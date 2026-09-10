"""Multi-agent orchestration.

Replaces v1's LangGraph graph with an explicit async pipeline, which buys:

- Real concurrency: a file's chunks run in parallel under a semaphore, where
  v1 processed them serially.
- Per-agent routing: each role picks its own provider and model, where v1 had a
  fixed OpenAI client inside every agent.
- Cost accounting: every call goes through the router, which records telemetry.
- A review loop that works: in v1 the comparison was always false, so the
  verifier ran on the most expensive model and its result was discarded without
  rewriting anything. Here rewriting happens, and only for rejected symbols.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from legacydoc_core.domain import (
    FileDocumentation,
    FindingDraft,
    ImproverOutput,
    SummarizerOutput,
    SymbolDoc,
    VerifierOutput,
    WriterOutput,
)
from legacydoc_core.errors import ProviderError
from legacydoc_core.plans import Feature, PlanLimits
from legacydoc_parsing.chunking import CodeChunk, build_chunks
from legacydoc_parsing.languages import LanguageInfo
from legacydoc_parsing.symbol_index import SymbolIndex, render_external_symbols
from legacydoc_parsing.symbols import ParsedFile, SymbolSpan, parse_file
from legacydoc_providers.router import AgentRole, ProviderRouter

from legacydoc_agents import prompts
from legacydoc_agents.context_selector import ContextCandidate, render_context, select_context

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, str], Awaitable[None]]


@dataclass
class PipelineOptions:
    output_language: str = "pt-BR"
    max_tokens_per_chunk: int = 6000
    chunk_concurrency: int = 6
    max_review_rounds: int = 1
    """How many times the writer may rewrite after a verifier rejection."""
    generate_summary: bool = True


@dataclass
class PipelineResult:
    documentation: FileDocumentation
    verifier_feedback: str = ""
    verifier_approved: bool = True
    review_rounds: int = 0
    chunks_processed: int = 0
    chunks_failed: int = 0
    warnings: list[str] = field(default_factory=list)


class DocumentationPipeline:
    """Runs the agents over a single file."""

    def __init__(
        self,
        router: ProviderRouter,
        plan: PlanLimits,
        options: PipelineOptions | None = None,
    ) -> None:
        self._router = router
        self._plan = plan
        self._options = options or PipelineOptions()

    async def run(
        self,
        *,
        path: str,
        source: str,
        language: LanguageInfo,
        context_items: list[ContextCandidate] | None = None,
        symbol_index: SymbolIndex | None = None,
        progress: ProgressCallback | None = None,
    ) -> PipelineResult:
        options = self._options

        parsed = parse_file(path, source, language)
        chunks = build_chunks(parsed, max_tokens_per_chunk=options.max_tokens_per_chunk)

        result = PipelineResult(documentation=FileDocumentation(path=path, language=language.name))

        if not chunks:
            result.warnings.append("Arquivo sem conteudo analisavel.")
            return result

        if parsed.parse_failed:
            result.warnings.append(
                f"Gramatica {language.name} indisponivel; o arquivo foi dividido por linhas."
            )

        prompt_context = self._build_prompt_context(
            language=language,
            file_path=path,
            source=source,
            context_items=context_items or [],
        )

        await self._report(progress, 15, "Analisando estrutura do codigo...")

        reader_notes = await self._run_reader(parsed, prompt_context)

        await self._report(progress, 25, f"Documentando {len(chunks)} bloco(s)...")

        symbols, findings, failed, invented_symbols = await self._process_chunks(
            chunks, prompt_context, reader_notes, path=path, symbol_index=symbol_index
        )

        result.chunks_processed = len(chunks) - failed
        result.chunks_failed = failed

        if failed:
            result.warnings.append(
                f"{failed} de {len(chunks)} blocos falharam e ficaram fora da documentacao."
            )

        if invented_symbols:
            # Surfaced deliberately: heavy invention in one file makes the rest
            # of its documentation suspect too.
            result.warnings.append(
                "Descartado(s) por nao existir(em) no codigo: "
                + ", ".join(sorted(set(invented_symbols))[:10])
            )

        result.documentation.symbols = symbols
        result.documentation.findings = findings

        if symbols and self._plan.allows(Feature.VERIFIER_AGENT):
            await self._report(progress, 70, "Auditando fidelidade da documentacao...")
            await self._review_loop(result, source=source, path=path, context=prompt_context)

        if options.generate_summary and symbols:
            await self._report(progress, 90, "Consolidando resumo do arquivo...")
            result.documentation.summary = await self._run_summarizer(path, symbols, prompt_context)

        return result

    # ------------------------------------------------------------- agentes

    async def _run_reader(self, parsed: ParsedFile, context: prompts.PromptContext) -> str:
        """Upfront diagnosis. A failure here is not fatal: the output is advisory."""
        from pydantic import BaseModel, Field

        class ReaderOutput(BaseModel):
            ready_to_write: bool = Field(description="True se o codigo se explica sozinho")
            queries: str = Field(default="", description="Perguntas tecnicas em ingles")
            user_facing_message: str = Field(default="")

        sample = parsed.source[:12000]

        try:
            result = await self._router.complete(
                AgentRole.READER,
                system=prompts.reader_system(context),
                user=f"Arquivo: {parsed.path}\n\nCODIGO:\n{sample}",
                schema=ReaderOutput,
            )
        except ProviderError as exc:
            logger.warning("Reader falhou em %s: %s", parsed.path, exc.message)
            return ""

        if result.value.ready_to_write:
            return ""

        return result.value.queries.strip()

    async def _process_chunks(
        self,
        chunks: list[CodeChunk],
        context: prompts.PromptContext,
        reader_notes: str,
        *,
        path: str,
        symbol_index: SymbolIndex | None = None,
    ) -> tuple[list[SymbolDoc], list[FindingDraft], int, list[str]]:
        """Run the writer, and the improver when the plan allows, across chunks.

        A failing chunk does not sink the rest: the job delivers partial
        documentation with a warning rather than nothing.
        """
        semaphore = asyncio.Semaphore(self._options.chunk_concurrency)
        wants_findings = self._plan.allows(Feature.IMPROVEMENT_FINDINGS)

        async def handle(chunk: CodeChunk):
            async with semaphore:
                writer_task = self._run_writer(
                    chunk, context, reader_notes, path=path, symbol_index=symbol_index
                )

                if wants_findings:
                    improver_task = self._run_improver(chunk, context, path=path)
                    return await asyncio.gather(writer_task, improver_task, return_exceptions=True)

                written = await asyncio.gather(writer_task, return_exceptions=True)
                return [written[0], ImproverOutput()]

        outcomes = await asyncio.gather(*(handle(chunk) for chunk in chunks))

        symbols: list[SymbolDoc] = []
        findings: list[FindingDraft] = []
        discarded: list[str] = []
        failed = 0

        for chunk, (written, improved) in zip(chunks, outcomes, strict=True):
            if isinstance(written, Exception):
                logger.warning("Writer falhou no bloco %s de %s: %s", chunk.index, path, written)
                failed += 1
            else:
                accepted, invented = self._enrich(written.symbols, chunk, context.language)
                symbols.extend(accepted)
                discarded.extend(invented)

            if isinstance(improved, Exception):
                logger.warning("Improver falhou no bloco %s de %s: %s", chunk.index, path, improved)
            elif improved is not None:
                findings.extend(improved.findings)

        return (
            _dedupe_symbols(symbols),
            _dedupe_findings(findings),
            failed,
            discarded,
        )

    async def _run_writer(
        self,
        chunk: CodeChunk,
        context: prompts.PromptContext,
        reader_notes: str,
        *,
        path: str,
        symbol_index: SymbolIndex | None = None,
    ) -> WriterOutput:
        external_symbols = ""

        if symbol_index is not None:
            external_symbols = render_external_symbols(
                symbol_index.references_in(chunk.source, exclude_path=path)
            )

        result = await self._router.complete(
            AgentRole.WRITER,
            system=prompts.writer_system(context),
            user=prompts.writer_user(
                chunk.source,
                file_path=path,
                reader_notes=reader_notes,
                external_symbols=external_symbols,
            ),
            schema=WriterOutput,
        )
        return result.value

    async def _run_improver(
        self,
        chunk: CodeChunk,
        context: prompts.PromptContext,
        *,
        path: str,
    ) -> ImproverOutput:
        hints = "\n".join(
            f"- {symbol.name}: complexidade ~{symbol.complexity}, {symbol.line_count} linhas"
            for symbol in chunk.symbols
        )

        result = await self._router.complete(
            AgentRole.IMPROVER,
            system=prompts.improver_system(context),
            user=prompts.improver_user(chunk.source, file_path=path, complexity_hints=hints),
            schema=ImproverOutput,
        )
        return result.value

    async def _review_loop(
        self,
        result: PipelineResult,
        *,
        source: str,
        path: str,
        context: prompts.PromptContext,
    ) -> None:
        """Audit, then rewrite only the rejected symbols.

        Rewriting the whole file over one bad symbol would burn tokens and risk
        degrading what was already correct.
        """
        for round_number in range(self._options.max_review_rounds + 1):
            documentation_json = json.dumps(
                [symbol.model_dump() for symbol in result.documentation.symbols],
                ensure_ascii=False,
            )[:60000]

            try:
                verdict = await self._router.complete(
                    AgentRole.VERIFIER,
                    system=prompts.verifier_system(context),
                    user=prompts.verifier_user(source[:60000], documentation_json, file_path=path),
                    schema=VerifierOutput,
                )
            except ProviderError as exc:
                result.warnings.append(f"Auditoria indisponivel: {exc.message}")
                return

            audit = verdict.value
            result.verifier_feedback = audit.feedback_message
            result.verifier_approved = audit.approved

            if audit.approved or not audit.rejected_symbols:
                return

            if round_number >= self._options.max_review_rounds:
                result.warnings.append(
                    "Auditoria apontou problemas que sobreviveram as reescritas: "
                    + ", ".join(audit.rejected_symbols[:10])
                )
                return

            result.review_rounds += 1
            await self._rewrite_rejected(result, audit, source=source, path=path, context=context)

    async def _rewrite_rejected(
        self,
        result: PipelineResult,
        audit: VerifierOutput,
        *,
        source: str,
        path: str,
        context: prompts.PromptContext,
    ) -> None:
        rejected = set(audit.rejected_symbols)
        targets = [s for s in result.documentation.symbols if s.name in rejected]

        if not targets:
            return

        lines = source.split("\n")
        rewritten: dict[str, SymbolDoc] = {}

        async def rewrite(symbol: SymbolDoc) -> None:
            start = max(symbol.line_start - 1, 0)
            end = min(symbol.line_end, len(lines))
            snippet = "\n".join(lines[start:end]) if end > start else symbol.signature

            try:
                fixed = await self._router.complete(
                    AgentRole.WRITER,
                    system=prompts.writer_system(context),
                    user=prompts.writer_user(
                        snippet,
                        file_path=path,
                        reader_notes=(
                            "A auditoria reprovou a documentacao anterior deste simbolo. "
                            f"Corrija exatamente estes pontos:\n{audit.audit_notes}"
                        ),
                    ),
                    schema=WriterOutput,
                )
            except ProviderError as exc:
                logger.warning("Reescrita de %s falhou: %s", symbol.name, exc.message)
                return

            for candidate in fixed.value.symbols:
                if candidate.name == symbol.name:
                    candidate.line_start = symbol.line_start
                    candidate.line_end = symbol.line_end
                    candidate.language = symbol.language
                    candidate.complexity_estimate = symbol.complexity_estimate
                    rewritten[symbol.name] = candidate

        await asyncio.gather(*(rewrite(symbol) for symbol in targets))

        result.documentation.symbols = [
            rewritten.get(symbol.name, symbol) for symbol in result.documentation.symbols
        ]

    async def _run_summarizer(
        self,
        path: str,
        symbols: list[SymbolDoc],
        context: prompts.PromptContext,
    ) -> str:
        digest = "\n".join(f"- {s.kind} {s.name}: {s.summary}" for s in symbols[:60])

        try:
            result = await self._router.complete(
                AgentRole.SUMMARIZER,
                system=prompts.summarizer_system(context),
                user=prompts.summarizer_user(path, digest),
                schema=SummarizerOutput,
            )
        except ProviderError as exc:
            logger.warning("Summarizer falhou em %s: %s", path, exc.message)
            return ""

        return result.value.summary

    # ------------------------------------------------------------ apoio

    def _build_prompt_context(
        self,
        *,
        language: LanguageInfo,
        file_path: str,
        source: str,
        context_items: list[ContextCandidate],
    ) -> prompts.PromptContext:
        project_context = ""

        if context_items and self._plan.allows(Feature.PROJECT_CONTEXT):
            selected = select_context(context_items, file_path=file_path, code_sample=source[:8000])
            project_context = render_context(selected)

        return prompts.PromptContext(
            language=language.display_name,
            output_language=self._options.output_language,
            project_context=project_context,
            file_path=file_path,
        )

    def _enrich(
        self, symbols: list[SymbolDoc], chunk: CodeChunk, language: str
    ) -> tuple[list[SymbolDoc], list[str]]:
        """Anchor model output to the AST, discarding what is not in the code.

        Line numbers, complexity and parent class come from the parser rather
        than the model: verifiable and free.

        A symbol the parser never saw is discarded. Models occasionally invent
        plausible functions, and before this they were stored as real
        documentation with `line_start=0`. The ground truth is already in hand;
        not using it wasted the cheapest defense against hallucination.

        Returns the accepted symbols and the discarded names, which become a
        warning.
        """
        for symbol in symbols:
            symbol.language = symbol.language or language

        # Without parser ground truth there is no way to tell invention from
        # fact, so everything is kept and the caller is warned.
        if not chunk.symbols:
            return symbols, []

        spans_by_name: dict[str, SymbolSpan] = {}

        for span in chunk.symbols:
            spans_by_name[span.name] = span

            # The model returns Class.method while the parser stores method plus parent.
            if span.parent:
                spans_by_name[f"{span.parent}.{span.name}"] = span
                spans_by_name[f"{span.parent.rsplit('.', 1)[-1]}.{span.name}"] = span

        accepted: list[SymbolDoc] = []
        discarded: list[str] = []

        for symbol in symbols:
            span = spans_by_name.get(symbol.name)

            if span is None:
                logger.warning(
                    "Simbolo '%s' documentado mas ausente do codigo em %s; descartado.",
                    symbol.name,
                    chunk.symbol_names,
                )
                discarded.append(symbol.name)
                continue

            # Normalise to the name as written in the code.
            symbol.name = span.name
            symbol.line_start = span.line_start
            symbol.line_end = span.line_end
            symbol.complexity_estimate = span.complexity
            symbol.parent = span.parent or symbol.parent

            if not symbol.signature:
                symbol.signature = span.signature

            accepted.append(symbol)

        return accepted, discarded

    async def _report(self, progress: ProgressCallback | None, percent: int, message: str) -> None:
        if progress is not None:
            await progress(percent, message)


def _dedupe_symbols(symbols: list[SymbolDoc]) -> list[SymbolDoc]:
    """Drop duplicates, keeping the most complete entry.

    A symbol can appear in two chunks when the header is resent.
    """
    best: dict[tuple[str, str | None], SymbolDoc] = {}

    for symbol in symbols:
        key = (symbol.name, symbol.parent)
        current = best.get(key)

        if current is None or len(symbol.description) > len(current.description):
            best[key] = symbol

    return sorted(best.values(), key=lambda s: (s.line_start, s.name))


def _dedupe_findings(findings: list[FindingDraft]) -> list[FindingDraft]:
    seen: set[tuple[str, str, str | None]] = set()
    unique: list[FindingDraft] = []

    for finding in findings:
        key = (finding.title.strip().lower(), str(finding.category), finding.symbol_name)

        if key in seen:
            continue

        seen.add(key)
        unique.append(finding)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

    return sorted(unique, key=lambda f: severity_order.get(str(f.severity), 9))
