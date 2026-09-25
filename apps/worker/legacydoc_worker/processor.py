"""Job execution: from the queue to stored documents."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from legacydoc_agents import DocumentationPipeline, PipelineOptions
from legacydoc_agents.context_selector import ContextCandidate
from legacydoc_core.archive import safe_extract
from legacydoc_core.errors import LegacyDocError, ValidationError
from legacydoc_core.models import (
    ContextItem,
    Document,
    Finding,
    Job,
    JobType,
    UsageRecord,
    User,
)
from legacydoc_core.plans import GenerationDepth, get_plan, resolve_depth
from legacydoc_core.queue import heartbeat
from legacydoc_core.repository import RepoFile, RepositoryLoader, cleanup_directory
from legacydoc_core.settings import Settings
from legacydoc_parsing.languages import SUPPORTED_EXTENSIONS, detect_language
from legacydoc_parsing.symbol_index import SymbolIndex
from legacydoc_parsing.symbols import parse_file
from legacydoc_providers.router import CallRecord, ProviderRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class JobOutcome:
    documents_created: int
    warnings: list[str]


class JobProcessor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._loader = RepositoryLoader(
            tmp_root=settings.tmp_dir,
            max_file_bytes=settings.max_source_file_bytes,
            max_files=settings.max_repo_files,
            max_total_bytes=settings.max_repo_bytes,
            clone_timeout_seconds=settings.clone_timeout_seconds,
        )

    async def process(
        self,
        session: AsyncSession,
        job: Job,
        *,
        worker_id: str,
    ) -> JobOutcome:
        user = await session.get(User, job.user_id)

        if user is None:
            raise ValidationError("Usuario do job nao existe mais.")

        plan = get_plan(user.plan_tier)
        params = job.params or {}

        router = ProviderRouter.from_settings(
            self._settings,
            usage_sink=self._make_usage_sink(session, job),
        )

        # Resolved here and not read straight from the parameters: a job can
        # sit in the queue while the account changes plan, and the plan in
        # force at execution time is the one that decides what gets paid for.
        depth = resolve_depth(params.get("depth"), plan)

        pipeline = DocumentationPipeline(
            router,
            plan,
            PipelineOptions(
                output_language=params.get("output_language", "pt-BR"),
                chunk_concurrency=self._settings.chunk_concurrency,
                depth=depth,
            ),
        )

        try:
            if job.job_type == JobType.DOCUMENT_SNIPPET:
                files = [self._snippet_to_file(params)]
                return await self._document_files(
                    session, job, pipeline, files, worker_id=worker_id
                )

            if job.job_type == JobType.DOCUMENT_ARCHIVE:
                return await self._document_archive(
                    session,
                    job,
                    pipeline,
                    params,
                    plan_max_files=plan.max_files_per_job,
                    worker_id=worker_id,
                )

            return await self._document_repository(
                session,
                job,
                pipeline,
                params,
                plan_max_files=plan.max_files_per_job,
                worker_id=worker_id,
            )
        finally:
            await router.aclose()

    async def _document_archive(
        self,
        session: AsyncSession,
        job: Job,
        pipeline: DocumentationPipeline,
        params: dict,
        *,
        plan_max_files: int,
        worker_id: str,
    ) -> JobOutcome:
        """Extract the uploaded archive and document whatever is inside."""
        archive_path = Path(params["archive_path"])

        if not archive_path.is_file():
            raise ValidationError("O arquivo enviado nao esta mais disponivel. Envie novamente.")

        await self._progress(session, job, worker_id, 5, "Extraindo o arquivo enviado...")

        extraction_dir = self._settings.tmp_dir / f"archive_{job.id.hex[:12]}"

        try:
            extraction = await asyncio.to_thread(
                safe_extract,
                archive_path,
                extraction_dir,
                max_files=self._settings.max_archive_entries,
                max_total_bytes=self._settings.max_repo_bytes,
                max_file_bytes=self._settings.max_source_file_bytes,
                allowed_suffixes=SUPPORTED_EXTENSIONS,
            )

            await self._progress(session, job, worker_id, 10, "Varrendo arquivos...")

            scan = await self._loader.scan(extraction_dir)

            if not scan.files:
                raise ValidationError("Nenhum arquivo de codigo suportado no .zip.")

            files = scan.files[:plan_max_files]
            warnings: list[str] = []

            warnings.extend(
                f"Entrada ignorada por seguranca - {reason}"
                for reason in extraction.rejected_entries[:10]
            )

            if len(scan.files) > plan_max_files:
                warnings.append(
                    f"O .zip tem {len(scan.files)} arquivos suportados; o plano cobre "
                    f"{plan_max_files}. Os demais foram ignorados."
                )

            outcome = await self._document_files(session, job, pipeline, files, worker_id=worker_id)
            outcome.warnings = warnings + outcome.warnings

            return outcome
        finally:
            cleanup_directory(extraction_dir)
            # The upload only feeds this job; keeping it would accumulate disk
            # and leave customer code sitting on the server.
            archive_path.unlink(missing_ok=True)

    # ------------------------------------------------------------ entradas

    def _snippet_to_file(self, params: dict) -> RepoFile:
        import hashlib

        path = params["path"]
        content = params["content"]
        language = detect_language(path)

        if language is None:
            raise ValidationError(f"Extensao nao suportada: {path}")

        return RepoFile(
            path=path,
            content=content,
            size_bytes=len(content.encode("utf-8")),
            language=language.name,
            sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        )

    async def _document_repository(
        self,
        session: AsyncSession,
        job: Job,
        pipeline: DocumentationPipeline,
        params: dict,
        *,
        plan_max_files: int,
        worker_id: str,
    ) -> JobOutcome:
        await self._progress(session, job, worker_id, 5, "Clonando repositorio...")

        clone_dir = await self._loader.clone(params["repo_url"], branch=params.get("branch"))

        try:
            await self._progress(session, job, worker_id, 10, "Varrendo arquivos...")

            scan = await self._loader.scan(clone_dir, only_paths=params.get("paths") or None)

            if not scan.files:
                raise ValidationError(
                    "Nenhum arquivo de codigo suportado encontrado. "
                    f"Arquivos vistos: {scan.total_files_seen}."
                )

            # The plan ceiling applies even when no paths were requested.
            files = scan.files[:plan_max_files]

            warnings: list[str] = []

            if len(scan.files) > plan_max_files:
                warnings.append(
                    f"O repositorio tem {len(scan.files)} arquivos suportados; "
                    f"o plano cobre {plan_max_files}. Os demais foram ignorados."
                )
            if scan.truncated:
                warnings.append("A varredura parou ao atingir o limite de tamanho do repositorio.")
            if scan.skipped_too_large:
                warnings.append(f"{scan.skipped_too_large} arquivo(s) grandes demais ignorados.")

            outcome = await self._document_files(session, job, pipeline, files, worker_id=worker_id)
            outcome.warnings = warnings + outcome.warnings

            return outcome
        finally:
            # Always cleaned: v1 left a 101 MB orphaned clone behind.
            cleanup_directory(clone_dir)

    # -------------------------------------------------------- processamento

    async def _document_files(
        self,
        session: AsyncSession,
        job: Job,
        pipeline: DocumentationPipeline,
        files: list[RepoFile],
        *,
        worker_id: str,
    ) -> JobOutcome:
        context_items = await self._load_context(session, job.project_id)

        # Parses everything up front: costs CPU and zero tokens, and lets the
        # writer understand calls into other files instead of guessing.
        symbol_index = await asyncio.to_thread(self._build_index, files)

        logger.info(
            "Indice do job %s: %d simbolos em %d arquivo(s).",
            job.id,
            symbol_index.symbol_count,
            symbol_index.file_count,
        )

        total = len(files)
        created = 0
        warnings: list[str] = []

        # A retry starts the job over, but files documented before the failure
        # were already committed. Skipping them saves the tokens and avoids
        # colliding with the unique (job, path) constraint.
        already_documented = await self._documented_paths(session, job)

        for index, repo_file in enumerate(files, start=1):
            language = detect_language(repo_file.path)

            if language is None:
                continue

            if repo_file.path in already_documented:
                created += 1
                continue

            percent = 15 + int((index - 1) / max(total, 1) * 80)

            alive = await self._progress(
                session,
                job,
                worker_id,
                percent,
                f"Documentando {repo_file.path} ({index}/{total})",
            )

            # A lost lease means another worker took this job; continuing would
            # duplicate documents and bill tokens twice.
            if not alive:
                logger.warning("Lease perdido no job %s; abortando.", job.id)
                break

            try:
                result = await pipeline.run(
                    path=repo_file.path,
                    source=repo_file.content,
                    language=language,
                    context_items=context_items,
                    symbol_index=symbol_index,
                )
            except LegacyDocError as exc:
                warnings.append(f"{repo_file.path}: {exc.message}")
                continue

            warnings.extend(f"{repo_file.path}: {item}" for item in result.warnings)

            # Realimenta o symbol_index: arquivos processados depois passam a ver o
            symbol_index.attach_summaries(
                repo_file.path,
                {s.name: s.summary for s in result.documentation.symbols if s.summary},
            )

            self._persist(session, job, repo_file, result, depth=pipeline.depth)
            created += 1

            # Commit per file so a late failure keeps the files already paid for.
            await session.commit()

        return JobOutcome(documents_created=created, warnings=warnings)

    async def _documented_paths(self, session: AsyncSession, job: Job) -> set[str]:
        rows = await session.execute(select(Document.path).where(Document.job_id == job.id))

        return set(rows.scalars())

    def _persist(
        self,
        session: AsyncSession,
        job: Job,
        repo_file: RepoFile,
        result,
        *,
        depth: GenerationDepth,
    ) -> None:
        document = Document(
            job_id=job.id,
            project_id=job.project_id,
            user_id=job.user_id,
            path=repo_file.path,
            language=repo_file.language,
            content_sha256=repo_file.sha256,
            depth=str(depth),
            summary=result.documentation.summary or None,
            symbols=[symbol.model_dump(mode="json") for symbol in result.documentation.symbols],
        )
        session.add(document)

        for draft in result.documentation.findings:
            session.add(
                Finding(
                    document=document,
                    category=str(draft.category),
                    severity=str(draft.severity),
                    title=draft.title,
                    detail=draft.detail,
                    suggestion=draft.suggestion,
                    symbol_name=draft.symbol_name,
                    line_start=draft.line_start,
                    line_end=draft.line_end,
                    confidence=draft.confidence,
                )
            )

    def _build_index(self, files: list[RepoFile]) -> SymbolIndex:
        """Monta o symbol_index de simbolos de todos os arquivos do job.

        Sincrono e chamado em thread: o parsing e CPU-bound e travaria o
        event loop do worker.
        """
        symbol_index = SymbolIndex()

        for repo_file in files:
            language = detect_language(repo_file.path)

            if language is None:
                continue

            try:
                symbol_index.add_file(parse_file(repo_file.path, repo_file.content, language))
            except Exception:
                # The index is a quality improvement, not a requirement.
                logger.warning("Falha ao indexar %s; seguindo.", repo_file.path)

        return symbol_index

    async def _load_context(
        self, session: AsyncSession, project_id: uuid.UUID | None
    ) -> list[ContextCandidate]:
        if project_id is None:
            return []

        rows = (
            await session.execute(select(ContextItem).where(ContextItem.project_id == project_id))
        ).scalars()

        return [
            ContextCandidate(
                id=str(item.id),
                kind=item.kind,
                title=item.title,
                content=item.content,
                path_globs=tuple(item.path_globs or []),
                tags=tuple(item.tags or []),
                weight=item.weight,
            )
            for item in rows
        ]

    # ------------------------------------------------------------- apoio

    def _make_usage_sink(self, session: AsyncSession, job: Job):
        """Record telemetry for each LLM call, flushed with the file commit."""
        pending: list[CallRecord] = []

        async def sink(record: CallRecord) -> None:
            pending.append(record)

            session.add(
                UsageRecord(
                    user_id=job.user_id,
                    job_id=job.id,
                    agent=record.agent,
                    provider=record.provider,
                    model=record.model,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    cost_usd=record.cost_usd,
                    latency_ms=record.latency_ms,
                    succeeded=record.succeeded,
                )
            )

        return sink

    async def _progress(
        self,
        session: AsyncSession,
        job: Job,
        worker_id: str,
        percent: int,
        message: str,
    ) -> bool:
        alive = await heartbeat(
            session,
            job_id=job.id,
            worker_id=worker_id,
            lease_seconds=self._settings.job_lease_seconds,
            progress_percent=percent,
            progress_message=message,
        )
        await session.commit()

        return alive
