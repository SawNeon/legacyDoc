"""Testes de API: autenticacao, isolamento entre usuarios, cotas e jobs."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from legacydoc_core.models import Document, Job, User
from sqlalchemy import select

REPO = "https://github.com/exemplo/projeto.git"


async def _register(client: AsyncClient, *, plan: str = "free") -> tuple[dict[str, str], str]:
    email = f"u-{uuid.uuid4().hex[:10]}@exemplo.com"

    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": "senha-bem-longa-123"}
    )
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _promote(session, email: str, plan: str) -> None:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    user.plan_tier = plan
    await session.commit()


# ------------------------------------------------------------------- auth


async def test_health_is_public(client: AsyncClient):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_register_then_me(client: AsyncClient):
    headers, email = await _register(client)

    response = await client.get("/v1/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == email
    assert body["plan"]["tier"] == "free"


async def test_duplicate_email_conflicts(client: AsyncClient):
    email = f"dup-{uuid.uuid4().hex[:8]}@exemplo.com"
    payload = {"email": email, "password": "senha-bem-longa-123"}

    assert (await client.post("/v1/auth/register", json=payload)).status_code == 201

    response = await client.post("/v1/auth/register", json=payload)

    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


async def test_weak_password_is_rejected(client: AsyncClient):
    response = await client.post(
        "/v1/auth/register",
        json={"email": "curto@exemplo.com", "password": "123"},
    )

    assert response.status_code == 422


async def test_all_numeric_password_is_rejected(client: AsyncClient):
    response = await client.post(
        "/v1/auth/register",
        json={"email": "numerico@exemplo.com", "password": "12345678901234"},
    )

    assert response.status_code == 422


async def test_login_failure_does_not_reveal_whether_email_exists(client: AsyncClient):
    _, email = await _register(client)

    wrong_password = await client.post(
        "/v1/auth/login", json={"email": email, "password": "senha-errada-123"}
    )
    unknown_email = await client.post(
        "/v1/auth/login",
        json={"email": "ninguem@exemplo.com", "password": "senha-errada-123"},
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["message"] == unknown_email.json()["message"]


async def test_protected_route_requires_credentials(client: AsyncClient):
    response = await client.get("/v1/auth/me")

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


async def test_garbage_token_is_rejected(client: AsyncClient):
    response = await client.get("/v1/auth/me", headers={"Authorization": "Bearer nao-e-um-token"})

    assert response.status_code == 401


# ------------------------------------------------------------ chaves de API


async def test_api_key_authenticates_and_is_shown_only_once(client: AsyncClient):
    """The VS Code extension path: a credential that does not expire daily."""
    headers, _ = await _register(client)

    created = await client.post("/v1/auth/api-keys", json={"name": "vscode"}, headers=headers)
    assert created.status_code == 201

    plaintext = created.json()["api_key"]
    assert plaintext.startswith("ldk_")

    with_key = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert with_key.status_code == 200

    listed = await client.get("/v1/auth/api-keys", headers=headers)
    assert listed.status_code == 200
    assert "api_key" not in listed.json()[0], "the plaintext must never be recoverable"


async def test_revoked_api_key_stops_working(client: AsyncClient):
    headers, _ = await _register(client)

    created = await client.post("/v1/auth/api-keys", json={"name": "ci"}, headers=headers)
    plaintext = created.json()["api_key"]
    key_id = created.json()["id"]

    revoked = await client.delete(f"/v1/auth/api-keys/{key_id}", headers=headers)
    assert revoked.status_code == 204

    response = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {plaintext}"})
    assert response.status_code == 401


async def test_user_cannot_revoke_another_users_key(client: AsyncClient):
    owner_headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    created = await client.post("/v1/auth/api-keys", json={"name": "minha"}, headers=owner_headers)
    key_id = created.json()["id"]

    response = await client.delete(f"/v1/auth/api-keys/{key_id}", headers=other_headers)

    assert response.status_code == 404


# --------------------------------------------------------------- projetos


async def test_project_is_scoped_to_owner(client: AsyncClient):
    """v1's central leak: every user's data visible to any signed-in account."""
    owner_headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    created = await client.post("/v1/projects", json={"name": "Meu projeto"}, headers=owner_headers)
    assert created.status_code == 201
    project_id = created.json()["id"]

    assert (
        await client.get(f"/v1/projects/{project_id}", headers=other_headers)
    ).status_code == 404
    assert (await client.get("/v1/projects", headers=other_headers)).json() == []
    assert len((await client.get("/v1/projects", headers=owner_headers)).json()) == 1


async def test_project_rejects_non_https_repo_url(client: AsyncClient):
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/projects",
        json={"name": "Local", "repo_url": "file:///etc/passwd"},
        headers=headers,
    )

    assert response.status_code == 422


# --------------------------------------------------------------- contexto


async def test_context_api_requires_paid_plan(client: AsyncClient, session):
    headers, email = await _register(client)

    project_id = (await client.post("/v1/projects", json={"name": "Ctx"}, headers=headers)).json()[
        "id"
    ]

    payload = {"title": "Glossario", "content": "SKU e o codigo do produto."}

    free_attempt = await client.post(
        f"/v1/projects/{project_id}/context", json=payload, headers=headers
    )
    assert free_attempt.status_code == 402
    assert free_attempt.json()["error"] == "quota_exceeded"

    await _promote(session, email, "pro")

    paid_attempt = await client.post(
        f"/v1/projects/{project_id}/context", json=payload, headers=headers
    )
    assert paid_attempt.status_code == 201
    assert paid_attempt.json()["title"] == "Glossario"


async def test_context_globs_round_trip(client: AsyncClient, session):
    headers, email = await _register(client)
    await _promote(session, email, "pro")

    project_id = (await client.post("/v1/projects", json={"name": "Ctx2"}, headers=headers)).json()[
        "id"
    ]

    response = await client.post(
        f"/v1/projects/{project_id}/context",
        json={
            "kind": "convention",
            "title": "Camada de auth",
            "content": "Tokens sempre via header.",
            "path_globs": ["src/auth/**"],
            "tags": ["seguranca"],
            "weight": 300,
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["path_globs"] == ["src/auth/**"]
    assert body["weight"] == 300


# ------------------------------------------------------------------- jobs


async def test_create_job_returns_202_without_processing(client: AsyncClient, session):
    """A API responde na hora; quem processa e o worker."""
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs",
        json={"job_type": "document_snippet", "path": "app.py", "content": "def f(): pass"},
        headers=headers,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["progress_percent"] == 0

    queued = (await session.execute(select(Job))).scalars().all()
    assert len(queued) == 1
    assert queued[0].params["path"] == "app.py"


async def test_snippet_job_rejects_unsupported_extension(client: AsyncClient):
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs",
        json={"job_type": "document_snippet", "path": "leia.txt", "content": "oi"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_repository_job_rejects_disallowed_host(client: AsyncClient):
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs",
        json={"job_type": "document_repository", "repo_url": "https://evil.example.com/x.git"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_free_plan_file_limit_is_enforced(client: AsyncClient):
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs",
        json={
            "job_type": "document_repository",
            "repo_url": REPO,
            "paths": [f"src/f{index}.py" for index in range(10)],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "3 arquivos" in response.json()["message"]


async def test_concurrency_limit_blocks_second_job_on_free_plan(client: AsyncClient):
    headers, _ = await _register(client)
    payload = {"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"}

    assert (await client.post("/v1/jobs", json=payload, headers=headers)).status_code == 202

    second = await client.post("/v1/jobs", json=payload, headers=headers)

    assert second.status_code == 402
    assert second.json()["error"] == "quota_exceeded"


async def test_webhook_requires_paid_plan(client: AsyncClient, session):
    headers, email = await _register(client)
    payload = {
        "job_type": "document_snippet",
        "path": "a.py",
        "content": "def f(): pass",
        "webhook_url": "https://exemplo.com/hook",
    }

    assert (await client.post("/v1/jobs", json=payload, headers=headers)).status_code == 402

    await _promote(session, email, "pro")

    assert (await client.post("/v1/jobs", json=payload, headers=headers)).status_code == 202


async def test_paid_plan_gets_higher_queue_priority(client: AsyncClient, session):
    headers, email = await _register(client)
    await _promote(session, email, "pro")

    await client.post(
        "/v1/jobs",
        json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
        headers=headers,
    )

    job = (await session.execute(select(Job))).scalars().first()
    assert job.priority == 50, "the Pro plan must be served before Free"


async def test_job_is_not_visible_to_another_user(client: AsyncClient):
    owner_headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    job_id = (
        await client.post(
            "/v1/jobs",
            json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
            headers=owner_headers,
        )
    ).json()["id"]

    assert (await client.get(f"/v1/jobs/{job_id}", headers=other_headers)).status_code == 404
    assert (await client.get(f"/v1/jobs/{job_id}", headers=owner_headers)).status_code == 200


async def test_cancel_queued_job(client: AsyncClient):
    headers, _ = await _register(client)

    job_id = (
        await client.post(
            "/v1/jobs",
            json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
            headers=headers,
        )
    ).json()["id"]

    response = await client.delete(f"/v1/jobs/{job_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


# -------------------------------------------------------------- documentos


async def _seed_document(session, client, headers) -> tuple[str, str]:
    job_id = (
        await client.post(
            "/v1/jobs",
            json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
            headers=headers,
        )
    ).json()["id"]

    job = await session.get(Job, uuid.UUID(job_id))

    document = Document(
        job_id=job.id,
        user_id=job.user_id,
        path="src/app.py",
        language="python",
        content_sha256="a" * 64,
        summary="Resumo do arquivo.",
        symbols=[
            {
                "name": "f",
                "kind": "function",
                "signature": "def f()",
                "language": "python",
                "line_start": 1,
                "line_end": 1,
                "summary": "Nao faz nada.",
                "description": "Funcao vazia usada como placeholder.",
                "parameters": [],
                "raises": [],
                "side_effects": [],
            }
        ],
    )
    session.add(document)
    await session.commit()

    return job_id, str(document.id)


async def test_document_export_is_authenticated(client: AsyncClient, session):
    """v1 served PDFs from a public path with predictable names."""
    headers, _ = await _register(client)
    _, document_id = await _seed_document(session, client, headers)

    anonymous = await client.get(f"/v1/documents/{document_id}/export?format=markdown")
    assert anonymous.status_code == 401

    authorized = await client.get(
        f"/v1/documents/{document_id}/export?format=markdown", headers=headers
    )
    assert authorized.status_code == 200
    assert b"src/app.py" in authorized.content
    assert "attachment" in authorized.headers["content-disposition"]


async def test_document_export_denied_to_other_user(client: AsyncClient, session):
    owner_headers, _ = await _register(client)
    other_headers, _ = await _register(client)

    _, document_id = await _seed_document(session, client, owner_headers)

    response = await client.get(
        f"/v1/documents/{document_id}/export?format=pdf", headers=other_headers
    )

    assert response.status_code == 404


async def test_document_export_supports_all_formats(client: AsyncClient, session):
    headers, _ = await _register(client)
    _, document_id = await _seed_document(session, client, headers)

    for export_format, expected_prefix in (
        ("markdown", b"#"),
        ("json", b"{"),
        ("pdf", b"%PDF"),
    ):
        response = await client.get(
            f"/v1/documents/{document_id}/export?format={export_format}", headers=headers
        )
        assert response.status_code == 200, export_format
        assert response.content.startswith(expected_prefix), export_format


async def test_invalid_export_format_is_rejected(client: AsyncClient, session):
    headers, _ = await _register(client)
    _, document_id = await _seed_document(session, client, headers)

    response = await client.get(f"/v1/documents/{document_id}/export?format=docx", headers=headers)

    assert response.status_code == 422


# ------------------------------------------------------------------- meta


async def test_languages_endpoint_lists_many_languages(client: AsyncClient):
    response = await client.get("/v1/meta/languages")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"python", "cpp", "go", "typescript", "rust", "java"} <= names


async def test_plans_endpoint_exposes_feature_gating(client: AsyncClient):
    response = await client.get("/v1/meta/plans")

    plans = {item["tier"]: item for item in response.json()}

    assert "improvement_findings" not in plans["free"]["features"]
    assert "improvement_findings" in plans["pro"]["features"]


def _build_zip_bytes(entradas: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in entradas.items():
            zf.writestr(nome, conteudo)

    return buffer.getvalue()


async def test_zip_upload_enqueues_job(client: AsyncClient, session):
    headers, _ = await _register(client)
    conteudo = _build_zip_bytes({"src/app.py": b"def f():\n    return 1\n"})

    response = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("projeto.zip", conteudo, "application/zip")},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["job_type"] == "document_archive"
    assert body["status"] == "queued"

    job = (await session.execute(select(Job))).scalars().one()
    assert job.params["original_filename"] == "projeto.zip"
    assert job.params["archive_path"].endswith(".zip")


async def test_upload_requires_authentication(client: AsyncClient):
    response = await client.post(
        "/v1/jobs/upload",
        files={"file": ("x.zip", _build_zip_bytes({"a.py": b"x=1"}), "application/zip")},
    )

    assert response.status_code == 401


async def test_upload_rejects_non_zip_content(client: AsyncClient):
    """The content type comes from the client; the bytes decide."""
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("falso.zip", b"%PDF-1.4 nem de longe um zip", "application/zip")},
    )

    assert response.status_code == 422
    assert "nao e um .zip" in response.json()["message"]


async def test_upload_rejects_wrong_extension(client: AsyncClient):
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("codigo.tar.gz", _build_zip_bytes({"a.py": b"x=1"}), "application/gzip")},
    )

    assert response.status_code == 422


async def test_upload_rejects_empty_file(client: AsyncClient):
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("vazio.zip", b"", "application/zip")},
    )

    assert response.status_code == 422


async def test_upload_respects_concurrency_limit(client: AsyncClient):
    headers, _ = await _register(client)
    conteudo = _build_zip_bytes({"a.py": b"x = 1\n"})

    primeiro = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("a.zip", conteudo, "application/zip")},
    )
    assert primeiro.status_code == 202

    segundo = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("b.zip", conteudo, "application/zip")},
    )

    assert segundo.status_code == 402, "the Free plan allows one concurrent job"


async def test_upload_on_free_plan_is_capped_to_the_cheapest_depth(client: AsyncClient, session):
    """Asking beyond the plan is reduced, not refused.

    A client that always sends the deepest option keeps working on every plan,
    and the stored job says what will actually be paid for.
    """
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        data={"depth": "pro"},
        files={"file": ("a.zip", _build_zip_bytes({"a.py": b"x = 1\n"}), "application/zip")},
    )

    assert response.status_code == 202
    assert response.json()["depth"] == "basic"

    job = (await session.execute(select(Job))).scalars().one()
    assert job.params["depth"] == "basic"


async def _record_spend(session, user_id, valor: float) -> None:
    """Simulate LLM spend already recorded in the current month."""
    from legacydoc_core.models import UsageRecord

    session.add(
        UsageRecord(
            user_id=user_id,
            agent="writer",
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=valor,
        )
    )
    await session.commit()


async def _user_id_for(session, email: str):
    return (await session.execute(select(User).where(User.email == email))).scalar_one().id


async def test_monthly_spend_is_reported_in_me(client: AsyncClient, session):
    headers, email = await _register(client)
    await _record_spend(session, await _user_id_for(session, email), 0.12)

    body = (await client.get("/v1/auth/me", headers=headers)).json()

    assert abs(body["spent_this_month_usd"] - 0.12) < 1e-6
    assert body["plan"]["monthly_cost_limit_usd"] == 0.50


async def test_user_blocked_when_cost_ceiling_reached(client: AsyncClient, session):
    """A job-count quota protects nothing: the bill is in dollars."""
    headers, email = await _register(client)
    await _record_spend(session, await _user_id_for(session, email), 0.60)  # acima de US$ 0,50

    response = await client.post(
        "/v1/jobs",
        json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
        headers=headers,
    )

    assert response.status_code == 402
    body = response.json()
    assert body["error"] == "quota_exceeded"
    assert body["details"]["scope"] == "user"
    assert body["details"]["limit_usd"] == 0.50


async def test_job_accepted_below_cost_ceiling(client: AsyncClient, session):
    headers, email = await _register(client)
    await _record_spend(session, await _user_id_for(session, email), 0.10)

    response = await client.post(
        "/v1/jobs",
        json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
        headers=headers,
    )

    assert response.status_code == 202


async def test_global_budget_blocks_every_user(client: AsyncClient, session, settings):
    """Last line of defense for the card: many accounts within their own
    limits can still add up beyond what the operator can pay."""
    outro_headers, outro_email = await _register(client)
    await _record_spend(
        session,
        await _user_id_for(session, outro_email),
        settings.global_monthly_budget_usd + 1,
    )

    # Fresh user with no spend of their own.
    headers, _ = await _register(client)

    response = await client.post(
        "/v1/jobs",
        json={"job_type": "document_snippet", "path": "a.py", "content": "def f(): pass"},
        headers=headers,
    )

    assert response.status_code == 402
    assert response.json()["details"]["scope"] == "global"


async def test_cost_ceiling_also_applies_to_upload(client: AsyncClient, session):
    headers, email = await _register(client)
    await _record_spend(session, await _user_id_for(session, email), 0.60)

    response = await client.post(
        "/v1/jobs/upload",
        headers=headers,
        files={"file": ("a.zip", _build_zip_bytes({"a.py": b"x = 1\n"}), "application/zip")},
    )

    assert response.status_code == 402, "upload must not bypass the cost ceiling"


async def _attempt_login(client: AsyncClient, email: str, senha: str):
    return await client.post("/v1/auth/login", json={"email": email, "password": senha})


async def test_account_locks_after_repeated_failures(client: AsyncClient):
    """Brute force against the account, rotating IP on every attempt."""
    from legacydoc_core.security import MAX_FAILED_LOGINS

    _, email = await _register(client)

    for _ in range(MAX_FAILED_LOGINS):
        assert (await _attempt_login(client, email, "senha-errada-123")).status_code == 401

    # Agora nem a senha CORRETA passa.
    resposta = await _attempt_login(client, email, "senha-bem-longa-123")

    assert resposta.status_code == 401
    assert "bloquead" in resposta.json()["message"].lower()


async def test_successful_login_resets_attempt_counter(client: AsyncClient):
    _, email = await _register(client)

    for _ in range(3):
        await _attempt_login(client, email, "senha-errada-123")

    assert (await _attempt_login(client, email, "senha-bem-longa-123")).status_code == 200

    # Counter reset: three more failures do not lock.
    for _ in range(3):
        await _attempt_login(client, email, "senha-errada-123")

    assert (await _attempt_login(client, email, "senha-bem-longa-123")).status_code == 200


async def test_lockout_does_not_reveal_email_existence(client: AsyncClient):
    """The attempt counter must not become an account enumerator."""
    _, email = await _register(client)

    real = await _attempt_login(client, email, "senha-errada-123")
    inexistente = await _attempt_login(client, "ninguem@exemplo.com", "senha-errada-123")

    assert real.status_code == inexistente.status_code == 401
    assert real.json()["message"] == inexistente.json()["message"]


async def test_full_password_reset_flow(client: AsyncClient, session, caplog):
    """What the front screen promised and never actually did."""
    import logging
    import re

    _, email = await _register(client)

    with caplog.at_level(logging.WARNING, logger="legacydoc_core.email"):
        pedido = await client.post("/v1/auth/password-reset/request", json={"email": email})

    assert pedido.status_code == 202

    # The console backend publishes the link to the log.
    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text)
    assert token, f"o link precisa chegar ao usuario; log: {caplog.text[:300]}"

    confirmacao = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": token.group(1), "new_password": "nova-senha-forte-9"},
    )

    assert confirmacao.status_code == 200
    assert "access_token" in confirmacao.json()

    assert (await _attempt_login(client, email, "nova-senha-forte-9")).status_code == 200
    assert (await _attempt_login(client, email, "senha-bem-longa-123")).status_code == 401


async def test_reset_request_for_unknown_email_responds_identically(client: AsyncClient):
    """Must not become a checker for who has an account."""
    _, email = await _register(client)

    existente = await client.post("/v1/auth/password-reset/request", json={"email": email})
    inexistente = await client.post(
        "/v1/auth/password-reset/request", json={"email": "ninguem@exemplo.com"}
    )

    assert existente.status_code == inexistente.status_code == 202
    assert existente.json() == inexistente.json()


async def test_reset_token_is_single_use(client: AsyncClient, caplog):
    import logging
    import re

    _, email = await _register(client)

    with caplog.at_level(logging.WARNING, logger="legacydoc_core.email"):
        await client.post("/v1/auth/password-reset/request", json={"email": email})

    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text).group(1)
    corpo = {"token": token, "new_password": "primeira-senha-9"}

    assert (await client.post("/v1/auth/password-reset/confirm", json=corpo)).status_code == 200

    segunda = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "segunda-senha-9"},
    )

    assert segunda.status_code == 401, "a spent token must not work again"


async def test_invalid_reset_token_is_rejected(client: AsyncClient):
    resposta = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": "token-falso-que-nao-existe-mesmo", "new_password": "outra-senha-9"},
    )

    assert resposta.status_code == 401


async def test_reset_requires_strong_password(client: AsyncClient, caplog):
    import logging
    import re

    _, email = await _register(client)

    with caplog.at_level(logging.WARNING, logger="legacydoc_core.email"):
        await client.post("/v1/auth/password-reset/request", json={"email": email})

    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text).group(1)

    resposta = await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "123"},
    )

    assert resposta.status_code == 422


async def test_reset_unlocks_a_locked_account(client: AsyncClient, caplog):
    """Proving email access must clear the lock the attack itself caused."""
    import logging
    import re

    from legacydoc_core.security import MAX_FAILED_LOGINS

    _, email = await _register(client)

    for _ in range(MAX_FAILED_LOGINS):
        await _attempt_login(client, email, "senha-errada-123")

    assert (await _attempt_login(client, email, "senha-bem-longa-123")).status_code == 401

    with caplog.at_level(logging.WARNING, logger="legacydoc_core.email"):
        await client.post("/v1/auth/password-reset/request", json={"email": email})

    token = re.search(r"token=([A-Za-z0-9_\-]+)", caplog.text).group(1)
    await client.post(
        "/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "senha-recuperada-9"},
    )

    assert (await _attempt_login(client, email, "senha-recuperada-9")).status_code == 200
