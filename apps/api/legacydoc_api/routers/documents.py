"""Generated documents and artifact downloads.

Critical difference from v1: there is no `StaticFiles` here. v1 mounted the
output directories publicly with deterministic filenames, so anyone could
download any customer's documentation by guessing a name. Artifacts are now
rendered on demand from the database, for the owner only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from legacydoc_core.db import get_db
from legacydoc_core.domain import FileDocumentation, FindingDraft, SymbolDoc
from legacydoc_core.errors import NotFoundError
from legacydoc_core.models import Document, Finding
from legacydoc_core.plans import Feature
from legacydoc_exporters import ExporterFactory
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from legacydoc_api.deps import Principal, get_principal
from legacydoc_api.schemas import (
    DocumentResponse,
    DocumentSummaryResponse,
    FindingResponse,
)

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.get("", response_model=list[DocumentSummaryResponse])
async def list_documents(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
    job_id: uuid.UUID | None = Query(default=None),
    project_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[DocumentSummaryResponse]:
    filters = [Document.user_id == principal.id]

    if job_id is not None:
        filters.append(Document.job_id == job_id)
    if project_id is not None:
        filters.append(Document.project_id == project_id)

    rows = list(
        (
            await session.execute(
                select(Document)
                .where(*filters)
                .order_by(Document.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars()
    )

    finding_counts = await _finding_counts(session, [doc.id for doc in rows])

    return [
        DocumentSummaryResponse(
            id=doc.id,
            job_id=doc.job_id,
            path=doc.path,
            language=doc.language,
            summary=doc.summary,
            symbol_count=len(doc.symbols or []),
            finding_count=finding_counts.get(doc.id, 0),
            depth=doc.depth,
            created_at=doc.created_at,
        )
        for doc in rows
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> DocumentResponse:
    document = await _owned_document(document_id, principal, session)
    shows_findings = principal.plan.allows(Feature.IMPROVEMENT_FINDINGS)

    return DocumentResponse(
        id=document.id,
        job_id=document.job_id,
        path=document.path,
        language=document.language,
        summary=document.summary,
        symbols=[SymbolDoc.model_validate(item) for item in document.symbols or []],
        findings=(
            [_finding_to_response(item) for item in document.findings] if shows_findings else []
        ),
        # Findings are stored even when the plan hides them, so an upgrade
        # reveals prior analysis without reprocessing or re-billing tokens.
        findings_locked=bool(document.findings) and not shows_findings,
        depth=document.depth,
        created_at=document.created_at,
    )


@router.get("/{document_id}/export")
async def export_document(
    document_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
    export_format: str = Query(default="markdown", alias="format"),
) -> Response:
    """Render the artifact on demand, authenticated and scoped to the owner."""
    document = await _owned_document(document_id, principal, session)
    exporter = ExporterFactory.get(export_format)

    documentation = FileDocumentation(
        path=document.path,
        language=document.language,
        summary=document.summary or "",
        symbols=[SymbolDoc.model_validate(item) for item in document.symbols or []],
        findings=[
            FindingDraft(
                category=item.category,
                severity=item.severity,
                title=item.title,
                detail=item.detail,
                suggestion=item.suggestion,
                symbol_name=item.symbol_name,
                line_start=item.line_start,
                line_end=item.line_end,
                confidence=item.confidence,
            )
            for item in document.findings
        ],
    )

    result = exporter.export(
        documentation,
        include_findings=principal.plan.allows(Feature.IMPROVEMENT_FINDINGS),
    )

    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{result.suggested_filename}"',
            "Cache-Control": "private, no-store",
        },
    )


# ------------------------------------------------------------------ apoio


async def _owned_document(
    document_id: uuid.UUID, principal: Principal, session: AsyncSession
) -> Document:
    document = (
        await session.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(selectinload(Document.findings))
        )
    ).scalar_one_or_none()

    if document is None or document.user_id != principal.id:
        raise NotFoundError("Documento nao encontrado.")

    return document


async def _finding_counts(
    session: AsyncSession, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not document_ids:
        return {}

    rows = await session.execute(
        select(Finding.document_id, func.count(Finding.id))
        .where(Finding.document_id.in_(document_ids))
        .group_by(Finding.document_id)
    )

    return {document_id: count for document_id, count in rows.all()}


def _finding_to_response(finding: Finding) -> FindingResponse:
    return FindingResponse(
        id=finding.id,
        category=finding.category,
        severity=finding.severity,
        title=finding.title,
        detail=finding.detail,
        suggestion=finding.suggestion,
        symbol_name=finding.symbol_name,
        line_start=finding.line_start,
        line_end=finding.line_end,
        confidence=finding.confidence,
    )
