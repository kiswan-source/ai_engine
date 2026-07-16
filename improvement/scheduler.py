"""Background tick loop for the Continuous Improvement Engine (Fase 7, DCF
v5 mandate). Deliberately separate from ``scheduler/scheduler.py`` (Bab
68 Prioritas 5) — that one runs user-created `ScheduledJob` workflow runs;
this one is an internal maintenance loop with nothing user-facing to
configure, a different concern entirely.

Every tick: analyze (always — read-only, safe, gives the ledger a
continuous trail even if auto-apply is off), record every recommendation,
auto-apply only if ``ENABLE_AUTONOMOUS_IMPROVEMENT`` is on, then check
whether any previously-applied action is due for review.
"""
from __future__ import annotations

import asyncio

from core.utils.logger import get_logger
from improvement import ledger
from improvement.apply import apply_recommendation, review_pending_actions
from improvement.engine import ImprovementEngine

logger = get_logger(__name__)


class ImprovementScheduler:
    def __init__(self, engine: ImprovementEngine | None = None, tick_seconds: int | None = None) -> None:
        from api.config import settings

        self._engine = engine or ImprovementEngine()
        self._tick_seconds = settings.IMPROVEMENT_TICK_SECONDS if tick_seconds is None else tick_seconds
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())
        logger.info("improvement_scheduler.started", tick_seconds=self._tick_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self._tick_seconds)
            try:
                await self.tick()
            except Exception as e:
                # A tick failure must never kill the loop — same Bab 10.4
                # principle every other background loop in this codebase follows.
                logger.error("improvement_scheduler.tick_failed", error=str(e))

    async def tick(self) -> list:
        from api.config import settings

        recommendations = await self._engine.analyze()
        applied = []
        for rec in recommendations:
            ledger.record_recommendation(rec)
            if settings.ENABLE_AUTONOMOUS_IMPROVEMENT:
                action = apply_recommendation(rec)
                if action is not None:
                    applied.append(action)

        reviewed = await review_pending_actions(self._engine)
        return [*applied, *reviewed]
