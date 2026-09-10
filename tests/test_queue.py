"""Testes da fila.

Ressalva: SQLite nao implementa `FOR UPDATE SKIP LOCKED`, entao aqui se exercita
o caminho de reivindicacao otimista. A garantia de exclusao mutua sob
concorrencia real depende do Postgres e precisa de teste de integracao com
container.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from legacydoc_core.models import Job, JobStatus
from legacydoc_core.queue import (
    cancel_job,
    claim_job,
    complete_job,
    count_active_jobs_for_user,
    enqueue,
    fail_job,
    heartbeat,
    reap_expired_leases,
)


def _as_aware(value: datetime) -> datetime:
    """SQLite descarta o fuso na ida e volta; no Postgres o valor volta aware."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def _add_job(session, user, *, priority: int = 100, max_attempts: int = 3) -> Job:
    job = await enqueue(
        session,
        user_id=user.id,
        job_type="document_snippet",
        params={"path": "a.py", "content": "def f(): pass"},
        priority=priority,
        max_attempts=max_attempts,
    )
    await session.commit()

    return job


async def test_claim_marks_running_and_increments_attempts(session, user):
    await _add_job(session, user)

    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    assert claimed is not None
    assert claimed.status == JobStatus.RUNNING
    assert claimed.locked_by == "w1"
    assert claimed.attempts == 1
    assert claimed.started_at is not None


async def test_claim_returns_none_when_queue_empty(session, user):
    assert await claim_job(session, worker_id="w1", lease_seconds=60) is None


async def test_job_is_claimed_only_once(session, user):
    await _add_job(session, user)

    first = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    second = await claim_job(session, worker_id="w2", lease_seconds=60)
    await session.commit()

    assert first is not None
    assert second is None, "o mesmo job nao pode ser entregue a dois workers"


async def test_priority_orders_the_queue(session, user):
    low = await _add_job(session, user, priority=100)
    high = await _add_job(session, user, priority=10)

    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    assert claimed is not None
    assert claimed.id == high.id, "planos pagos precisam ser atendidos primeiro"
    assert claimed.id != low.id


async def test_heartbeat_renews_lease_and_reports_progress(session, user):
    await _add_job(session, user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    alive = await heartbeat(
        session,
        job_id=claimed.id,
        worker_id="w1",
        lease_seconds=120,
        progress_percent=42,
        progress_message="documentando",
    )
    await session.commit()
    await session.refresh(claimed)

    assert alive is True
    assert claimed.progress_percent == 42
    assert claimed.progress_message == "documentando"


async def test_heartbeat_from_wrong_worker_is_rejected(session, user):
    """Impede que um worker que perdeu o lease continue e duplique trabalho."""
    await _add_job(session, user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    alive = await heartbeat(session, job_id=claimed.id, worker_id="w2", lease_seconds=60)
    await session.commit()

    assert alive is False


async def test_fail_requeues_with_backoff_while_attempts_remain(session, user):
    await _add_job(session, user, max_attempts=3)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    requeued = await fail_job(
        session,
        job_id=claimed.id,
        worker_id="w1",
        error_code="provider_error",
        error_message="provedor fora do ar",
    )
    await session.commit()
    await session.refresh(claimed)

    assert requeued is True
    assert claimed.status == JobStatus.QUEUED
    assert claimed.locked_by is None
    assert _as_aware(claimed.scheduled_at) > datetime.now(UTC), (
        "o backoff precisa adiar a proxima tentativa"
    )


async def test_fail_is_final_when_attempts_exhausted(session, user):
    await _add_job(session, user, max_attempts=1)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    requeued = await fail_job(
        session,
        job_id=claimed.id,
        worker_id="w1",
        error_code="provider_error",
        error_message="falhou de novo",
    )
    await session.commit()
    await session.refresh(claimed)

    assert requeued is False
    assert claimed.status == JobStatus.FAILED
    assert claimed.finished_at is not None


async def test_domain_errors_are_not_retried(session, user):
    """Repo invalido nao melhora com nova tentativa."""
    await _add_job(session, user, max_attempts=3)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    requeued = await fail_job(
        session,
        job_id=claimed.id,
        worker_id="w1",
        error_code="validation_error",
        error_message="repositorio invalido",
        retryable=False,
    )
    await session.commit()
    await session.refresh(claimed)

    assert requeued is False
    assert claimed.status == JobStatus.FAILED


async def test_reaper_requeues_job_whose_worker_died(session, user):
    """O caso que a v1 nao cobria: deploy no meio de um job perdia a requisicao."""
    await _add_job(session, user, max_attempts=3)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    requeued = await reap_expired_leases(session)
    await session.commit()
    await session.refresh(claimed)

    assert requeued == 1
    assert claimed.status == JobStatus.QUEUED
    assert claimed.locked_by is None


async def test_reaper_fails_job_that_exhausted_attempts(session, user):
    await _add_job(session, user, max_attempts=1)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    claimed.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.commit()

    await reap_expired_leases(session)
    await session.commit()
    await session.refresh(claimed)

    assert claimed.status == JobStatus.FAILED, "nao pode ficar em loop eterno de reenfileiramento"
    assert claimed.error_code == "lease_expired"


async def test_complete_marks_success(session, user):
    await _add_job(session, user)
    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    await complete_job(session, job_id=claimed.id, worker_id="w1")
    await session.commit()
    await session.refresh(claimed)

    assert claimed.status == JobStatus.SUCCEEDED
    assert claimed.progress_percent == 100
    assert claimed.lease_expires_at is None


async def test_cancel_only_affects_queued_jobs(session, user):
    job = await _add_job(session, user)

    assert await cancel_job(session, job_id=job.id) is True
    await session.commit()

    other = await _add_job(session, user)
    await claim_job(session, worker_id="w1", lease_seconds=60)
    await session.commit()

    assert await cancel_job(session, job_id=other.id) is False, (
        "job em execucao nao pode ser cancelado pela fila"
    )


async def test_active_job_count_ignores_terminal_states(session, user):
    await _add_job(session, user)
    await _add_job(session, user)

    assert await count_active_jobs_for_user(session, user.id) == 2

    claimed = await claim_job(session, worker_id="w1", lease_seconds=60)
    await complete_job(session, job_id=claimed.id, worker_id="w1")
    await session.commit()

    assert await count_active_jobs_for_user(session, user.id) == 1
