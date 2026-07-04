"""Consensus Engine (MASTER_INSTRUCTION.md Bab 26).

Combines several independent ``AgentResult`` candidates — produced by running
the same prompt across multiple roles/agents — into one collective decision.
Used when accuracy/diversity of viewpoint matters more than speed or cost.

Strategies implemented (Bab 26 table):

* **Majority Voting** — the most common normalized answer wins.
* **Weighted Voting** — votes are weighted (e.g. by historical accuracy from
  Reflection Memory, Bab 28) before picking the winner.
* **Arbitrator Model** — an independent agent (the ``consensus`` role) reads
  every candidate and writes the final answer.

Structured Debate is implemented one layer up, in ``workflows/consensus.py``,
because it needs to re-dispatch tasks across rounds — this module only knows
how to *decide*, not how to run a workflow.

Every decision is published on the Event Bus as ``consensus.decided``
(Bab 23 prinsip 1) so it's auditable which strategy produced which outcome.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from agents.base_agent import AgentResult, Task, new_id
from core.utils.logger import get_logger
from messaging import EventBus
from messaging.events import CONSENSUS_DECIDED

from .dispatcher import Dispatcher

logger = get_logger(__name__)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _empty_result(trace_id: str = "") -> AgentResult:
    return AgentResult(
        output="",
        confidence=0.0,
        trace_id=trace_id,
        provider_used="none",
        model_used="none",
        error="no candidates to decide over",
    )


@dataclass(frozen=True)
class ConsensusDecision:
    """The chosen result plus how the decision was reached."""

    winner: AgentResult
    strategy: str
    agreement_rate: float
    candidates: list[AgentResult]


class ConsensusEngine:
    """Turns multiple candidate ``AgentResult``s into one decision (Bab 26)."""

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._events = event_bus or EventBus()

    @staticmethod
    def agreement_rate(results: list[AgentResult]) -> float:
        """Fraction of successful candidates that share the most common answer."""
        ok = [r for r in results if r.ok and r.output]
        if not ok:
            return 0.0
        counts = Counter(_normalize(r.output) for r in ok)
        _, top = counts.most_common(1)[0]
        return top / len(ok)

    def majority_vote(self, results: list[AgentResult]) -> ConsensusDecision:
        """Pick the most common normalized answer; ties broken by confidence.

        A tie is any set of distinct answers sharing the top vote count — not
        just duplicates of one answer — so e.g. two singleton answers (1 vote
        each) are compared against each other by confidence, not resolved by
        whichever happens to sort first.
        """
        ok = [r for r in results if r.ok and r.output]
        if not ok:
            winner = results[0] if results else _empty_result()
            return ConsensusDecision(winner=winner, strategy="majority", agreement_rate=0.0, candidates=results)
        counts = Counter(_normalize(r.output) for r in ok)
        top_count = max(counts.values())
        tied_keys = {key for key, count in counts.items() if count == top_count}
        contenders = [r for r in ok if _normalize(r.output) in tied_keys]
        winner = max(contenders, key=lambda r: r.confidence)
        rate = counts[_normalize(winner.output)] / len(ok)
        return ConsensusDecision(winner=winner, strategy="majority", agreement_rate=rate, candidates=results)

    def weighted_vote(self, results: list[AgentResult], weights: dict[str, float]) -> ConsensusDecision:
        """Like majority voting, but each candidate's vote is scaled by ``weights``.

        ``weights`` is keyed by ``agent_id`` first, falling back to ``role``; an
        unweighted candidate counts as ``1.0`` (Bab 26 — weighted by e.g. Bab 28
        historical accuracy, supplied by the caller).
        """
        ok = [r for r in results if r.ok and r.output]
        if not ok:
            winner = results[0] if results else _empty_result()
            return ConsensusDecision(winner=winner, strategy="weighted", agreement_rate=0.0, candidates=results)

        totals: dict[str, float] = {}
        representative: dict[str, AgentResult] = {}
        for r in ok:
            key = _normalize(r.output)
            weight = weights.get(r.agent_id, weights.get(r.role, 1.0))
            totals[key] = totals.get(key, 0.0) + weight
            if key not in representative or r.confidence > representative[key].confidence:
                representative[key] = r

        top_key = max(totals, key=totals.get)
        winner = representative[top_key]
        rate = totals[top_key] / sum(totals.values())
        return ConsensusDecision(winner=winner, strategy="weighted", agreement_rate=rate, candidates=results)

    async def arbitrate(
        self,
        results: list[AgentResult],
        dispatcher: Dispatcher,
        arbitrator_role: str = "consensus",
        trace_id: str = "",
    ) -> ConsensusDecision:
        """Dispatch all candidates to an arbitrator agent, which writes the final answer."""
        ok = [r for r in results if r.ok and r.output]
        if not ok:
            winner = results[0] if results else _empty_result(trace_id)
            return ConsensusDecision(winner=winner, strategy="arbitrator", agreement_rate=0.0, candidates=results)

        options = "\n\n".join(f"[Kandidat {i + 1} — {r.role}]\n{r.output}" for i, r in enumerate(ok))
        prompt = (
            "Beberapa agent memberikan jawaban independen untuk task yang sama. "
            "Timbang seluruh opini, pilih atau gabungkan menjadi satu jawaban akhir terbaik:\n\n"
            f"{options}"
        )
        task = Task(role=arbitrator_role, prompt=prompt, trace_id=trace_id or new_id())
        winner = await dispatcher.dispatch(task)
        return ConsensusDecision(
            winner=winner, strategy="arbitrator", agreement_rate=self.agreement_rate(ok), candidates=results
        )

    async def decide(
        self,
        results: list[AgentResult],
        strategy: str = "majority",
        dispatcher: Dispatcher | None = None,
        weights: dict[str, float] | None = None,
        trace_id: str = "",
    ) -> ConsensusDecision:
        """Dispatch to the requested strategy and publish ``consensus.decided``."""
        if strategy == "majority":
            decision = self.majority_vote(results)
        elif strategy == "weighted":
            decision = self.weighted_vote(results, weights or {})
        elif strategy == "arbitrator":
            if dispatcher is None:
                raise ValueError("arbitrator strategy requires a dispatcher")
            decision = await self.arbitrate(results, dispatcher, trace_id=trace_id)
        else:
            raise ValueError(f"unknown consensus strategy: {strategy!r}")

        await self._events.emit(
            CONSENSUS_DECIDED,
            source="consensus_engine",
            trace_id=trace_id,
            payload={"strategy": decision.strategy, "agreement_rate": decision.agreement_rate},
        )
        logger.info(
            "consensus.decide",
            strategy=decision.strategy,
            agreement_rate=decision.agreement_rate,
            trace_id=trace_id,
        )
        return decision
