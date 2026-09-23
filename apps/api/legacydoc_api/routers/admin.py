"""Painel de contas.

Tres regras moldam este arquivo:

Mostra metadado, nunca conteudo. O produto processa codigo-fonte de terceiros,
e um painel que abre a documentacao de um cliente torna verdadeira a frase "a
equipe le o codigo dos clientes". Restringir por desenho custa nada agora e e
impossivel de desfazer depois.

Toda acao e registrada. Sem isso, daqui a tres meses ninguem sabe por que uma
conta esta no plano Team. E quando a cobranca entrar, o gateway passara a mandar
o plano pelo webhook: uma troca feita na mao sem registro vira conflito
silencioso entre o que a pessoa pagou e o que ela tem.

Promover administrador nao e rota. Isso acontece so pela linha de comando, para
que ganhar privilegio nao seja algo que se alcance por HTTP.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from legacydoc_core.db import get_db
from legacydoc_core.errors import NotFoundError, ValidationError
from legacydoc_core.models import AdminAction, Document, Job, JobStatus, UsageRecord, User
from legacydoc_core.plans import PlanTier, get_plan
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_api.deps import Principal, require_admin
from legacydoc_api.schemas import (
    AdminAccountList,
    AdminAccountResponse,
    AdminActionResponse,
    AdminPlanChangeRequest,
    AdminStatusChangeRequest,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])

ACAO_PLANO = "plan_changed"
ACAO_ATIVACAO = "account_enabled"
ACAO_DESATIVACAO = "account_disabled"


def _inicio_do_mes() -> datetime:
    agora = datetime.now(UTC)
    return datetime(agora.year, agora.month, 1, tzinfo=UTC)


async def _metricas_por_conta(session: AsyncSession, ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Uma consulta agregada por metrica, e nao uma por conta.

    Buscar gasto e contagem dentro do laco da listagem seria uma ida ao banco
    por linha; com cem contas na tela isso vira trezentas consultas.
    """
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

    # A contagem do mes e separada da data do ultimo job: uma olha so o mes
    # corrente, a outra precisa enxergar o historico inteiro.
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


def _para_resposta(usuario: User, metricas: dict) -> AdminAccountResponse:
    plano = get_plan(usuario.plan_tier)

    return AdminAccountResponse(
        id=usuario.id,
        email=usuario.email,
        display_name=usuario.display_name,
        plan_tier=usuario.plan_tier,
        is_active=usuario.is_active,
        is_admin=usuario.is_admin,
        created_at=usuario.created_at,
        cost_limit_usd=plano.monthly_cost_limit_usd,
        locked_until=usuario.locked_until,
        jobs_this_month=metricas["jobs_this_month"],
        spent_this_month_usd=round(metricas["spent_this_month_usd"], 4),
        documents_total=metricas["documents_total"],
        last_job_at=metricas["last_job_at"],
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

    return AdminAccountList(
        items=[_para_resposta(usuario, metricas[usuario.id]) for usuario in usuarios],
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

    return _para_resposta(usuario, metricas[usuario.id])


@router.patch("/accounts/{user_id}/status", response_model=AdminAccountResponse)
async def change_status(
    user_id: uuid.UUID,
    payload: AdminStatusChangeRequest,
    admin: Principal = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminAccountResponse:
    """Ativa ou desativa a conta.

    Desativar a propria conta e recusado: e um caminho sem volta pela interface,
    porque a sessao seguinte nao passaria mais pela porta.
    """
    usuario = await _conta_alvo(user_id, session)

    if usuario.id == admin.id and not payload.is_active:
        raise ValidationError(
            "Voce nao pode desativar a propria conta: ninguem conseguiria reativa-la pelo painel."
        )

    if usuario.is_active == payload.is_active:
        estado = "ativa" if payload.is_active else "desativada"
        raise ValidationError(f"A conta ja esta {estado}.")

    usuario.is_active = payload.is_active

    # Reativar limpa o bloqueio por tentativas: quem foi reativado a mao nao
    # deve esbarrar num bloqueio antigo na primeira tentativa de entrar.
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

    return _para_resposta(usuario, metricas[usuario.id])


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
