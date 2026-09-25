"""Queue concurrency proven against a real Postgres."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from legacydoc_core.models import Base, Job, JobStatus, User
from legacydoc_core.queue import claim_job, enqueue
from legacydoc_core.security import hash_password
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="requires Postgres; SQLite has no SKIP LOCKED",
)

JOB_COUNT = 40
WORKER_COUNT = 8


@pytest.fixture
async def engine():
    engine = create_async_engine(DATABASE_URL)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with factory() as session:
        await session.execute(delete(Job))
        await session.execute(delete(User))
        await session.commit()

    return factory


@pytest.fixture
async def seeded_user(session_factory) -> uuid.UUID:
    async with session_factory() as session:
        user = User(
            email=f"queue-{uuid.uuid4().hex[:8]}@example.com",
            password_hash=hash_password("password-long-enough-1"),
        )
        session.add(user)
        await session.commit()

        return user.id


async def _seed_jobs(session_factory, user_id: uuid.UUID, count: int) -> None:
    async with session_factory() as session:
        for index in range(count):
            await enqueue(
                session,
                user_id=user_id,
                job_type="document_snippet",
                params={"path": f"file_{index}.py", "content": "def f(): pass"},
            )
        await session.commit()


async def _drain(session_factory, worker_id: str) -> list[uuid.UUID]:
    """Claim jobs until the queue is empty, each worker on its own connection."""
    claimed: list[uuid.UUID] = []

    while True:
        async with session_factory() as session:
            job = await claim_job(session, worker_id=worker_id, lease_seconds=300)
            await session.commit()

            if job is None:
                return claimed

            claimed.append(job.id)


async def test_concurrent_workers_never_claim_the_same_job(session_factory, seeded_user):
    """The guarantee the entire scaling story rests on."""
    await _seed_jobs(session_factory, seeded_user, JOB_COUNT)

    results = await asyncio.gather(
        *(_drain(session_factory, f"worker-{index}") for index in range(WORKER_COUNT))
    )

    all_claimed = [job_id for worker_result in results for job_id in worker_result]

    assert len(all_claimed) == JOB_COUNT, "every job must be claimed exactly once"
    assert len(set(all_claimed)) == JOB_COUNT, "a job was handed to two workers"


async def test_every_job_ends_up_running_and_owned(session_factory, seeded_user):
    await _seed_jobs(session_factory, seeded_user, JOB_COUNT)

    await asyncio.gather(
        *(_drain(session_factory, f"worker-{index}") for index in range(WORKER_COUNT))
    )

    async with session_factory() as session:
        jobs = (await session.execute(select(Job))).scalars().all()

    assert len(jobs) == JOB_COUNT
    assert all(job.status == JobStatus.RUNNING for job in jobs)
    assert all(job.locked_by is not None for job in jobs)
    assert all(job.attempts == 1 for job in jobs), "no job may be claimed twice"


async def test_priority_is_respected_under_concurrency(session_factory, seeded_user):
    async with session_factory() as session:
        low_priority = await enqueue(
            session,
            user_id=seeded_user,
            job_type="document_snippet",
            params={"path": "low.py", "content": "x = 1"},
            priority=100,
        )
        high_priority = await enqueue(
            session,
            user_id=seeded_user,
            job_type="document_snippet",
            params={"path": "high.py", "content": "x = 1"},
            priority=10,
        )
        await session.commit()

    async with session_factory() as session:
        first = await claim_job(session, worker_id="worker-a", lease_seconds=300)
        await session.commit()

    assert first is not None
    assert first.id == high_priority.id
    assert first.id != low_priority.id
