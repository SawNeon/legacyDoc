"""Job queue built on Postgres.

There is no separate broker. Workers claim work with
`SELECT ... FOR UPDATE SKIP LOCKED`, which is atomic and lets N concurrent
workers run without two claiming the same job.

Every job carries a lease that the running worker keeps renewing. If the
process dies the lease expires and another worker reclaims the job, so a
deploy mid-processing does not lose the client request.

The SQLite path exists only so the test suite can run without a container. It
has no SKIP LOCKED and must not be used with real concurrency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from legacydoc_core.models import Job, JobStatus

_BACKOFF_BASE_SECONDS = 30
_MAX_BACKOFF_SECONDS = 900


def _now() -> datetime:
    return datetime.now(UTC)


def _is_postgres(session: AsyncSession) -> bool:
    return session.bind.dialect.name == "postgresql"  # type: ignore[union-attr]


async def enqueue(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    job_type: str,
    params: dict[str, Any],
    priority: int = 100,
    project_id: uuid.UUID | None = None,
    max_attempts: int = 3,
    webhook_url: str | None = None,
) -> Job:
    job = Job(
        user_id=user_id,
        project_id=project_id,
        job_type=job_type,
        params=params,
        priority=priority,
        max_attempts=max_attempts,
        webhook_url=webhook_url,
        status=JobStatus.QUEUED,
        scheduled_at=_now(),
    )
    session.add(job)
    await session.flush()
    return job


async def claim_job(
    session: AsyncSession,
    *,
    worker_id: str,
    lease_seconds: int,
) -> Job | None:
    """Claim the next eligible job, or None when the queue is empty.

    Ordered by priority so paid plans go first, then by `scheduled_at`, which
    preserves FIFO within a tier.
    """
    lease_until = _now() + timedelta(seconds=lease_seconds)

    if _is_postgres(session):
        statement = text(
            """
            UPDATE jobs
               SET status = :running,
                   locked_by = :worker_id,
                   lease_expires_at = :lease_until,
                   attempts = attempts + 1,
                   started_at = COALESCE(started_at, now()),
                   updated_at = now()
             WHERE id = (
                   SELECT id
                     FROM jobs
                    WHERE status = :queued
                      AND scheduled_at <= now()
                    ORDER BY priority ASC, scheduled_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
             )
            RETURNING id
            """
        )
        result = await session.execute(
            statement,
            {
                "running": JobStatus.RUNNING.value,
                "queued": JobStatus.QUEUED.value,
                "worker_id": worker_id,
                "lease_until": lease_until,
            },
        )
        row = result.first()

        if row is None:
            return None

        return await session.get(Job, row[0])

    candidate = (
        await session.execute(
            select(Job)
            .where(Job.status == JobStatus.QUEUED, Job.scheduled_at <= _now())
            .order_by(Job.priority.asc(), Job.scheduled_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if candidate is None:
        return None

    updated = await session.execute(
        update(Job)
        .where(Job.id == candidate.id, Job.status == JobStatus.QUEUED)
        .values(
            status=JobStatus.RUNNING,
            locked_by=worker_id,
            lease_expires_at=lease_until,
            attempts=Job.attempts + 1,
            started_at=candidate.started_at or _now(),
        )
    )

    if updated.rowcount == 0:
        return None

    await session.refresh(candidate)
    return candidate


async def heartbeat(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int,
    progress_percent: int | None = None,
    progress_message: str | None = None,
) -> bool:
    """Renew the lease and publish progress.

    Returns False when the job no longer belongs to this worker, in which case
    the caller must abort to avoid duplicating work.
    """
    values: dict[str, Any] = {"lease_expires_at": _now() + timedelta(seconds=lease_seconds)}

    if progress_percent is not None:
        values["progress_percent"] = max(0, min(100, progress_percent))
    if progress_message is not None:
        values["progress_message"] = progress_message[:300]

    result = await session.execute(
        update(Job)
        .where(
            Job.id == job_id,
            Job.locked_by == worker_id,
            Job.status == JobStatus.RUNNING,
        )
        .values(**values)
    )
    return result.rowcount > 0


async def complete_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.locked_by == worker_id)
        .values(
            status=JobStatus.SUCCEEDED,
            finished_at=_now(),
            progress_percent=100,
            progress_message="Concluido.",
            lease_expires_at=None,
            error_code=None,
            error_message=None,
        )
    )


async def fail_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool = True,
) -> bool:
    """Record a failure, rescheduling with backoff while attempts remain.

    Returns True when the job returned to the queue, False when it failed for good.
    """
    job = await session.get(Job, job_id)

    if job is None or job.locked_by != worker_id:
        return False

    should_retry = retryable and job.attempts < job.max_attempts

    if should_retry:
        delay = min(_BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)), _MAX_BACKOFF_SECONDS)
        job.status = JobStatus.QUEUED
        job.scheduled_at = _now() + timedelta(seconds=delay)
        job.locked_by = None
        job.lease_expires_at = None
        job.progress_message = f"Falhou, nova tentativa em {delay}s."
    else:
        job.status = JobStatus.FAILED
        job.finished_at = _now()
        job.lease_expires_at = None
        job.locked_by = None

    job.error_code = error_code
    job.error_message = error_message[:4000]

    await session.flush()
    return should_retry


async def reap_expired_leases(session: AsyncSession) -> int:
    """Requeue jobs whose worker died without finishing.

    Jobs that exhausted their attempts become FAILED instead of looping forever.
    """
    now = _now()

    requeued = await session.execute(
        update(Job)
        .where(
            Job.status == JobStatus.RUNNING,
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
            Job.attempts < Job.max_attempts,
        )
        .values(
            status=JobStatus.QUEUED,
            locked_by=None,
            lease_expires_at=None,
            scheduled_at=now,
            progress_message="Worker perdeu o lease; reenfileirado.",
        )
    )

    await session.execute(
        update(Job)
        .where(
            Job.status == JobStatus.RUNNING,
            Job.lease_expires_at.is_not(None),
            Job.lease_expires_at < now,
            Job.attempts >= Job.max_attempts,
        )
        .values(
            status=JobStatus.FAILED,
            locked_by=None,
            lease_expires_at=None,
            finished_at=now,
            error_code="lease_expired",
            error_message="O worker parou de responder e as tentativas acabaram.",
        )
    )

    return requeued.rowcount


async def count_active_jobs_for_user(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Queued or running jobs, used to enforce the plan concurrency limit."""
    result = await session.execute(
        select(Job.id).where(
            Job.user_id == user_id,
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    return len(result.all())


async def cancel_job(session: AsyncSession, *, job_id: uuid.UUID) -> bool:
    """Cancel a job that has not started.

    A running job is not interrupted; the worker only observes cancellation on
    its next heartbeat.
    """
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
        .values(
            status=JobStatus.CANCELLED,
            finished_at=_now(),
            progress_message="Cancelado pelo usuario.",
        )
    )
    return result.rowcount > 0
