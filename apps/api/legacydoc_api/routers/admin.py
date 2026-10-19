"""Painel de contas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from legacydoc_core.billing import (
    RECOMMENDED_PLANS,
    RECOMMENDED_SETTINGS,
    Pricing,
    balance_for,
    grant_credit,
    load_pricing,
)
from legacydoc_core.db import get_db
from legacydoc_core.errors import NotFoundError, ValidationError
from legacydoc_core.models import (
    AdminAction,
    BillingSetting,
    Document,
    Job,
    JobStatus,
    PlanPricing,
    UsageRecord,
    User,
)
from legacydoc_core.plans import PlanTier
from legacydoc_core.settings import Settings
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.deps import Principal, get_app_settings, global_spend_this_month, require_admin
from legacydoc_api.schemas import (
    AdminAccountList,
    AdminAccountResponse,
    AdminActionResponse,
    AdminBillingResponse,
    AdminPlanChangeRequest,
    AdminStatusChangeRequest,
    BillingPlanView,
    BillingSettingsUpdate,
    CreditGrantRequest,
    CreditGrantResponse,
    PlanPricingUpdate,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

ACAO_PLANO = "plan_changed"
ACAO_ATIVACAO = "account_enabled"
ACAO_DESATIVACAO = "account_disabled"
ACTION_SETTING = "billing_setting_changed"
ACTION_PLAN_PRICING = "plan_pricing_changed"
ACTION_CREDIT = "credit_granted"


def _inicio_do_mes() -> datetime:
    agora = datetime.now(UTC)
    return datetime(agora.year, agora.month, 1, tzinfo=UTC)


async def _metricas_por_conta(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Uma consulta agregada por metrica, e nao uma por conta."""
    if not ids:
        return {}

    inicio = _inicio_do_mes()
    metricas: dict[uuid.UUID, dict] = {
        identificador: {
            "jobs_this_month": 0,
            "spent_this_month_usd": 0.0,
            "documents_total": 0,
            "last_job_at": None,
        }
        for identificador in ids
    }

    gastos = await session.execute(
        select(UsageRecord.user_id, func.coalesce(func.sum(UsageRecord.cost_usd), 0.0))
        .where(UsageRecord.user_id.in_(ids), UsageRecord.created_at >= inicio)
        .group_by(UsageRecord.user_id)
    )
    for identificador, total in gastos.all():
        metricas[identificador]["spent_this_month_usd"] = float(total)

    ultimos = await session.execute(
        select(Job.user_id, func.max(Job.created_at))
        .where(Job.user_id.in_(ids), Job.status != JobStatus.CANCELLED)
        .group_by(Job.user_id)
    )
    for identificador, ultimo in ultimos.all():
        metricas[identificador]["last_job_at"] = ultimo

    jobs_do_mes = await session.execute(
        select(Job.user_id, func.count(Job.id))
        .where(
            Job.user_id.in_(ids),
            Job.created_at >= inicio,
            Job.status != JobStatus.CANCELLED,
        )
        .group_by(Job.user_id)
    )
    for identificador, quantidade in jobs_do_mes.all():
        metricas[identificador]["jobs_this_month"] = int(quantidade)

    documentos = await session.execute(
        select(Document.user_id, func.count(Document.id))
        .where(Document.user_id.in_(ids))
        .group_by(Document.user_id)
    )
    for identificador, quantidade in documentos.all():
        metricas[identificador]["documents_total"] = int(quantidade)

    return metricas


def _para_resposta(
    usuario: User, metricas: dict, ceiling_usd: float, credits_remaining_brl: float
) -> AdminAccountResponse:

    return AdminAccountResponse(
        id=usuario.id,
        email=usuario.email,
        display_name=usuario.display_name,
        plan_tier=usuario.plan_tier,
        is_active=usuario.is_active,
        is_admin=usuario.is_admin,
        created_at=usuario.created_at,
        cost_limit_usd=round(ceiling_usd, 4),
        credits_remaining_brl=round(credits_remaining_brl, 2),
        locked_until=usuario.locked_until,
        jobs_this_month=metricas["jobs_this_month"],
        spent_this_month_usd=round(metricas["spent_this_month_usd"], 4),
        documents_total=metricas["documents_total"],
        last_job_at=metricas["last_job_at"],
    )


async def _account_view(
    session: AsyncSession, usuario: User, metricas: dict, pricing: Pricing
) -> AdminAccountResponse:
    balance = await balance_for(session, usuario.id, usuario.plan_tier, pricing)

    return _para_resposta(
        usuario, metricas, balance.plan.ceiling_usd, balance.credits_remaining_brl
    )


def _filtrar(consulta: Select, busca: str | None) -> Select:
    if not busca:
        return consulta

    return consulta.where(User.email.ilike(f"%{busca.strip()}%"))


