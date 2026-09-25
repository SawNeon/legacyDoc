"""Jobs: enqueue, track and cancel."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile, status
from legacydoc_core.archive import looks_like_zip
from legacydoc_core.db import get_db
from legacydoc_core.errors import ConflictError, NotFoundError, ValidationError
from legacydoc_core.models import Document, Job, JobStatus, JobType
from legacydoc_core.plans import Feature, GenerationDepth, resolve_depth
from legacydoc_core.queue import cancel_job, enqueue
from legacydoc_core.repository import validate_repo_url
from legacydoc_core.settings import Settings
from legacydoc_parsing.languages import detect_language
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.deps import (
    Principal,
    enforce_cost_budget,
    enforce_job_quota,
    get_app_settings,
    get_owned_project,
    get_principal,
)
from legacydoc_api.schemas import (
    JobListResponse,
    JobResponse,
    RepositoryJobRequest,
    SnippetJobRequest,
)

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

JobRequestBody = Annotated[
    RepositoryJobRequest | SnippetJobRequest,
    Body(discriminator="job_type"),
]


@router.post("", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    payload: JobRequestBody,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> JobResponse:
    """Enqueue a job and return 202 immediately."""
    await enforce_cost_budget(principal, session, settings)
    await enforce_job_quota(principal, session)

    if payload.project_id is not None:
        await get_owned_project(payload.project_id, principal, session)

    if payload.webhook_url:
        principal.require(Feature.WEBHOOKS)

    depth = resolve_depth(payload.depth, principal.plan)

    params: dict = {
        "output_language": payload.output_language,
        "depth": str(depth),
    }

    if isinstance(payload, RepositoryJobRequest):
        validate_repo_url(payload.repo_url)

        if len(payload.paths) > principal.plan.max_files_per_job:
            raise ValidationError(
                f"O plano {principal.plan.display_name} permite ate "
                f"{principal.plan.max_files_per_job} arquivos por job; "
                f"foram pedidos {len(payload.paths)}."
            )

        job_type = JobType.DOCUMENT_REPOSITORY
        params |= {
            "repo_url": payload.repo_url,
            "branch": payload.branch,
            "paths": payload.paths,
            "max_files": principal.plan.max_files_per_job,
        }
    else:
        if detect_language(payload.path) is None:
            raise ValidationError(
                f"Extensao nao suportada em '{payload.path}'. Consulte GET /v1/meta/languages."
            )

        job_type = JobType.DOCUMENT_SNIPPET
        params |= {"path": payload.path, "content": payload.content}

    job = await enqueue(
        session,
        user_id=principal.id,
        job_type=str(job_type),
        params=params,
        priority=principal.plan.queue_priority,
        project_id=payload.project_id,
        webhook_url=payload.webhook_url,
    )

    return _to_response(job, document_count=0)


@router.post("/upload", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_upload_job(
    file: UploadFile = File(..., description="Arquivo .zip com o codigo-fonte"),
    project_id: uuid.UUID | None = Form(default=None),
    output_language: str = Form(default="pt-BR"),
    depth: GenerationDepth | None = Form(default=None),
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> JobResponse:
    """Enqueue documentation for an uploaded archive."""
    await enforce_cost_budget(principal, session, settings)
    await enforce_job_quota(principal, session)

    if project_id is not None:
        await get_owned_project(project_id, principal, session)

    filename = (file.filename or "envio.zip").strip()

    if not filename.lower().endswith(".zip"):
        raise ValidationError("Envie um arquivo .zip.")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    destination = settings.upload_dir / f"{uuid.uuid4().hex}.zip"

    bytes_written = 0
    first_block = b""

    try:
        with open(destination, "wb") as sink:
            while block := await file.read(1024 * 1024):
                if not first_block:
                    first_block = block[:8]

                bytes_written += len(block)

                if bytes_written > settings.max_upload_bytes:
                    raise ValidationError(
                        f"O arquivo passa de {settings.max_upload_bytes // 1024 // 1024} MB."
                    )

                sink.write(block)

        if bytes_written == 0:
            raise ValidationError("O arquivo enviado esta vazio.")

        if not looks_like_zip(first_block):
            raise ValidationError("O conteudo enviado nao e um .zip.")
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    job = await enqueue(
        session,
        user_id=principal.id,
        job_type=str(JobType.DOCUMENT_ARCHIVE),
        params={
            "archive_path": str(destination),
            "original_filename": filename,
            "output_language": output_language,
            "depth": str(resolve_depth(depth, principal.plan)),
            "max_files": principal.plan.max_files_per_job,
        },
        priority=principal.plan.queue_priority,
        project_id=project_id,
    )

    return _to_response(job, document_count=0)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    job_status: str | None = Query(default=None, alias="status"),
) -> JobListResponse:
    filters = [Job.user_id == principal.id]

    if job_status:
        filters.append(Job.status == job_status)

    total = int((await session.execute(select(func.count(Job.id)).where(*filters))).scalar_one())

    rows = list(
        (
            await session.execute(
                select(Job)
                .where(*filters)
                .order_by(Job.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
    )

    counts = await _document_counts(session, [job.id for job in rows])

    return JobListResponse(
        items=[_to_response(job, counts.get(job.id, 0)) for job in rows],
        total=total,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> JobResponse:
    job = await _owned_job(job_id, principal, session)
    counts = await _document_counts(session, [job.id])

    return _to_response(job, counts.get(job.id, 0))


@router.delete("/{job_id}", response_model=JobResponse)
async def cancel(
    job_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> JobResponse:
    """Cancel a job that has not started."""
    job = await _owned_job(job_id, principal, session)

    if JobStatus(job.status).is_terminal:
        raise ConflictError(f"O job ja esta em estado terminal ({job.status}).")

    if not await cancel_job(session, job_id=job_id):
        raise ConflictError("O job ja saiu da fila e nao pode mais ser cancelado.")

    await session.refresh(job)

    return _to_response(job, 0)


async def _owned_job(job_id: uuid.UUID, principal: Principal, session: AsyncSession) -> Job:
    job = await session.get(Job, job_id)

    if job is None or job.user_id != principal.id:
        raise NotFoundError("Job nao encontrado.")

    return job


async def _document_counts(session: AsyncSession, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Count documents per job in one query, avoiding N+1 on listings."""
    if not job_ids:
        return {}

    rows = await session.execute(
        select(Document.job_id, func.count(Document.id))
        .where(Document.job_id.in_(job_ids))
        .group_by(Document.job_id)
    )

    return {job_id: count for job_id, count in rows.all()}


def _to_response(job: Job, document_count: int) -> JobResponse:
    return JobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress_percent=job.progress_percent,
        progress_message=job.progress_message,
        attempts=job.attempts,
        project_id=job.project_id,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error_code=job.error_code,
        error_message=job.error_message,
        document_count=document_count,
        depth=(job.params or {}).get("depth", str(GenerationDepth.BASIC)),
        source=_source_of(job),
    )


def _source_of(job: Job) -> str | None:
    """O que foi analisado, no formato que faz sentido para cada tipo de job."""
    params = job.params or {}

    return params.get("repo_url") or params.get("original_filename") or params.get("path")
