"""Reflection workflow (MASTER_INSTRUCTION.md Bab 24, 25).

Runs every graph step through the Reflection Engine's generate/self-evaluate/
revise cycle instead of a single dispatch, chaining output forward like
``SequentialWorkflow`` (the Planner builds a reflection graph the same way).
If any step exhausts its iteration budget without reaching the confidence
threshold, the aggregated result is flagged ``escalate=True`` so the
Orchestrator routes it to the Human Approval gate (Bab 25 rule 3).
"""
from __future__ import annotations

import dataclasses

from core.utils.logger import get_logger
from memory.memory_manager import build_memory_manager
from orchestrator.confidence import ConfidenceScorer
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph
from orchestrator.reflection import ReflectionEngine

from .base import BaseWorkflow, WorkflowResult

logger = get_logger(__name__)


class ReflectionWorkflow(BaseWorkflow):
    """Execute each step through a Reflection cycle, chaining output forward."""

    mode = "reflection"

    def __init__(self, memory=None, scorer: ConfidenceScorer | None = None) -> None:
        self._memory = memory or build_memory_manager().reflection
        self._scorer = scorer or ConfidenceScorer()

    async def run(self, graph: ExecutionGraph, dispatcher: Dispatcher) -> WorkflowResult:
        graph.validate()
        ordered: list[tuple[str, "object"]] = []
        trace_id = ""
        prev_output = ""
        prev_role = ""
        any_escalate = False

        for step in graph.linear_order():
            trace_id = step.task.trace_id
            task = step.task
            if prev_output:
                chained_prompt = (
                    f"{task.prompt}\n\n"
                    f"[Konteks dari langkah sebelumnya — {prev_role}]:\n{prev_output}"
                )
                task = dataclasses.replace(task, prompt=chained_prompt)

            engine = ReflectionEngine(dispatcher, self._memory, scorer=self._scorer)
            outcome = await engine.run(task)
            ordered.append((step.step_id, outcome.result))
            any_escalate = any_escalate or outcome.escalate
            logger.info(
                "workflow.reflection.step",
                step_id=step.step_id,
                trace_id=trace_id,
                iterations=outcome.iterations,
                confidence=outcome.confidence,
                escalate=outcome.escalate,
            )
            if outcome.result.ok and outcome.result.output:
                prev_output = outcome.result.output
                prev_role = outcome.result.role

        return self._aggregate(self.mode, trace_id, ordered, escalate=any_escalate)  # type: ignore[arg-type]
