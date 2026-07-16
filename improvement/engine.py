"""Continuous Improvement Engine (Fase 7, DCF v5 mandate: "AI ENGINE
memperbaiki dirinya... namun SELF IMPROVEMENT != SELF UNCONTROLLED
CHANGE").

``ImprovementEngine.analyze()`` is pure read + detection: it looks at
telemetry (`telemetry/metrics.py`'s per-role error rates, already tracked)
and workflow escalation (tracked here — `telemetry/metrics.py` doesn't
track "how often workflows escalate to Human Approval", so a small,
self-contained `EscalationTracker` subscribes to the SAME shared
orchestrator's event bus rather than modifying that already-tested
module) against configurable thresholds with a minimum sample size, and
returns `ImprovementRecommendation`s. It never writes anything —
`improvement/apply.py` is the only thing that turns a recommendation into
an actual change, and only for whitelisted settings.

Every recommendation, actionable or not, is meant to be recorded to
`improvement/ledger.py` by the caller (the scheduler job or the API route
that triggers analysis) — `analyze()` itself has no side effects, so it's
safe to call as often as needed (e.g. from a dashboard "refresh").
"""
from __future__ import annotations

from typing import Optional

from improvement.models import ImprovementRecommendation
from messaging import EventBus
from messaging.schemas import Event


class EscalationTracker:
    """In-process tally of workflow starts vs. escalations to Human
    Approval (`workflow.pending` vs `workflow.reviewing` on the Event
    Bus) — same in-process-only, not-persisted-across-restarts assumption
    `telemetry.metrics.MetricsCollector` already makes."""

    def __init__(self, event_bus: EventBus) -> None:
        self._events = event_bus
        self._started = False
        self.pending_count = 0
        self.escalated_count = 0

    async def start(self) -> None:
        if self._started:
            return
        await self._events.subscribe("workflow.pending", self._on_pending)
        await self._events.subscribe("workflow.reviewing", self._on_reviewing)
        self._started = True

    async def _on_pending(self, event: Event) -> None:
        self.pending_count += 1

    async def _on_reviewing(self, event: Event) -> None:
        self.escalated_count += 1

    def escalate_rate(self) -> Optional[float]:
        """``None`` when there's nothing to compute from yet — distinct
        from ``0.0``, which is a real (very healthy) observed rate."""
        if self.pending_count == 0:
            return None
        return self.escalated_count / self.pending_count


class ImprovementEngine:
    def __init__(self, orchestrator=None, escalation_tracker: EscalationTracker | None = None) -> None:
        from orchestrator.orchestrator import get_shared_orchestrator

        self._orchestrator = orchestrator or get_shared_orchestrator()
        self._escalation = escalation_tracker or EscalationTracker(self._orchestrator.events)

    async def current_escalate_rate(self) -> Optional[float]:
        """Public accessor for `improvement/apply.py::review_pending_actions`
        — re-checking whether a past problem persists shouldn't need to
        reach into this engine's internal `EscalationTracker`."""
        await self._escalation.start()
        return self._escalation.escalate_rate()

    async def analyze(self) -> list[ImprovementRecommendation]:
        from api.config import settings

        await self._escalation.start()
        recommendations: list[ImprovementRecommendation] = []

        # ── Category 1: workflow escalation rate vs. CONFIDENCE_THRESHOLD_DEFAULT ──
        rate = self._escalation.escalate_rate()
        if rate is not None and self._escalation.pending_count >= settings.IMPROVEMENT_MIN_SAMPLES:
            evidence = {
                "escalate_rate": rate,
                "pending_count": self._escalation.pending_count,
                "escalated_count": self._escalation.escalated_count,
                "current_threshold": settings.CONFIDENCE_THRESHOLD_DEFAULT,
            }
            if rate > settings.IMPROVEMENT_ESCALATE_RATE_HIGH:
                new_value = max(
                    settings.IMPROVEMENT_CONFIDENCE_MIN,
                    round(settings.CONFIDENCE_THRESHOLD_DEFAULT - settings.IMPROVEMENT_CONFIDENCE_STEP, 4),
                )
                if new_value != settings.CONFIDENCE_THRESHOLD_DEFAULT:
                    recommendations.append(ImprovementRecommendation(
                        category="confidence_threshold_too_strict",
                        severity="medium" if rate < 0.5 else "high",
                        evidence=evidence,
                        suggestion=(
                            f"Escalate rate {rate:.2%} melebihi ambang sehat "
                            f"({settings.IMPROVEMENT_ESCALATE_RATE_HIGH:.0%}) dari "
                            f"{self._escalation.pending_count} workflow. Turunkan "
                            f"CONFIDENCE_THRESHOLD_DEFAULT dari {settings.CONFIDENCE_THRESHOLD_DEFAULT} "
                            f"ke {new_value}."
                        ),
                        setting="CONFIDENCE_THRESHOLD_DEFAULT",
                        suggested_value=new_value,
                    ))
            elif rate < settings.IMPROVEMENT_ESCALATE_RATE_LOW:
                new_value = min(
                    settings.IMPROVEMENT_CONFIDENCE_MAX,
                    round(settings.CONFIDENCE_THRESHOLD_DEFAULT + settings.IMPROVEMENT_CONFIDENCE_STEP, 4),
                )
                if new_value != settings.CONFIDENCE_THRESHOLD_DEFAULT:
                    recommendations.append(ImprovementRecommendation(
                        category="confidence_threshold_too_lax",
                        severity="low",
                        evidence=evidence,
                        suggestion=(
                            f"Escalate rate {rate:.2%} jauh di bawah ambang bawah "
                            f"({settings.IMPROVEMENT_ESCALATE_RATE_LOW:.0%}) dari "
                            f"{self._escalation.pending_count} workflow — mungkin terlalu longgar. "
                            f"Naikkan CONFIDENCE_THRESHOLD_DEFAULT dari {settings.CONFIDENCE_THRESHOLD_DEFAULT} "
                            f"ke {new_value}."
                        ),
                        setting="CONFIDENCE_THRESHOLD_DEFAULT",
                        suggested_value=new_value,
                    ))

        # ── Category 2: per-role error rate (informational — no whitelisted
        # setting maps to "fix this role's prompt/provider", so this can
        # never be auto-applied; a human reads it and decides). ──
        error_rates = self._orchestrator.metrics.error_rate_by_role()
        totals_by_role = self._orchestrator.metrics.total_dispatches_by_role()
        for role, err_rate in error_rates.items():
            total = totals_by_role.get(role, 0)
            if total < settings.IMPROVEMENT_MIN_SAMPLES:
                continue
            if err_rate > settings.IMPROVEMENT_ESCALATE_RATE_HIGH:
                recommendations.append(ImprovementRecommendation(
                    category="role_error_rate",
                    severity="high" if err_rate > 0.5 else "medium",
                    evidence={"role": role, "error_rate": err_rate, "samples": total},
                    suggestion=(
                        f"Role '{role}' punya error rate {err_rate:.2%} dari {total} dispatch — "
                        "tinjau prompt/provider/fallback untuk role ini secara manual "
                        "(tidak ada setting whitelisted untuk auto-perbaiki ini)."
                    ),
                    setting=None,
                    suggested_value=None,
                ))

        return recommendations
