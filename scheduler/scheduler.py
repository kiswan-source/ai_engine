"""Automation scheduler (MASTER_INSTRUCTION.md Bab 68 Prioritas 5).

An in-process async tick loop that fires due ``ScheduledJob`` rows through
the same ``Orchestrator`` instance ``api/routes/orchestrator.py`` already
uses — not a separate worker process, and not routed through
``messaging.TaskQueue``. That queue exists (Bab 23) but nothing currently
consumes it (see ``telemetry/monitoring.py``'s ``queue_dashboard`` docstring
— "nothing has started publishing to it yet"); building a consumer for it
is a separate, larger piece of work than this first Automation pass
warrants. Direct in-process execution is simpler and provably live in a
single-process deployment, at the cost of jobs not surviving a process
restart mid-run (acceptable for a first pass — Bab 3 incremental, not a
production HA guarantee).

Trigger model is deliberately a plain interval ("every N seconds"), not
cron syntax — see ``db.models.ScheduledJob`` docstring for why.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.utils.logger import get_logger
from db.connection import AsyncSessionFactory
from db.models import ScheduledJob
from orchestrator.orchestrator import Orchestrator

logger = get_logger(__name__)


class Scheduler:
    """Ticks every ``tick_seconds``, running whichever jobs are due."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        tick_seconds: int = 30,
        clock: Callable[[], datetime] = datetime.utcnow,
    ) -> None:
        self._orchestrator = orchestrator
        self._tick_seconds = tick_seconds
        self._clock = clock
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        """Idempotent — safe to call more than once (mirrors Orchestrator._ensure_telemetry_started)."""
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("scheduler.started", tick_seconds=self._tick_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("scheduler.stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except Exception as exc:  # a bad tick must never kill the loop (Bab 10 — no silent failure, but no crash either)
                logger.error("scheduler.tick_failed", error=str(exc))
            await asyncio.sleep(self._tick_seconds)

    async def tick(self) -> int:
        """Run every due job once. Exposed directly (not just via the sleep loop) so tests can call it without waiting."""
        now = self._clock()
        async with AsyncSessionFactory() as session:
            result = await session.execute(
                select(ScheduledJob).where(
                    ScheduledJob.enabled.is_(True),
                    (ScheduledJob.next_run_at.is_(None)) | (ScheduledJob.next_run_at <= now),
                )
            )
            due = result.scalars().all()
            for job in due:
                await self._run_job(session, job, now)
            await session.commit()
        return len(due)

    async def run_now(self, job_id: str) -> ScheduledJob | None:
        """Run one job immediately regardless of `next_run_at` (manual trigger from the API/UI)."""
        now = self._clock()
        async with AsyncSessionFactory() as session:
            job = await session.get(ScheduledJob, job_id)
            if job is None:
                return None
            await self._run_job(session, job, now)
            await session.commit()
            await session.refresh(job)
            return job

    async def _run_job(self, session: AsyncSession, job: ScheduledJob, now: datetime) -> None:
        try:
            result = await self._orchestrator.run(prompt=job.prompt, roles=job.roles, mode=job.mode)
            job.last_status = "failed" if result.failed else "success"
            job.last_result_summary = (result.final_output or "")[:500]
        except Exception as exc:  # a broken job must not stop other due jobs from running
            job.last_status = "failed"
            job.last_result_summary = str(exc)[:500]
            logger.error("scheduler.job_failed", job_id=job.id, name=job.name, error=str(exc))
        job.last_run_at = now
        job.next_run_at = now + timedelta(seconds=job.interval_seconds)
        session.add(job)
        logger.info("scheduler.job_ran", job_id=job.id, name=job.name, status=job.last_status)
