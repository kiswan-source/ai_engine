"""Sequential workflow — linear, dependency-ordered execution (Bab 24).

Runs steps one after another in topological order, chaining each step's output
into the next step's prompt (Planner → Research → Writer style). Used when tasks
have a clear linear dependency.
"""
from __future__ import annotations

import dataclasses

from core.utils.logger import get_logger
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph

from .base import BaseWorkflow, WorkflowResult

logger = get_logger(__name__)


class SequentialWorkflow(BaseWorkflow):
    """Execute graph steps sequentially, feeding output forward."""

    mode = "sequential"

    async def run(self, graph: ExecutionGraph, dispatcher: Dispatcher) -> WorkflowResult:
        graph.validate()
        ordered: list[tuple[str, "object"]] = []
        trace_id = ""
        prev_output = ""
        prev_role = ""

        for step in graph.linear_order():
            trace_id = step.task.trace_id
            task = step.task
            if prev_output:
                # Chain previous output into this step's prompt (Bab 24 sequential).
                chained_prompt = (
                    f"{task.prompt}\n\n"
                    f"[Konteks dari langkah sebelumnya — {prev_role}]:\n{prev_output}"
                )
                task = dataclasses.replace(task, prompt=chained_prompt)

            result = await dispatcher.dispatch(task)
            ordered.append((step.step_id, result))
            logger.info(
                "workflow.sequential.step",
                step_id=step.step_id,
                trace_id=trace_id,
                ok=result.ok,
                degraded=result.degraded,
            )
            if result.ok and result.output:
                prev_output = result.output
                prev_role = result.role

        return self._aggregate(self.mode, trace_id, ordered)  # type: ignore[arg-type]
