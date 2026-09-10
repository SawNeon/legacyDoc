"""Dependencias do FastAPI: autenticacao, plano e cotas.

Aceita duas credenciais no mesmo header `Authorization: Bearer <valor>`:

- JWT de sessao, para o front web (expira em horas).
- Chave de API `ldk_...`, para a extensao do VS Code e CI (nao expira; e
  revogavel). Sem isso o desenvolvedor teria que refazer login no editor todo
  dia.
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
    """Quem esta chamando, e com qual plano."""

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
    """Busca pelo prefixo indexado e confirma com comparacao em tempo constante."""
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
    """Quanto este usuario ja custou em LLM no mes corrente."""
    result = await session.execute(
        select(func.coalesce(func.sum(UsageRecord.cost_usd), 0.0)).where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= _current_month_start(),
        )
    )
    return float(result.scalar_one())


async def global_spend_this_month(session: AsyncSession) -> float:
    """Gasto do sistema inteiro no mes corrente."""
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
    """Bloqueia por gasto real, nao por numero de jobs.

    Sao dois tetos com finalidades distintas:

    - Por usuario: impede que uma conta sozinha consuma o orcamento.
    - Global: ultima linha de defesa do cartao. Cem contas dentro do proprio
      limit ainda podem somar mais do que da para pagar.

    A verificacao e feita ANTES de enfileirar. Nao interrompe job em andamento,
    entao o gasto pode passar um pouco do teto - o custo de um job ja aceito. O
    teto e um freio, nao uma cerca exata.
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
    """Bloqueia antes de enfileirar.

    Sao dois limites diferentes: cota mensal controla custo total, e
    concorrencia impede que um unico usuario ocupe todos os workers.
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
    """Carrega um projeto garantindo que pertence a quem chamou.

    404 e nao 403 de proposito: responder 403 revelaria que o id existe.
    """
    project = await session.get(Project, project_id)

    if project is None or project.owner_id != principal.id:
        raise NotFoundError("Projeto nao encontrado.")

    return project
