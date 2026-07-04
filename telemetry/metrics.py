"""Metrics (MASTER_INSTRUCTION.md Bab 34) — counts, error rate, latency percentiles.

Subscribes to ``agent.*``/``workflow.*`` events (Bab 23 prinsip 1) — zero
direct coupling to Dispatcher/Orchestrator. One dispatch attempt's latency is
measured from its ``agent.running`` to the next ``agent.completed``/
``agent.failed`` for the same ``(trace_id, task_id)``; end-to-end workflow
latency is measured from ``workflow.pending`` to ``workflow.completed``/
``failed``/``cancelled`` for the same ``trace_id`` (Bab 33 rule 1 — every
request type gets a measurable latency).

In-process only (no Redis backend): metrics are meant to be scraped/read
within the same process that's running the workflows, same assumption
``TaskManager``'s in-memory default already makes — persistence across
restarts isn't the point here, current behavior is (Bab 35 dashboards read
live, not historical, snapshots).
"""
from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from core.utils.logger import get_logger
from messaging import EventBus
from messaging.schemas import Event

logger = get_logger(__name__)

_TERMINAL_AGENT_EVENTS = ("agent.completed", "agent.failed")
_TERMINAL_WORKFLOW_EVENTS = ("workflow.completed", "workflow.failed", "workflow.cancelled")


def percentile(samples: list[float], p: float) -> float:
    """``p`` in ``[0, 100]``; linear interpolation between the closest ranks."""
    if not samples:
        return 0.0
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    rank = (p / 100) * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    frac = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * frac


@dataclass
class _Samples:
    values: list[float] = field(default_factory=list)

    def add(self, value: float, cap: int) -> None:
        self.values.append(value)
        if len(self.values) > cap:
            del self.values[: len(self.values) - cap]


