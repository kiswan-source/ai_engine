"""Reflection Engine (MASTER_INSTRUCTION.md Bab 25).

Runs the ``Generate -> Self-Evaluate -> Identify Weakness -> Revise ->
Re-Evaluate`` cycle for a single task, capped at ``REFLECTION_MAX_ITERATIONS``
rounds to bound cost/latency (rule 1). Every iteration is journaled to
Reflection Memory (rule 2). If the confidence threshold is never reached, this
module does not force the task through — it reports ``escalate=True`` and
leaves the Human Approval decision to the caller (rule 3, Bab 24/61).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from agents.base_agent import AgentResult, Task
from api.config import settings
from core.utils.logger import get_logger
from memory.reflection_memory import ReflectionMemory
from messaging import EventBus
from messaging.events import AGENT_REVIEWING

from .confidence import ConfidenceScorer, threshold_for
from .dispatcher import Dispatcher

logger = get_logger(__name__)


@dataclass(frozen=True)
class ReflectionOutcome:
    """Final result of a reflection cycle plus whether it needs Human Approval."""

    result: AgentResult
    confidence: float
    iterations: int
    escalate: bool


def _revise_prompt(original: str, previous_output: str, iteration: int) -> str:
    return (
        f"{original}\n\n"
        f"[Refleksi ronde {iteration}] Jawaban sebelumnya:\n{previous_output}\n\n"
        "Identifikasi kelemahan jawaban di atas, lalu berikan versi yang sudah diperbaiki."
    )


class ReflectionEngine:
    """Generate/self-evaluate/revise loop for one task (Bab 25)."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        memory: ReflectionMemory,
        scorer: ConfidenceScorer | None = None,
        max_iterations: int | None = None,
        risk: str = "default",
        event_bus: EventBus | None = None,
    ) -> None:
        self._dispatcher = dispatcher
        self._memory = memory
        self._scorer = scorer or ConfidenceScorer()
        self._max_iterations = (
            settings.REFLECTION_MAX_ITERATIONS if max_iterations is None else max_iterations
        )
        self._threshold = threshold_for(risk)
        self._events = event_bus or EventBus()

    async def run(self, task: Task) -> ReflectionOutcome:
        """Run the reflection cycle for ``task`` until threshold or iteration cap."""
        current = task
        result: AgentResult | None = None
        confidence = 0.0
        iteration = 0

        for iteration in range(1, self._max_iterations + 1):
            result = await self._dispatcher.dispatch(current)
            breakdown = await self._scorer.score(result, memory=self._memory)
            confidence = breakdown.score
            success = confidence >= self._threshold

            await self._memory.record(
                role=task.role,
                task_id=task.task_id,
                trace_id=task.trace_id,
                success=success,
                score=confidence,
                lesson=(
                    ""
                    if success
                    else f"iterasi {iteration}: confidence {confidence:.2f} di bawah ambang {self._threshold:.2f}"
                ),
            )
            await self._events.emit(
                AGENT_REVIEWING,
                source="reflection_engine",
                trace_id=task.trace_id,
                payload={"iteration": iteration, "confidence": confidence, "role": task.role},
            )
            logger.info(
                "reflection.iteration",
                trace_id=task.trace_id,
                role=task.role,
                iteration=iteration,
                confidence=confidence,
                success=success,
            )

            if success or not result.ok:
                break
            current = dataclasses.replace(
                task, prompt=_revise_prompt(task.prompt, result.output, iteration)
            )

        escalate = confidence < self._threshold
        final = dataclasses.replace(result, confidence=confidence)
        return ReflectionOutcome(result=final, confidence=confidence, iterations=iteration, escalate=escalate)