@router.get("/accounts", response_model=AdminAccountList)
async def list_accounts(
    _: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    search: str | None = Query(default=None, description="Trecho do e-mail"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AdminAccountList:
    """Contas com o que decide uma acao: gasto contra o teto, uso e situacao."""
    total = int((await session.execute(_filtrar(select(func.count(User.id)), search))).scalar_one())

    usuarios = list(
        (
            await session.execute(
                _filtrar(select(User), search)
                .order_by(User.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    metricas = await _metricas_por_conta(session, [usuario.id for usuario in usuarios])
    pricing = await load_pricing(session)

    return AdminAccountList(
        items=[
            await _account_view(session, usuario, metricas[usuario.id], pricing)
            for usuario in usuarios
        ],
        total=total,
    )


async def _conta_alvo(user_id: uuid.UUID, session: AsyncSession) -> User:
    usuario = await session.get(User, user_id)

    if usuario is None:
        raise NotFoundError("Conta nao encontrada.")

    return usuario


def _registrar(
    session: AsyncSession,
    *,
    autor: Principal,
    alvo: User,
    acao: str,
    antes: str | None,
    depois: str | None,
    motivo: str,
) -> None:
    session.add(
        AdminAction(
            actor_id=autor.id,
            actor_email=autor.user.email,
            target_user_id=alvo.id,
            target_email=alvo.email,
            action=acao,
            value_before=antes,
            value_after=depois,
            reason=motivo.strip(),
        )
    )


@router.patch("/accounts/{user_id}/plan", response_model=AdminAccountResponse)
async def change_plan(
    user_id: uuid.UUID,
    payload: AdminPlanChangeRequest,
    admin: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminAccountResponse:
    """Troca o plano da conta, exigindo um motivo escrito."""
    try:
        destino = PlanTier(payload.plan)
    except ValueError as erro:
        aceitos = ", ".join(str(tier) for tier in PlanTier)
        raise ValidationError(f"Plano invalido. Aceitos: {aceitos}.") from erro

    usuario = await _conta_alvo(user_id, session)
    anterior = usuario.plan_tier

    if anterior == str(destino):
        raise ValidationError(f"A conta ja esta no plano {destino}.")

    usuario.plan_tier = str(destino)

    _registrar(
        session,
        autor=admin,
        alvo=usuario,
        acao=ACAO_PLANO,
        antes=anterior,
        depois=str(destino),
        motivo=payload.reason,
    )

    await session.flush()

    metricas = await _metricas_por_conta(session, [usuario.id])

    return await _account_view(session, usuario, metricas[usuario.id], await load_pricing(session))


@router.patch("/accounts/{user_id}/status", response_model=AdminAccountResponse)
async def change_status(
    user_id: uuid.UUID,
    payload: AdminStatusChangeRequest,
    admin: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminAccountResponse:
    """Ativa ou desativa a conta."""
    usuario = await _conta_alvo(user_id, session)

    if usuario.id == admin.id and not payload.is_active:
        raise ValidationError(
            "Voce nao pode desativar a propria conta: ninguem conseguiria reativa-la pelo painel."
        )

    if usuario.is_active == payload.is_active:
        estado = "ativa" if payload.is_active else "desativada"
        raise ValidationError(f"A conta ja esta {estado}.")

    usuario.is_active = payload.is_active

    if payload.is_active:
        usuario.failed_login_attempts = 0
        usuario.locked_until = None

    _registrar(
        session,
        autor=admin,
        alvo=usuario,
        acao=ACAO_ATIVACAO if payload.is_active else ACAO_DESATIVACAO,
        antes=str(not payload.is_active).lower(),
        depois=str(payload.is_active).lower(),
        motivo=payload.reason,
    )

    await session.flush()

    metricas = await _metricas_por_conta(session, [usuario.id])

    return await _account_view(session, usuario, metricas[usuario.id], await load_pricing(session))


@router.get("/audit", response_model=list[AdminActionResponse])
async def list_audit(
    _: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AdminActionResponse]:
    """Historico de acoes, da mais recente para a mais antiga."""
    registros = (
        await session.execute(
            select(AdminAction).order_by(AdminAction.created_at.desc()).limit(limit)
        )
    ).scalars()

    return [
        AdminActionResponse(
            id=registro.id,
            actor_email=registro.actor_email,
            target_email=registro.target_email,
            action=registro.action,
            value_before=registro.value_before,
            value_after=registro.value_after,
            reason=registro.reason,
            created_at=registro.created_at,
        )
        for registro in registros
    ]


def _plan_view(pricing: Pricing, tier: str) -> BillingPlanView:
    plan = pricing.plans[tier]
    margin = plan.worst_case_margin_percent
    alert_threshold = pricing.settings.min_margin_alert_percent

    return BillingPlanView(
        tier=tier,
        price_brl=plan.price_brl,
        credits_brl=plan.credits_brl,
        cost_ratio=plan.cost_ratio,
        ceiling_usd=round(plan.ceiling_usd, 4),
        worst_case_margin_percent=None if margin is None else round(margin, 1),
        typical_margin_percent=(
            None if plan.typical_margin_percent is None else round(plan.typical_margin_percent, 1)
        ),
        margin_alert=margin is not None and margin < alert_threshold,
        recommended=RECOMMENDED_PLANS[tier],
    )


async def _billing_response(session: AsyncSession, app_settings: Settings) -> AdminBillingResponse:
    pricing = await load_pricing(session)
    current = pricing.settings

    return AdminBillingResponse(
        settings={name: getattr(current, name) for name in RECOMMENDED_SETTINGS},
        recommended_settings=RECOMMENDED_SETTINGS,
        plans=[_plan_view(pricing, str(tier)) for tier in PlanTier if str(tier) in pricing.plans],
        global_spend_usd=round(await global_spend_this_month(session), 4),
        global_budget_usd=app_settings.global_monthly_budget_usd,
    )


def _record_config_change(
    session: AsyncSession,
    *,
    author: Principal,
    action: str,
    target: str,
    before: object,
    after: object,
    reason: str,
) -> None:
    session.add(
        AdminAction(
            actor_id=author.id,
            actor_email=author.user.email,
            target_user_id=None,
            target_email=target,
            action=action,
            value_before=str(before)[:120],
            value_after=str(after)[:120],
            reason=reason.strip(),
        )
    )


def _normalised_packs(prices: list[float]) -> list[float]:
    if any(price <= 0 or price > 1_000_000 for price in prices):
        raise ValidationError("Os pacotes precisam de valores positivos.")

    return sorted({round(price, 2) for price in prices})


@router.get("/billing", response_model=AdminBillingResponse)
async def get_billing(
    _: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    app_settings: Settings = Depends(get_app_settings),
) -> AdminBillingResponse:
    """Regras comerciais em vigor, com o valor recomendado ao lado de cada uma."""
    return await _billing_response(session, app_settings)


@router.patch("/billing/settings", response_model=AdminBillingResponse)
async def update_billing_settings(
    payload: BillingSettingsUpdate,
    admin: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    app_settings: Settings = Depends(get_app_settings),
) -> AdminBillingResponse:
    await load_pricing(session)
    row = await session.get(BillingSetting, 1)
    assert row is not None

    changes = payload.model_dump(exclude={"reason"}, exclude_none=True)

    if "topup_pack_prices_brl" in changes:
        changes["topup_pack_prices_brl"] = _normalised_packs(changes["topup_pack_prices_brl"])

    changed = False

    for field, new_value in changes.items():
        old_value = getattr(row, field)

        if old_value == new_value:
            continue

        setattr(row, field, new_value)
        changed = True
        _record_config_change(
            session,
            author=admin,
            action=ACTION_SETTING,
            target=f"billing:{field}",
            before=old_value,
            after=new_value,
            reason=payload.reason,
        )

    if not changed:
        raise ValidationError("Nenhum valor mudou.")

    await session.flush()

    return await _billing_response(session, app_settings)


@router.patch("/billing/plans/{tier}", response_model=AdminBillingResponse)
async def update_plan_pricing(
    tier: str,
    payload: PlanPricingUpdate,
    admin: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    app_settings: Settings = Depends(get_app_settings),
) -> AdminBillingResponse:
    if tier not in {str(item) for item in PlanTier}:
        raise NotFoundError("Plano nao encontrado.")

    await load_pricing(session)
    row = await session.get(PlanPricing, tier)
    assert row is not None

    changed = False

    for field, new_value in payload.model_dump(exclude={"reason"}, exclude_none=True).items():
        old_value = getattr(row, field)

        if old_value == new_value:
            continue

        setattr(row, field, new_value)
        changed = True
        _record_config_change(
            session,
            author=admin,
            action=ACTION_PLAN_PRICING,
            target=f"plan:{tier}:{field}",
            before=old_value,
            after=new_value,
            reason=payload.reason,
        )

    if not changed:
        raise ValidationError("Nenhum valor mudou.")

    await session.flush()

    return await _billing_response(session, app_settings)


@router.post("/accounts/{user_id}/credits", response_model=CreditGrantResponse, status_code=201)
async def add_credits(
    user_id: uuid.UUID,
    payload: CreditGrantRequest,
    admin: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> CreditGrantResponse:
    """Adiciona credito a uma conta: recarga paga (pelo valor) ou cortesia (pelo credito)."""
    if (payload.price_brl is None) == (payload.credits_brl is None):
        raise ValidationError("Informe o valor pago (price_brl) ou o credito (credits_brl), so um.")

    user = await _conta_alvo(user_id, session)
    pricing = await load_pricing(session)

    if payload.price_brl is not None:
        credits = round(payload.price_brl * pricing.settings.topup_credit_ratio, 2)
        paid: float | None = payload.price_brl
    else:
        credits = round(payload.credits_brl or 0.0, 2)
        paid = None

    grant = await grant_credit(
        session, user.id, credits_brl=credits, price_paid_brl=paid, pricing=pricing
    )

    session.add(
        AdminAction(
            actor_id=admin.id,
            actor_email=admin.user.email,
            target_user_id=user.id,
            target_email=user.email,
            action=ACTION_CREDIT,
            value_before=None,
            value_after=f"R$ {credits:.2f}",
            reason=payload.reason.strip(),
        )
    )
    await session.flush()

    metricas = await _metricas_por_conta(session, [user.id])

    return CreditGrantResponse(
        id=grant.id,
        credits_brl=credits,
        expires_at=grant.expires_at,
        account=await _account_view(session, user, metricas[user.id], pricing),
    )
