"""Monitoring (MASTER_INSTRUCTION.md Bab 35) — aggregates telemetry into dashboards + alerts.

Bab 62 lists eight minimum dashboards; this module builds each one's data from
:mod:`telemetry.metrics`, :mod:`telemetry.cost_tracker`, and
:mod:`telemetry.tracing` plus the existing Agent/Task Manager registries —
dependency-injected (explicit args), not read from hidden globals, so callers
control which orchestrator/registry instance a dashboard reflects. Bab 62's
rule ("every dashboard must share one source of truth with alerting") is
satisfied by :func:`check_alerts` reading these same functions' output rather
than a separate metrics path.

``check_readiness`` is the same check ``api/routes/health.py``'s ``/ready``
exposes — defined here so the route and :func:`health_dashboard` can't drift
into two different answers for "is the system up" (Bab 35 rule 3).

No UI/frontend and no alert-delivery channel (Slack/email/pager) are built
here — these functions return structured data for a future API route or
dashboard frontend to render, and for a future paging integration to consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.utils.logger import get_logger
from registry.agent_registry import AgentRegistry

from .cost_tracker import CostTracker
from .metrics import MetricsCollector

logger = get_logger(__name__)


async def check_readiness() -> dict:
    """DB/Redis/Ollama/cloud-provider connectivity (Bab 35 rule 3).

    Single source of truth for both ``GET /health/ready`` and
    :func:`health_dashboard` — checking each provider LLM's connectivity, not
    just Ollama, is the part Bab 35 rule 3 explicitly calls for.
    """
    from core.ai.gemma_client import gemma
    from db.connection import get_db_status
    from providers.provider_factory import create_provider
    from registry.provider_registry import list_enabled_providers

    checks: dict[str, object] = {"database": await get_db_status()}

    try:
        import redis.asyncio as aioredis

        from api.config import settings

        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception as exc:  # connectivity probe — any failure just reports unhealthy
        checks["redis"] = f"error: {exc}"

    checks["ollama"] = await gemma.health_check()

    for name in list_enabled_providers():
        if name == "ollama":
            continue  # already covered by the gemma client check above
        try:
            provider = create_provider(name)
            checks[name] = "ok" if await provider.health_check() else "error: health_check returned false"
        except Exception as exc:
            checks[name] = f"error: {exc}"

    all_ok = (
        checks["database"] == "ok"
        and checks["redis"] == "ok"
        and checks["ollama"].get("ollama") == "ok"
        and all(v == "ok" for key, v in checks.items() if key not in ("database", "redis", "ollama"))
    )
    return {"ready": all_ok, "checks": checks}


def agent_dashboard(registry: AgentRegistry, metrics: MetricsCollector) -> dict:
    """Bab 62 Agent Dashboard: registered agents/roles + per-role success rate."""
    error_by_role = metrics.error_rate_by_role()
    return {
        "agents": registry.list_agents(),
        "roles": registry.list_roles(),
        "success_rate_by_role": {role: 1.0 - rate for role, rate in error_by_role.items()},
        "latency_ms_by_role": {
            role: metrics.agent_latency_percentiles(f"role:{role}")
            for role in registry.list_roles()
        },
    }


def workflow_dashboard(metrics: MetricsCollector) -> dict:
    """Bab 62 Workflow Dashboard: workflow state counts, duration, escalation rate.

    Known gap: TaskManager doesn't expose "list every currently-tracked id"
    (its store contract is get/save-by-id only, and adding an enumeration
    means a Redis SCAN for the RedisTaskStore backend) — so this reports
    aggregate counts/durations from completed events, not a live list of
    in-flight workflows. Good enough for rates and durations; not for "what's
    running right now."
    """
    counts = metrics.counts
    reviewing = counts.get("workflow.reviewing", 0)
    completed = counts.get("workflow.completed", 0)
    failed = counts.get("workflow.failed", 0)
    pending = counts.get("workflow.pending", 0)
    return {
        "state_counts": {
            state: counts.get(f"workflow.{state}", 0)
            for state in ("pending", "planning", "executing", "reviewing", "approved", "completed", "failed", "cancelled")
        },
        "escalation_rate": reviewing / pending if pending else 0.0,
        "success_rate": metrics.success_rate(),
        "avg_duration_ms": metrics.workflow_latency_percentiles()["p50"],
        "by_mode": {
            mode: metrics.workflow_latency_percentiles(mode)
            for mode in ("sequential", "parallel", "reflection", "voting", "consensus")
        },
        "_note": "state_counts/completed/failed are lifetime totals, not a live in-flight list",
        "completed": completed,
        "failed": failed,
    }


async def provider_dashboard(metrics: MetricsCollector) -> dict:
    """Bab 62 Provider Dashboard: health, error rate, latency per provider.

    Circuit Breaker status (Bab 55) isn't included — that pattern isn't
    implemented in this codebase yet (Dispatcher does retry + fallback, Bab
    54, but no breaker state machine); a gap for a future session, not
    silently faked here.
    """
    readiness = await check_readiness()
    provider_health = {k: v for k, v in readiness["checks"].items() if k not in ("database", "redis")}
    error_rates = metrics.error_rate_by_provider()
    return {
        "health": provider_health,
        "error_rate": error_rates,
        "latency_ms": {
            provider: metrics.agent_latency_percentiles(f"provider:{provider}")
            for provider in error_rates
        },
    }


async def cost_dashboard(costs: CostTracker) -> dict:
    """Bab 62 Cost Dashboard: cost per provider/agent/day."""
    return {
        "total_usd": await costs.total_cost(),
        "today_usd": await costs.cost_for_day(),
        "by_provider_usd": await costs.cost_by_provider(),
        "by_role_usd": await costs.cost_by_role(),
    }


async def memory_dashboard(vector_memory) -> dict:
    """Bab 62 Memory Dashboard: tier sizes.

    Only Vector Memory exposes a count today (``VectorMemory.count()``,
    Tahap 5); working/conversation/summary/long-term stores have no
    enumeration method (adding one to every tier is a bigger change than
    this dashboard warrants) — reported as ``None`` rather than guessed.
    """
    return {
        "working_entries": None,
        "conversation_sessions": None,
        "summary_scopes": None,
        "long_term_facts": None,
        "vector_entries": await vector_memory.count(),
    }


def latency_dashboard(metrics: MetricsCollector) -> dict:
    """Bab 62 Latency Dashboard: p50/p95/p99 end-to-end and per role/provider."""
    return {
        "end_to_end_ms": metrics.workflow_latency_percentiles(),
        "by_role_ms": {
            key.removeprefix("role:"): metrics.agent_latency_percentiles(key)
            for key in metrics.agent_latency_keys("role:")
        },
        "by_provider_ms": {
            key.removeprefix("provider:"): metrics.agent_latency_percentiles(key)
            for key in metrics.agent_latency_keys("provider:")
        },
    }


async def health_dashboard() -> dict:
    """Bab 62 Health Dashboard: same data as ``GET /health/ready``."""
    return await check_readiness()


async def queue_dashboard(queue_names: tuple[str, ...] = ("ai_queue", "gis_queue", "pipeline_queue")) -> dict:
    """Bab 62 Queue Dashboard: RQ (legacy pipeline) + TaskQueue (v4-native) lengths.

    Both are reported because they're genuinely two different mechanisms
    sharing this codebase today (CLAUDE.md §4) — RQ is what `worker_ai`/
    `worker_gis` actually consume; `messaging.TaskQueue` is the newer
    orchestrator-native path nothing has started publishing to yet, so it
    will legitimately read zero until something does.
    """
    from api.config import settings
    from messaging import TaskQueue

    result: dict[str, dict] = {}
    try:
        import redis as sync_redis
        from rq import Queue

        conn = sync_redis.from_url(settings.REDIS_URL)
        for name in queue_names:
            q = Queue(name, connection=conn)
            result[name] = {"rq_length": len(q), "rq_failed": q.failed_job_registry.count}
    except Exception as exc:
        logger.warning("queue_dashboard.rq_unavailable", error=str(exc))
        for name in queue_names:
            result.setdefault(name, {})["rq_error"] = str(exc)

    for name in queue_names:
        result.setdefault(name, {})["task_queue_length"] = await TaskQueue(name).size()

    return result


@dataclass(frozen=True)
class Alert:
    """One threshold breach (Bab 35 rule 2)."""

    kind: str
    message: str
    value: float
    threshold: float


async def check_alerts(metrics: MetricsCollector, costs: CostTracker) -> list[Alert]:
    """Evaluate the Bab 35 rule 2 conditions against current metrics/cost.

    Reads the exact same :class:`MetricsCollector`/:class:`CostTracker`
    instances the dashboards above use — one source of truth for alerting and
    dashboards, per Bab 62's closing rule. Returns data only; there's no
    paging/notification channel wired up to actually deliver these.
    """
    from api.config import settings

    alerts: list[Alert] = []

    error_rate = metrics.error_rate()
    if error_rate > settings.ALERT_ERROR_RATE_THRESHOLD:
        alerts.append(
            Alert(
                kind="error_rate",
                message=f"agent error rate {error_rate:.1%} exceeds threshold",
                value=error_rate,
                threshold=settings.ALERT_ERROR_RATE_THRESHOLD,
            )
        )

    p95 = metrics.workflow_latency_percentiles()["p95"]
    if p95 > settings.ALERT_LATENCY_P95_MS:
        alerts.append(
            Alert(
                kind="latency_p95",
                message=f"workflow p95 latency {p95:.0f}ms exceeds budget",
                value=p95,
                threshold=settings.ALERT_LATENCY_P95_MS,
            )
        )

    daily_cost = await costs.cost_for_day()
    if daily_cost > settings.COST_BUDGET_DAILY:
        alerts.append(
            Alert(
                kind="daily_cost",
                message=f"daily cost ${daily_cost:.2f} exceeds budget",
                value=daily_cost,
                threshold=settings.COST_BUDGET_DAILY,
            )
        )

    return alerts
