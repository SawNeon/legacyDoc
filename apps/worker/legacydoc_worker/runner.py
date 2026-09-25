"""Worker main loop."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import uuid

import httpx
from legacydoc_core.db import init_engine, session_scope
from legacydoc_core.errors import LegacyDocError
from legacydoc_core.models import Job
from legacydoc_core.queue import claim_job, complete_job, fail_job, reap_expired_leases
from legacydoc_core.settings import Settings

from legacydoc_worker.processor import JobProcessor

logger = logging.getLogger(__name__)

REAP_INTERVAL_SECONDS = 60


class Worker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._processor = JobProcessor(settings)
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        init_engine(self._settings)
        self._install_signal_handlers()

        logger.info(
            "Worker %s iniciado com %d slots.",
            self._worker_id,
            self._settings.worker_concurrency,
        )

        tasks = [
            asyncio.create_task(self._slot(index))
            for index in range(self._settings.worker_concurrency)
        ]
        tasks.append(asyncio.create_task(self._reaper()))

        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("Worker %s encerrado.", self._worker_id)

    async def _slot(self, index: int) -> None:
        slot_id = f"{self._worker_id}#{index}"

        while not self._shutdown.is_set():
            try:
                claimed = await self._claim_and_run(slot_id)
            except Exception:
                logger.exception("Falha inesperada no slot %s.", slot_id)
                claimed = False

            if not claimed:
                try:
                    await asyncio.wait_for(
                        self._shutdown.wait(),
                        timeout=self._settings.worker_poll_interval_seconds,
                    )
                except TimeoutError:
                    continue

    async def _claim_and_run(self, slot_id: str) -> bool:
        async with session_scope() as session:
            job = await claim_job(
                session,
                worker_id=slot_id,
                lease_seconds=self._settings.job_lease_seconds,
            )

            if job is None:
                return False

            job_id = job.id
            logger.info("Slot %s pegou o job %s (%s).", slot_id, job_id, job.job_type)

        await self._execute(job_id, slot_id)

        return True

    async def _execute(self, job_id: uuid.UUID, slot_id: str) -> None:
        async with session_scope() as session:
            job = await session.get(Job, job_id)

            if job is None:
                return

            try:
                outcome = await self._processor.process(session, job, worker_id=slot_id)
            except LegacyDocError as exc:
                await fail_job(
                    session,
                    job_id=job_id,
                    worker_id=slot_id,
                    error_code=exc.code,
                    error_message=exc.message,
                    retryable=False,
                )
                logger.warning("Job %s falhou: %s", job_id, exc.message)
                await self._notify(job, status="failed", error=exc.message)
                return
            except Exception as exc:
                requeued = await fail_job(
                    session,
                    job_id=job_id,
                    worker_id=slot_id,
                    error_code="internal_error",
                    error_message=str(exc),
                    retryable=True,
                )
                logger.exception(
                    "Job %s falhou (%s).", job_id, "reenfileirado" if requeued else "definitivo"
                )

                if not requeued:
                    await self._notify(job, status="failed", error=str(exc))
                return

            if outcome.documents_created == 0:
                await fail_job(
                    session,
                    job_id=job_id,
                    worker_id=slot_id,
                    error_code="no_documents",
                    error_message="; ".join(outcome.warnings[:5]) or "Nenhum documento foi gerado.",
                    retryable=False,
                )
                await self._notify(job, status="failed", error="Nenhum documento gerado.")
                return

            await complete_job(session, job_id=job_id, worker_id=slot_id)

            if outcome.warnings:
                job.progress_message = f"Concluido com {len(outcome.warnings)} aviso(s)."

            logger.info("Job %s concluido: %d documento(s).", job_id, outcome.documents_created)

        await self._notify(job, status="succeeded", documents=outcome.documents_created)

    async def _reaper(self) -> None:
        """Requeue jobs whose worker died without finishing."""
        while not self._shutdown.is_set():
            try:
                async with session_scope() as session:
                    requeued = await reap_expired_leases(session)

                if requeued:
                    logger.info("%d job(s) com lease vencido reenfileirados.", requeued)
            except Exception:
                logger.exception("Falha ao varrer leases vencidos.")

            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=REAP_INTERVAL_SECONDS)
            except TimeoutError:
                continue

    async def _notify(self, job: Job, *, status: str, **extra) -> None:
        """Fire the webhook when configured. A failure here never fails the job."""
        if not job.webhook_url:
            return

        payload = {"job_id": str(job.id), "status": status, **extra}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(job.webhook_url, json=payload)
        except Exception as exc:
            logger.warning("Webhook do job %s falhou: %s", job.id, exc)

    def _install_signal_handlers(self) -> None:
        """Graceful shutdown: stop claiming work and let the current job finish."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown.set)
            except NotImplementedError:
                signal.signal(sig, lambda *_: self._shutdown.set())