class MetricsCollector:
    """In-process counters + latency samples, keyed by role/provider/workflow mode."""

    def __init__(self, event_bus: EventBus | None = None, max_samples: int | None = None) -> None:
        from api.config import settings

        self._events = event_bus or EventBus()
        self._max_samples = settings.METRICS_MAX_SAMPLES if max_samples is None else max_samples
        self._started = False
        self.counts: Counter = Counter()
        self._agent_latency: dict[str, _Samples] = defaultdict(_Samples)
        self._workflow_latency: dict[str, _Samples] = defaultdict(_Samples)
        self._agent_running_at: dict[tuple[str, str], float] = {}
        self._workflow_started_at: dict[str, tuple[float, str]] = {}
        # Per-provider/per-role outcome tallies (Bab 62 Provider Dashboard —
        # "tingkat error per provider" needs this breakdown; the flat `counts`
        # Counter above only has totals across every provider/role combined.
        self._provider_outcomes: dict[str, Counter] = defaultdict(Counter)
        self._role_outcomes: dict[str, Counter] = defaultdict(Counter)

    async def start(self) -> None:
        """Subscribe to the Event Bus. Idempotent — safe to call more than once."""
        if self._started:
            return
        await self._events.subscribe("agent.*", self._on_agent_event)
        await self._events.subscribe("workflow.*", self._on_workflow_event)
        self._started = True

    async def _on_agent_event(self, event: Event) -> None:
        self.counts[event.event_type] += 1
        task_id = event.payload.get("task_id")
        if task_id is None:
            return

        if event.event_type == "agent.running":
            self._agent_running_at[(event.trace_id, task_id)] = time.monotonic()
            return

        if event.event_type not in _TERMINAL_AGENT_EVENTS:
            return

        role = event.payload.get("role", "unknown")
        provider = event.payload.get("provider", "unknown")
        self._role_outcomes[role][event.event_type] += 1
        self._provider_outcomes[provider][event.event_type] += 1

        start = self._agent_running_at.pop((event.trace_id, task_id), None)
        if start is None:
            return
        elapsed_ms = (time.monotonic() - start) * 1000
        self._agent_latency[f"role:{role}"].add(elapsed_ms, self._max_samples)
        self._agent_latency[f"provider:{provider}"].add(elapsed_ms, self._max_samples)

    async def _on_workflow_event(self, event: Event) -> None:
        self.counts[event.event_type] += 1
        if event.event_type == "workflow.pending":
            mode = event.payload.get("mode", "unknown")
            self._workflow_started_at[event.trace_id] = (time.monotonic(), mode)
        elif event.event_type in _TERMINAL_WORKFLOW_EVENTS:
            started = self._workflow_started_at.pop(event.trace_id, None)
            if started is None:
                return
            start_time, mode = started
            elapsed_ms = (time.monotonic() - start_time) * 1000
            self._workflow_latency[mode].add(elapsed_ms, self._max_samples)
            self._workflow_latency["_all"].add(elapsed_ms, self._max_samples)

    def error_rate(self) -> float:
        """Fraction of terminal agent dispatches that failed (Bab 34 — Failure Rate)."""
        completed = self.counts.get("agent.completed", 0)
        failed = self.counts.get("agent.failed", 0)
        total = completed + failed
        return failed / total if total else 0.0

    def error_rate_by_provider(self) -> dict[str, float]:
        """Per-provider error rate (Bab 62 Provider Dashboard)."""
        return {
            provider: outcomes.get("agent.failed", 0) / total
            for provider, outcomes in self._provider_outcomes.items()
            if (total := outcomes.get("agent.completed", 0) + outcomes.get("agent.failed", 0)) > 0
        }

    def error_rate_by_role(self) -> dict[str, float]:
        """Per-role error rate (Bab 62 Agent Dashboard — "tingkat keberhasilan per agent")."""
        return {
            role: outcomes.get("agent.failed", 0) / total
            for role, outcomes in self._role_outcomes.items()
            if (total := outcomes.get("agent.completed", 0) + outcomes.get("agent.failed", 0)) > 0
        }

    def success_rate(self) -> float:
        """Fraction of terminal workflows that completed, vs failed/cancelled (Bab 34 — Success
        Rate). Approximation: doesn't distinguish "completed after Human Approval" from
        "completed without ever escalating" — reconstructing that needs per-trace
        correlation (see :mod:`telemetry.tracing`), not a flat counter."""
        completed = self.counts.get("workflow.completed", 0)
        failed = self.counts.get("workflow.failed", 0)
        cancelled = self.counts.get("workflow.cancelled", 0)
        total = completed + failed + cancelled
        return completed / total if total else 0.0

    def agent_latency_percentiles(self, key: str, percentiles: tuple[int, ...] = (50, 95, 99)) -> dict[str, float]:
        samples = self._agent_latency.get(key)
        values = samples.values if samples else []
        return {f"p{p}": percentile(values, p) for p in percentiles}

    def agent_latency_keys(self, prefix: str = "") -> list[str]:
        """Known ``agent_latency_percentiles`` keys, optionally filtered by prefix
        (``"role:"`` or ``"provider:"``) — lets dashboards enumerate without
        reaching into this collector's internals."""
        return [key for key in self._agent_latency if key.startswith(prefix)]

    def workflow_latency_percentiles(
        self, mode: str = "_all", percentiles: tuple[int, ...] = (50, 95, 99)
    ) -> dict[str, float]:
        samples = self._workflow_latency.get(mode)
        values = samples.values if samples else []
        return {f"p{p}": percentile(values, p) for p in percentiles}

    def snapshot(self) -> dict:
        """Everything at a glance — the data behind the Bab 62 Latency/Agent dashboards."""
        return {
            "counts": dict(self.counts),
            "error_rate": self.error_rate(),
            "error_rate_by_provider": self.error_rate_by_provider(),
            "error_rate_by_role": self.error_rate_by_role(),
            "success_rate": self.success_rate(),
            "workflow_latency_ms": self.workflow_latency_percentiles(),
        }
