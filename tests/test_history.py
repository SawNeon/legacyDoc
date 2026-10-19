"""Exclusao de itens do historico: o job some, os documentos sao apagados e a cota nao volta."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from legacydoc_api.deps import count_jobs_this_month
from legacydoc_core.models import Document, Finding, Job, JobStatus, JobType, UsageRecord, User
from sqlalchemy import func, select

SEGREDO = "senha_do_banco = 'nao-guarde'"
SNIPPET = {"job_type": "document_snippet", "path": "a.py", "content": SEGREDO}


async def _register(client: AsyncClient) -> tuple[dict[str, str], str]:
    email = f"h-{uuid.uuid4().hex[:10]}@exemplo.com"

    response = await client.post(
        "/v1/auth/register", json={"email": email, "password": "senha-bem-longa-123"}
    )
    assert response.status_code == 201, response.text

    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


async def _user_id(session, email: str) -> uuid.UUID:
    return (await session.execute(select(User.id).where(User.email == email))).scalar_one()


async def _finished_job(
    client: AsyncClient, session, headers, status: JobStatus = JobStatus.SUCCEEDED
) -> tuple[str, str]:
    job_id = (await client.post("/v1/jobs", json=SNIPPET, headers=headers)).json()["id"]

    job = await session.get(Job, uuid.UUID(job_id))
    job.status = str(status)

    document = Document(
        job_id=job.id,
        user_id=job.user_id,
        path="src/app.py",
        language="python",
        content_sha256="a" * 64,
        summary="Resumo do arquivo.",
    )
    document.findings.append(
        Finding(category="complexity", severity="low", title="Funcao longa", detail="Detalhe.")
    )
    session.add(document)
    await session.commit()

    return job_id, str(document.id)


async def _count(session, model, *filters) -> int:
    query = select(func.count()).select_from(model).where(*filters)

    return int((await session.execute(query)).scalar_one())


async def test_deleting_removes_the_job_and_its_documents(client: AsyncClient, session):
    headers, _ = await _register(client)
    job_id, document_id = await _finished_job(client, session, headers)

    response = await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    assert response.status_code == 204
    assert (await client.get(f"/v1/jobs/{job_id}", headers=headers)).status_code == 404
    assert (await client.get("/v1/jobs", headers=headers)).json() == {"items": [], "total": 0}
    assert (await client.get("/v1/documents", headers=headers)).json() == []

    export = await client.get(
        f"/v1/documents/{document_id}/export?format=markdown", headers=headers
    )
    assert export.status_code == 404

    assert await _count(session, Document, Document.job_id == uuid.UUID(job_id)) == 0
    assert await _count(session, Finding, Finding.document_id == uuid.UUID(document_id)) == 0


async def test_failed_and_cancelled_jobs_can_be_deleted(client: AsyncClient, session):
    headers, _ = await _register(client)

    for status in (JobStatus.FAILED, JobStatus.CANCELLED):
        job_id, _ = await _finished_job(client, session, headers, status)

        response = await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

        assert response.status_code == 204, status


async def test_deleting_forgets_the_submitted_code(client: AsyncClient, session):
    """O job continua no banco por causa da cota, mas sem o codigo enviado."""
    headers, _ = await _register(client)
    job_id, _ = await _finished_job(client, session, headers)

    await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    session.expire_all()
    job = await session.get(Job, uuid.UUID(job_id))

    assert job.deleted_at is not None
    assert job.params == {}
    assert SEGREDO not in str(job.params)


async def test_job_in_progress_cannot_be_deleted(client: AsyncClient, session):
    headers, _ = await _register(client)
    job_id = (await client.post("/v1/jobs", json=SNIPPET, headers=headers)).json()["id"]

    queued = await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    assert queued.status_code == 409
    assert queued.json()["error"] == "conflict"

    job = await session.get(Job, uuid.UUID(job_id))
    job.status = str(JobStatus.RUNNING)
    await session.commit()

    running = await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    assert running.status_code == 409
    assert (await client.get(f"/v1/jobs/{job_id}", headers=headers)).status_code == 200


async def test_other_user_cannot_delete(client: AsyncClient, session):
    owner_headers, _ = await _register(client)
    other_headers, _ = await _register(client)
    job_id, _ = await _finished_job(client, session, owner_headers)

    response = await client.delete(f"/v1/jobs/{job_id}/history", headers=other_headers)

    assert response.status_code == 404
    assert (await client.get(f"/v1/jobs/{job_id}", headers=owner_headers)).status_code == 200
    assert len((await client.get("/v1/documents", headers=owner_headers)).json()) == 1


async def test_deleting_twice_is_not_found(client: AsyncClient, session):
    headers, _ = await _register(client)
    job_id, _ = await _finished_job(client, session, headers)

    assert (await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)).status_code == 204
    assert (await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)).status_code == 404


async def test_deleted_job_cannot_be_cancelled(client: AsyncClient, session):
    headers, _ = await _register(client)
    job_id, _ = await _finished_job(client, session, headers)

    await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    assert (await client.delete(f"/v1/jobs/{job_id}", headers=headers)).status_code == 404


async def test_deleted_job_still_counts_toward_the_monthly_quota(client: AsyncClient, session):
    """Senao bastaria excluir o historico para ganhar cota de novo."""
    headers, email = await _register(client)
    job_id, _ = await _finished_job(client, session, headers)
    user_id = await _user_id(session, email)

    before = await count_jobs_this_month(session, user_id)

    await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    assert before == 1
    assert await count_jobs_this_month(session, user_id) == before


async def test_deleting_removes_a_leftover_upload(client: AsyncClient, session, tmp_path):
    """Um envio cancelado na fila nunca passou pelo worker, que e quem apaga o .zip."""
    headers, email = await _register(client)
    archive = tmp_path / "envio.zip"
    archive.write_bytes(b"PK\x03\x04")

    job = Job(
        user_id=await _user_id(session, email),
        job_type=str(JobType.DOCUMENT_ARCHIVE),
        status=str(JobStatus.CANCELLED),
        params={"archive_path": str(archive), "original_filename": "envio.zip"},
    )
    session.add(job)
    await session.commit()

    response = await client.delete(f"/v1/jobs/{job.id}/history", headers=headers)

    assert response.status_code == 204
    assert not archive.exists()


async def test_deleting_requires_authentication(client: AsyncClient):
    response = await client.delete(f"/v1/jobs/{uuid.uuid4()}/history")

    assert response.status_code == 401


async def test_deleting_works_with_an_api_key(client: AsyncClient, session):
    headers, _ = await _register(client)
    key = (await client.post("/v1/auth/api-keys", json={"name": "vscode"}, headers=headers)).json()[
        "api_key"
    ]
    job_id, _ = await _finished_job(client, session, headers)

    response = await client.delete(
        f"/v1/jobs/{job_id}/history", headers={"Authorization": f"Bearer {key}"}
    )

    assert response.status_code == 204


async def test_deleting_keeps_the_recorded_spend(client: AsyncClient, session):
    headers, email = await _register(client)
    job_id, _ = await _finished_job(client, session, headers)
    session.add(
        UsageRecord(
            user_id=await _user_id(session, email),
            job_id=uuid.UUID(job_id),
            agent="writer",
            provider="openai",
            model="gpt-4o-mini",
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.25,
            latency_ms=1,
            succeeded=True,
        )
    )
    await session.commit()

    await client.delete(f"/v1/jobs/{job_id}/history", headers=headers)

    me = (await client.get("/v1/auth/me", headers=headers)).json()
    assert me["spent_this_month_usd"] == 0.25
