"""Voting workflow (MASTER_INSTRUCTION.md Bab 24, 26).

Dispatches every graph step independently and concurrently — typically one
role per candidate, e.g. ``["writer", "analyst", "critic"]`` all answering the
same prompt — then lets the Consensus Engine pick the majority answer. If
agreement falls below the default confidence threshold (Bab 28), the result
is escalated to Human Approval (Bab 61) rather than trusting a weak plurality.
"""
from __future__ import annotations

import asyncio

from agents.base_agent import AgentResult
from api.config import settings
from core.utils.logger import get_logger
from orchestrator.consensus import ConsensusEngine
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph

from .base import BaseWorkflow, WorkflowResult

logger = get_logger(__name__)


class VotingWorkflow(BaseWorkflow):
    """Independent candidate answers, majority wins (Bab 26 — Majority Voting)."""

    mode = "voting"

    def __init__(self, consensus: ConsensusEngine | None = None) -> None:
        self._consensus = consensus or ConsensusEngine()

    async def run(self, graph: ExecutionGraph, dispatcher: Dispatcher) -> WorkflowResult:
        graph.validate()
        steps = graph.linear_order()
        trace_id = steps[0].task.trace_id if steps else ""

        results: list[AgentResult] = list(
            await asyncio.gather(*(dispatcher.dispatch(step.task) for step in steps))
        )
        decision = await self._consensus.decide(results, strategy="majority", trace_id=trace_id)
        logger.info(
            "workflow.voting.decided",
            trace_id=trace_id,
            agreement_rate=decision.agreement_rate,
            winner_role=decision.winner.role,
        )

        ordered = [(step.step_id, result) for step, result in zip(steps, results)]
        aggregated = self._aggregate(self.mode, trace_id, ordered)
        escalate = decision.agreement_rate < settings.CONFIDENCE_THRESHOLD_DEFAULT
        return WorkflowResult(
            mode=self.mode,
            trace_id=trace_id,
            final_output=decision.winner.output,
            results=aggregated.results,
            step_outputs=aggregated.step_outputs,
            degraded=aggregated.degraded or decision.winner.degraded,
            failed=not decision.winner.ok,
            escalate=escalate or aggregated.guardrail_blocked,
            guardrail_blocked=aggregated.guardrail_blocked,
        )
