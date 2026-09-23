"""FastAPI dependencies: authentication, plan and quotas.

Two credential kinds share the `Authorization: Bearer` header. A session JWT
serves the web front and expires within hours; a revocable API key serves the
VS Code extension and CI, where a daily re-login inside the editor would be
unusable.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from legacydoc_core.db import get_db
from legacydoc_core.errors import (
    AuthenticationError,
    NotFoundError,
    QuotaExceededError,
)
from legacydoc_core.models import ApiKey, Job, JobStatus, Project, UsageRecord, User
from legacydoc_core.plans import Feature, PlanLimits, get_plan
from legacydoc_core.queue import count_active_jobs_for_user
from legacydoc_core.security import (
    api_key_lookup_prefix,
    api_key_matches,
    decode_access_token,
    looks_like_api_key,
)
from legacydoc_core.settings import Settings, get_settings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# auto_error=False so domain errors keep the shared response shape.
_bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    """Who is calling, and under which plan."""

    user: User
    plan: PlanLimits
    via_api_key: bool

    @property
    def id(self) -> uuid.UUID:
        return self.user.id

    def require(self, feature: Feature) -> None:
        if not self.plan.allows(feature):
            raise QuotaExceededError(
                f"O plano {self.plan.display_name} nao inclui este recurso.",
                details={"feature": str(feature), "plan": str(self.plan.tier)},
            )


def get_app_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


async def get_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> Principal:
    if credentials is None or not credentials.credentials.strip():
        raise AuthenticationError("Credencial ausente.")

    token = credentials.credentials.strip()

    user = (
        await _user_from_api_key(token, session)
        if looks_like_api_key(token)
        else await _user_from_jwt(token, session, settings)
    )

    if not user.is_active:
        raise AuthenticationError("Conta desativada.")

    return Principal(
        user=user,
        plan=get_plan(user.plan_tier),
        via_api_key=looks_like_api_key(token),
    )


async def _user_from_jwt(token: str, session: AsyncSession, settings: Settings) -> User:
    payload = decode_access_token(token, settings)

    try:
        user_id = uuid.UUID(payload.user_id)
    except ValueError as exc:
        raise AuthenticationError("Token invalido.") from exc

    user = await session.get(User, user_id)

    if user is None:
        raise AuthenticationError("Usuario nao encontrado.")

    return user


async def _user_from_api_key(token: str, session: AsyncSession) -> User:
    """Look up by indexed prefix, then confirm in constant time."""
    rows = (
        await session.execute(
            select(ApiKey).where(
                ApiKey.prefix == api_key_lookup_prefix(token),
                ApiKey.revoked_at.is_(None),
            )
        )
    ).scalars()

    for candidate in rows:
        if api_key_matches(token, candidate.key_hash):
            candidate.last_used_at = datetime.now(UTC)

            user = await session.get(User, candidate.user_id)

            if user is None:
                raise AuthenticationError("Usuario da chave nao existe mais.")

            return user

    raise AuthenticationError("Chave de API invalida ou revogada.")


async def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    """Acesso ao painel de contas.

    Recusa chave de API de proposito, aceitando apenas sessao. Chave e uma
    credencial longa, feita para ficar guardada em maquina de CI e no editor;
    transformar isso em acesso administrativo significaria que um vazamento de
    chave entrega o painel junto.

    Responde 404, e nao 403, pelo mesmo motivo do resto da API: 403 confirmaria
    para quem esta sondando que existe um painel neste caminho.
    """
    if principal.via_api_key or not principal.user.is_admin:
        raise NotFoundError("Recurso nao encontrado.")

    return principal


# ------------------------------------------------------------------- cotas


async def count_jobs_this_month(session: AsyncSession, user_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    period_start = datetime(now.year, now.month, 1, tzinfo=UTC)

    result = await session.execute(
        select(func.count(Job.id)).where(
            Job.user_id == user_id,
            Job.created_at >= period_start,
            Job.status != JobStatus.CANCELLED,
        )
    )

    return int(result.scalar_one())


def _current_month_start() -> datetime:
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def spend_this_month(session: AsyncSession, user_id: uuid.UUID) -> float:
    """How much this user has cost in LLM spend during the current month."""
    result = await session.execute(
        select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= _current_month_start(),
        )
    )
    return float(result.scalar_one())


async def global_spend_this_month(session: AsyncSession) -> float:
    """System-wide spend for the current month."""
    result = await session.execute(
        select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).where(
            UsageRecord.created_at >= _current_month_start()
        )
    )
    return float(result.scalar_one())


async def enforce_cost_budget(
    principal: Principal,
    session: AsyncSession,
    settings: Settings,
) -> None:
    """Block on real spend rather than job count.

    The per-user ceiling stops one account from consuming the budget; the global
    ceiling is the last line of defense for the card, since many accounts each
    within their own limit can still add up beyond what the operator can pay.

    Checked before enqueueing and never interrupting a running job, so spend can
    overshoot slightly by the cost of a job already accepted. It is a brake,
    not an exact fence.
    """
    global_spend = await global_spend_this_month(session)

    if global_spend >= settings.global_monthly_budget_usd:
        raise QuotaExceededError(
            "O sistema atingiu o limit de processamento deste mes. Tente novamente no proximo mes.",
            details={
                "scope": "global",
                "spent_usd": round(global_spend, 4),
                "limit_usd": settings.global_monthly_budget_usd,
            },
        )

    user_spend = await spend_this_month(session, principal.id)
    limit = principal.plan.monthly_cost_limit_usd

    if user_spend >= limit:
        raise QuotaExceededError(
            f"Voce atingiu o limit de processamento do plano "
            f"{principal.plan.display_name} neste mes "
            f"(US$ {user_spend:.2f} de US$ {limit:.2f}).",
            details={
                "scope": "user",
                "spent_usd": round(user_spend, 4),
                "limit_usd": limit,
            },
        )


async def enforce_job_quota(principal: Principal, session: AsyncSession) -> None:
    """Block before enqueueing.

    The monthly quota caps total cost; the concurrency limit stops one user
    from occupying every worker.
    """
    used = await count_jobs_this_month(session, principal.id)

    if used >= principal.plan.monthly_job_quota:
        raise QuotaExceededError(
            f"Cota mensal do plano {principal.plan.display_name} atingida "
            f"({used}/{principal.plan.monthly_job_quota}).",
            details={"used": used, "quota": principal.plan.monthly_job_quota},
        )

    active = await count_active_jobs_for_user(session, principal.id)

    if active >= principal.plan.max_concurrent_jobs:
        raise QuotaExceededError(
            f"Voce ja tem {active} job(s) em andamento, o maximo do plano "
            f"{principal.plan.display_name}. Aguarde terminar.",
            details={"active": active, "limit": principal.plan.max_concurrent_jobs},
        )


async def get_owned_project(
    project_id: uuid.UUID,
    principal: Principal,
    session: AsyncSession,
) -> Project:
    """Load a project, ensuring it belongs to the caller.

    Returns 404 rather than 403 on purpose: a 403 would reveal that the id
    exists.
    """
    project = await session.get(Project, project_id)

    if project is None or project.owner_id != principal.id:
        raise NotFoundError("Projeto nao encontrado.")

    return project
