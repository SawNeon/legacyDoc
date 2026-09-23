"""Painel de contas: quem entra, o que vê e o que fica registrado.

O painel é uma porta com privilégio, então a maior parte destes testes é sobre
quem NÃO passa por ela.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from legacydoc_core.models import AdminAction, User
from sqlalchemy import select


async def _register(client: AsyncClient) -> tuple[dict[str, str], str]:
    email = f"a-{uuid.uuid4().hex[:10]}@exemplo.com"

    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": "senha-bem-longa-123"}
    )
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _promote(session, email: str) -> None:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_admin = True
    await session.commit()


async def _id_of(session, email: str) -> uuid.UUID:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    return user.id


# ---------------------------------------------------------------- a porta


async def test_common_account_cannot_see_the_panel(client: AsyncClient):
    """404 e nao 403: 403 confirmaria que existe um painel neste caminho."""
    headers, _ = await _register(client)

    for caminho in ("/v1/admin/accounts", "/v1/admin/audit"):
        assert (await client.get(caminho, headers=headers)).status_code == 404


async def test_the_panel_needs_credentials(client: AsyncClient):
    assert (await client.get("/v1/admin/accounts")).status_code == 401


async def test_an_api_key_never_opens_the_panel(client: AsyncClient, session):
    """Chave é credencial longa, guardada em CI e no editor.

    Aceitá-la aqui significaria que um vazamento de chave entrega o painel
    junto, e chave não expira como sessão.
    """
    headers, email = await _register(client)
    await _promote(session, email)

    plaintext = (
        await client.post("/v1/auth/api-keys", json={"name": "ci"}, headers=headers)
    ).json()["api_key"]

    com_chave = await client.get(
        "/v1/admin/accounts", headers={"Authorization": f"Bearer {plaintext}"}
    )
    com_sessao = await client.get("/v1/admin/accounts", headers=headers)

    assert com_chave.status_code == 404
    assert com_sessao.status_code == 200


# ---------------------------------------------------------------- a lista


async def test_the_panel_lists_accounts_with_what_decides_an_action(client: AsyncClient, session):
    headers, email = await _register(client)
    await _promote(session, email)
    await _register(client)

    corpo = (await client.get("/v1/admin/accounts", headers=headers)).json()

    assert corpo["total"] == 2

    conta = corpo["items"][0]
    for campo in (
        "email",
        "plan_tier",
        "spent_this_month_usd",
        "cost_limit_usd",
        "jobs_this_month",
        "is_active",
    ):
        assert campo in conta


async def test_the_panel_never_exposes_document_content(client: AsyncClient, session):
    """A regra que molda o painel inteiro.

    O produto processa código-fonte de terceiros. Um painel que abre a
    documentação de um cliente torna verdadeira a frase "a equipe lê o código
    dos clientes", que passaria a ser obrigatória na política de privacidade.
    """
    headers, email = await _register(client)
    await _promote(session, email)

    corpo = (await client.get("/v1/admin/accounts", headers=headers)).text

    for vazamento in ("symbols", "summary", "content", "path"):
        assert vazamento not in corpo


async def test_search_narrows_by_email(client: AsyncClient, session):
    headers, email = await _register(client)
    await _promote(session, email)
    _, outro = await _register(client)

    achados = (
        await client.get(f"/v1/admin/accounts?search={outro.split('@')[0]}", headers=headers)
    ).json()

    assert [item["email"] for item in achados["items"]] == [outro]


# ----------------------------------------------------------- troca de plano


async def test_changing_a_plan_records_who_did_it_and_why(client: AsyncClient, session):
    headers, admin_email = await _register(client)
    await _promote(session, admin_email)
    _, alvo = await _register(client)
    alvo_id = await _id_of(session, alvo)

    resposta = await client.patch(
        f"/v1/admin/accounts/{alvo_id}/plan",
        json={"plan": "pro", "reason": "Liberado para a banca do TCC avaliar."},
        headers=headers,
    )

    assert resposta.status_code == 200
    assert resposta.json()["plan_tier"] == "pro"

    registro = (await session.execute(select(AdminAction))).scalars().one()

    assert registro.actor_email == admin_email
    assert registro.target_email == alvo
    assert (registro.value_before, registro.value_after) == ("free", "pro")
    assert "banca" in registro.reason


async def test_a_plan_change_without_a_reason_is_refused(client: AsyncClient, session):
    """Uma troca sem motivo escrito é a que ninguém explica três meses depois."""
    headers, email = await _register(client)
    await _promote(session, email)
    _, alvo = await _register(client)
    alvo_id = await _id_of(session, alvo)

    resposta = await client.patch(
        f"/v1/admin/accounts/{alvo_id}/plan",
        json={"plan": "pro", "reason": "x"},
        headers=headers,
    )

    assert resposta.status_code == 422
    assert (await session.execute(select(AdminAction))).scalars().all() == []


async def test_an_unknown_plan_is_refused(client: AsyncClient, session):
    headers, email = await _register(client)
    await _promote(session, email)
    _, alvo = await _register(client)
    alvo_id = await _id_of(session, alvo)

    resposta = await client.patch(
        f"/v1/admin/accounts/{alvo_id}/plan",
        json={"plan": "enterprise", "reason": "tentativa de plano inexistente"},
        headers=headers,
    )

    assert resposta.status_code == 422


# -------------------------------------------------------------- ativacao


async def test_disabling_an_account_blocks_its_session(client: AsyncClient, session):
    headers, admin_email = await _register(client)
    await _promote(session, admin_email)
    alvo_headers, alvo = await _register(client)
    alvo_id = await _id_of(session, alvo)

    assert (await client.get("/v1/auth/me", headers=alvo_headers)).status_code == 200

    await client.patch(
        f"/v1/admin/accounts/{alvo_id}/status",
        json={"is_active": False, "reason": "Abuso de cota confirmado."},
        headers=headers,
    )

    assert (await client.get("/v1/auth/me", headers=alvo_headers)).status_code == 401


async def test_an_admin_cannot_disable_themselves(client: AsyncClient, session):
    """Caminho sem volta pela interface: a sessão seguinte não passaria na porta."""
    headers, email = await _register(client)
    await _promote(session, email)
    proprio_id = await _id_of(session, email)

    resposta = await client.patch(
        f"/v1/admin/accounts/{proprio_id}/status",
        json={"is_active": False, "reason": "desativando a mim mesmo por engano"},
        headers=headers,
    )

    assert resposta.status_code == 422
    assert (await client.get("/v1/admin/accounts", headers=headers)).status_code == 200


async def test_reactivating_clears_the_login_lockout(client: AsyncClient, session):
    """Quem foi reativado à mão não deve esbarrar num bloqueio antigo."""
    headers, admin_email = await _register(client)
    await _promote(session, admin_email)
    _, alvo = await _register(client)
    alvo_id = await _id_of(session, alvo)

    usuario = (await session.execute(select(User).where(User.email == alvo))).scalar_one()
    usuario.is_active = False
    usuario.failed_login_attempts = 5
    await session.commit()

    await client.patch(
        f"/v1/admin/accounts/{alvo_id}/status",
        json={"is_active": True, "reason": "Falso positivo, reativando."},
        headers=headers,
    )

    await session.refresh(usuario)

    assert usuario.is_active is True
    assert usuario.failed_login_attempts == 0
    assert usuario.locked_until is None


async def test_acting_on_an_unknown_account_is_a_not_found(client: AsyncClient, session):
    headers, email = await _register(client)
    await _promote(session, email)

    resposta = await client.patch(
        f"/v1/admin/accounts/{uuid.uuid4()}/plan",
        json={"plan": "pro", "reason": "conta que nao existe"},
        headers=headers,
    )

    assert resposta.status_code == 404


# ---------------------------------------------------------------- auditoria


async def test_the_audit_survives_the_account_being_deleted(client: AsyncClient, session):
    """Por isso os e-mails são copiados, e a chave estrangeira é SET NULL.

    Um registro que some junto com a conta não serve de registro.
    """
    headers, admin_email = await _register(client)
    await _promote(session, admin_email)
    _, alvo = await _register(client)
    alvo_id = await _id_of(session, alvo)

    await client.patch(
        f"/v1/admin/accounts/{alvo_id}/plan",
        json={"plan": "team", "reason": "Conta de demonstracao para a banca."},
        headers=headers,
    )

    usuario = (await session.execute(select(User).where(User.email == alvo))).scalar_one()
    await session.delete(usuario)
    await session.commit()

    registro = (await session.execute(select(AdminAction))).scalars().one()

    assert registro.target_user_id is None
    assert registro.target_email == alvo
    assert registro.value_after == "team"


async def test_the_audit_is_only_visible_to_admins(client: AsyncClient, session):
    headers, admin_email = await _register(client)
    await _promote(session, admin_email)
    comum_headers, _ = await _register(client)

    assert (await client.get("/v1/admin/audit", headers=headers)).status_code == 200
    assert (await client.get("/v1/admin/audit", headers=comum_headers)).status_code == 404


async def test_me_says_whether_the_account_opens_the_panel(client: AsyncClient, session):
    """O front decide por aqui se mostra o acesso.

    Esconder o link nao e controle de acesso: o painel recusa por conta propria
    quem nao for administrador. Isto existe para nao oferecer uma porta que a
    pessoa vai bater e receber 404.
    """
    headers, email = await _register(client)

    assert (await client.get("/v1/auth/me", headers=headers)).json()["is_admin"] is False

    await _promote(session, email)

    assert (await client.get("/v1/auth/me", headers=headers)).json()["is_admin"] is True
