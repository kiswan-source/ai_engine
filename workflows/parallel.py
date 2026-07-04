"""Parallel workflow — concurrent execution of independent steps (Bab 24).

Runs each dependency layer concurrently with ``asyncio.gather(..., return_exceptions=True)``
(Bab 9): one failing step never cancels its siblings. For a fully independent
plan this is a single layer; graphs with dependencies still run layer-by-layer.
"""
from __future__ import annotations

import asyncio

from agents.base_agent import AgentResult
from core.utils.logger import get_logger
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph

from .base import BaseWorkflow, WorkflowResult

logger = get_logger(__name__)


class ParallelWorkflow(BaseWorkflow):
    """Execute graph steps concurrently, one dependency layer at a time."""

    mode = "parallel"

    async def run(self, graph: ExecutionGraph, dispatcher: Dispatcher) -> WorkflowResult:
        graph.validate()
        ordered: list[tuple[str, AgentResult]] = []
        trace_id = ""

        for layer in graph.topological_layers():
            coros = [dispatcher.dispatch(step.task) for step in layer]
            results = await asyncio.gather(*coros, return_exceptions=True)
            for step, result in zip(layer, results):
                trace_id = step.task.trace_id
                if isinstance(result, BaseException):
                    # gather caught an unexpected (non-ProviderError) failure.
                    logger.error(
                        "workflow.parallel.step_error",
                        step_id=step.step_id,
                        trace_id=trace_id,
                        error=str(result),
                    )
                    result = AgentResult(
                        output="",
                        confidence=0.0,
                        trace_id=trace_id,
                        provider_used="none",
                        model_used="none",
                        role=step.task.role,
                        degraded=True,
                        error=f"unexpected: {result}",
                    )
                ordered.append((step.step_id, result))

        return self._aggregate(self.mode, trace_id, ordered)
