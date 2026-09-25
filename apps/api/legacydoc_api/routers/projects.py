"""Projects and the context API."""

from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, status
from legacydoc_core.db import get_db
from legacydoc_core.errors import ConflictError, NotFoundError, ValidationError
from legacydoc_core.models import ContextItem, Project
from legacydoc_core.plans import Feature
from legacydoc_core.repository import validate_repo_url
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.deps import Principal, get_owned_project, get_principal
from legacydoc_api.schemas import (
    ContextItemCreateRequest,
    ContextItemResponse,
    ProjectCreateRequest,
    ProjectResponse,
    ProjectUpdateRequest,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])

MAX_CONTEXT_ITEMS_PER_PROJECT = 200


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:160] or "projeto"


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> list[ProjectResponse]:
    rows = (
        await session.execute(
            select(Project)
            .where(Project.owner_id == principal.id)
            .order_by(Project.created_at.desc())
        )
    ).scalars()

    return [_to_response(project) for project in rows]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreateRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    if payload.repo_url:
        validate_repo_url(payload.repo_url)

    project = Project(
        owner_id=principal.id,
        name=payload.name,
        slug=_slugify(payload.name),
        repo_url=payload.repo_url,
        default_branch=payload.default_branch,
        description=payload.description,
    )
    session.add(project)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("Voce ja tem um projeto com esse nome.") from exc

    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    return _to_response(await get_owned_project(project_id, principal, session))


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    project = await get_owned_project(project_id, principal, session)

    if payload.repo_url:
        validate_repo_url(payload.repo_url)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)

    if payload.name:
        project.slug = _slugify(payload.name)

    return _to_response(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> None:
    project = await get_owned_project(project_id, principal, session)
    await session.delete(project)


@router.get("/{project_id}/context", response_model=list[ContextItemResponse])
async def list_context(
    project_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> list[ContextItemResponse]:
    await get_owned_project(project_id, principal, session)

    rows = (
        await session.execute(
            select(ContextItem)
            .where(ContextItem.project_id == project_id)
            .order_by(ContextItem.weight.desc(), ContextItem.created_at.desc())
        )
    ).scalars()

    return [_context_to_response(item) for item in rows]


@router.post(
    "/{project_id}/context",
    response_model=ContextItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_context(
    project_id: uuid.UUID,
    payload: ContextItemCreateRequest,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> ContextItemResponse:
    principal.require(Feature.PROJECT_CONTEXT)
    await get_owned_project(project_id, principal, session)

    total = int(
        (
            await session.execute(
                select(func.count(ContextItem.id)).where(ContextItem.project_id == project_id)
            )
        ).scalar_one()
    )

    if total >= MAX_CONTEXT_ITEMS_PER_PROJECT:
        raise ValidationError(
            f"Limite de {MAX_CONTEXT_ITEMS_PER_PROJECT} itens de contexto por projeto atingido."
        )

    item = ContextItem(
        project_id=project_id,
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        path_globs=payload.path_globs,
        tags=payload.tags,
        weight=payload.weight,
    )
    session.add(item)
    await session.flush()

    return _context_to_response(item)


@router.delete(
    "/{project_id}/context/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_context(
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    principal: Principal = Depends(get_principal),
    session: AsyncSession = Depends(get_db),
) -> None:
    await get_owned_project(project_id, principal, session)

    item = await session.get(ContextItem, item_id)

    if item is None or item.project_id != project_id:
        raise NotFoundError("Item de contexto nao encontrado.")

    await session.delete(item)


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        repo_url=project.repo_url,
        default_branch=project.default_branch,
        description=project.description,
        created_at=project.created_at,
    )


def _context_to_response(item: ContextItem) -> ContextItemResponse:
    return ContextItemResponse(
        id=item.id,
        kind=item.kind,
        title=item.title,
        content=item.content,
        path_globs=list(item.path_globs or []),
        tags=list(item.tags or []),
        weight=item.weight,
        created_at=item.created_at,
    )
