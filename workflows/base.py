"""Shared workflow contract (MASTER_INSTRUCTION.md Bab 24).

Internal base module for the workflow patterns in this package. Every workflow
consumes an :class:`~orchestrator.execution_graph.ExecutionGraph` and a
``Dispatcher``, and returns a uniform :class:`WorkflowResult` so the Orchestrator
(Bab 18) treats all patterns interchangeably.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agents.base_agent import AgentResult

if TYPE_CHECKING:  # avoid import cycle at runtime; orchestrator imports workflows
    from orchestrator.dispatcher import Dispatcher
    from orchestrator.execution_graph import ExecutionGraph


@dataclass(frozen=True)
class WorkflowResult:
    """Uniform result of running any workflow pattern."""

    mode: str
    trace_id: str
    final_output: str
    results: list[AgentResult] = field(default_factory=list)
    step_outputs: dict[str, AgentResult] = field(default_factory=dict)
    degraded: bool = False
    failed: bool = False
    # Set when the result needs Human Approval before it can complete (Bab 25
    # rule 3, Bab 61) — e.g. Reflection never reached its confidence threshold,
    # or Consensus/Voting agreement fell below it. The Orchestrator, not this
    # dataclass, decides what to do about it.
    escalate: bool = False


class BaseWorkflow(ABC):
    """Interface every workflow pattern implements."""

    mode: str = "base"

    @abstractmethod
    async def run(self, graph: "ExecutionGraph", dispatcher: "Dispatcher") -> WorkflowResult:
        """Execute ``graph`` using ``dispatcher`` and return a result."""
        raise NotImplementedError

    @staticmethod
    def _aggregate(
        mode: str,
        trace_id: str,
        ordered: list[tuple[str, AgentResult]],
        escalate: bool = False,
    ) -> WorkflowResult:
        """Build a :class:`WorkflowResult` from ``(step_id, result)`` pairs."""
        results = [r for _, r in ordered]
        step_outputs = dict(ordered)
        degraded = any(r.degraded for r in results)
        failed = any(not r.ok for r in results)
        # Final output: the last successful output, else the last output produced.
        final = ""
        for r in results:
            if r.ok and r.output:
                final = r.output
        if not final and results:
            final = results[-1].output
        return WorkflowResult(
            mode=mode,
            trace_id=trace_id,
            final_output=final,
            results=results,
            step_outputs=step_outputs,
            degraded=degraded,
            failed=failed,
            escalate=escalate,
        )
