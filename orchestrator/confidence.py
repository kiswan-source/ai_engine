"""Confidence Scoring (MASTER_INSTRUCTION.md Bab 28).

Replaces the placeholder heuristic in ``agents/generic_agent.py`` (Tahap 2)
with a blend of the signals from the Bab 28 table that this platform actually
has available:

* **self-reported** — the agent's own heuristic confidence (``AgentResult.confidence``),
  standing in for provider log-probability where a model doesn't expose one.
* **history** — the role's track record from Reflection Memory (Bab 25).
* **agreement** — how much independent agents agreed, when the caller is the
  Consensus/Voting Engine (Bab 26).

Guardrail/output-validator signal (Bab 30) isn't wired in — that module ships
in Tahap 7. A missing signal is dropped and the remaining weights renormalized,
so the blended score always stays in ``[0.0, 1.0]``.
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.base_agent import AgentResult
from api.config import settings
from memory.reflection_memory import ReflectionMemory

_W_SELF_REPORTED = 0.5
_W_HISTORY = 0.3
_W_AGREEMENT = 0.2


@dataclass(frozen=True)
class ConfidenceBreakdown:
    """The blended score plus each contributing signal (for observability)."""

    score: float
    self_reported: float
    history: float | None
    agreement: float | None


class ConfidenceScorer:
    """Blends self-reported, historical, and agreement signals into one score (Bab 28)."""

    async def score(
        self,
        result: AgentResult,
        memory: ReflectionMemory | None = None,
        agreement_rate: float | None = None,
    ) -> ConfidenceBreakdown:
        """Score ``result`` for its role, optionally folding in ``memory``/``agreement_rate``."""
        self_reported = result.confidence

        history: float | None = None
        if memory is not None:
            recent = await memory.recent(result.role, limit=20)
            scored = [entry["score"] for entry in recent if "score" in entry]
            if scored:
                history = sum(scored) / len(scored)

        signals: list[tuple[float, float]] = [(_W_SELF_REPORTED, self_reported)]
        if history is not None:
            signals.append((_W_HISTORY, history))
        if agreement_rate is not None:
            signals.append((_W_AGREEMENT, agreement_rate))

        total_weight = sum(weight for weight, _ in signals)
        blended = sum(weight * value for weight, value in signals) / total_weight if total_weight else 0.0
        return ConfidenceBreakdown(
            score=round(blended, 4),
            self_reported=self_reported,
            history=history,
            agreement=agreement_rate,
        )


def threshold_for(risk: str = "default") -> float:
    """Domain confidence threshold (Bab 28 rule 2 — high-risk domains are stricter)."""
    if risk == "high":
        return settings.CONFIDENCE_THRESHOLD_HIGH_RISK
    return settings.CONFIDENCE_THRESHOLD_DEFAULT
