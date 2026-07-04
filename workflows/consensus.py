"""Consensus workflow (MASTER_INSTRUCTION.md Bab 24, 26).

Runs ``CONSENSUS_DEBATE_ROUNDS`` of Structured Debate — every candidate agent
sees the others' current answers and may revise its own — then hands all
final-round answers to an Arbitrator agent (the ``consensus`` role) to write
the decision. This is the "accuracy over speed/cost" pattern: Structured
Debate plus Arbitrator Model from the Bab 26 strategy table, combined because
neither alone resolves genuine disagreement as well as debate-then-arbitrate.
"""
from __future__ import annotations

import asyncio
import dataclasses

from agents.base_agent import AgentResult, Task
from api.config import settings
from core.utils.logger import get_logger
from orchestrator.consensus import ConsensusEngine
from orchestrator.dispatcher import Dispatcher
from orchestrator.execution_graph import ExecutionGraph, GraphValidationError

from .base import BaseWorkflow, WorkflowResult

logger = get_logger(__name__)


def _debate_prompt(original_prompt: str, others: list[AgentResult], round_no: int) -> str:
    rebuttals = "\n\n".join(f"[{r.role}]: {r.output}" for r in others if r.output)
    return (
        f"{original_prompt}\n\n"
        f"[Structured debate — ronde {round_no}] Pendapat agent lain:\n{rebuttals}\n\n"
        "Sanggah atau perkuat jawabanmu berdasarkan pendapat di atas, lalu berikan jawaban akhirmu."
    )


class ConsensusWorkflow(BaseWorkflow):
    """Structured debate across candidates, arbitrated to one decision (Bab 26)."""

    mode = "consensus"

    def __init__(self, consensus: ConsensusEngine | None = None, rounds: int | None = None) -> None:
        self._consensus = consensus or ConsensusEngine()
        self._rounds = settings.CONSENSUS_DEBATE_ROUNDS if rounds is None else rounds

    async def run(self, graph: ExecutionGraph, dispatcher: Dispatcher) -> WorkflowResult:
        graph.validate()
        steps = graph.linear_order()
        if not steps:
            raise GraphValidationError("consensus workflow requires at least one step")
        trace_id = steps[0].task.trace_id
        original_tasks: list[Task] = [step.task for step in steps]

        results: list[AgentResult] = list(
            await asyncio.gather(*(dispatcher.dispatch(task) for task in original_tasks))
        )

        for round_no in range(1, self._rounds + 1):
            revised_tasks = [
                dataclasses.replace(
                    original_tasks[i],
                    prompt=_debate_prompt(
                        original_tasks[i].prompt,
                        [r for j, r in enumerate(results) if j != i],
                        round_no,
                    ),
                )
                for i in range(len(original_tasks))
            ]
            results = list(await asyncio.gather(*(dispatcher.dispatch(task) for task in revised_tasks)))
            logger.info("workflow.consensus.debate_round", round=round_no, trace_id=trace_id)

        decision = await self._consensus.arbitrate(results, dispatcher, trace_id=trace_id)
        logger.info(
            "workflow.consensus.decided",
            trace_id=trace_id,
            agreement_rate=decision.agreement_rate,
        )

        ordered = [(step.step_id, result) for step, result in zip(steps, results)]
        aggregated = self._aggregate(self.mode, trace_id, ordered)
        escalate = decision.agreement_rate < settings.CONFIDENCE_THRESHOLD_DEFAULT
        return WorkflowResult(
            mode=self.mode,
            trace_id=trace_id,
            final_output=decision.winner.output,
            results=aggregated.results + [decision.winner],
            step_outputs=aggregated.step_outputs,
            degraded=aggregated.degraded or decision.winner.degraded,
            failed=not decision.winner.ok,
            escalate=escalate,
        )
