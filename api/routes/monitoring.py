"""Monitoring API — exposes `telemetry/monitoring.py`'s dashboards (Bab 62)
over HTTP for the Monitoring page. Not a protected folder (Bab 45.1).

Reuses the same `Orchestrator` singleton as `api/routes/orchestrator.py`
(not a fresh `CostTracker`/`MetricsCollector`/`Tracer`) so this reflects
whatever telemetry real `/run` calls have actually recorded in this process —
the same "one source of truth" rule Bab 62 requires between dashboards and
alerting (`telemetry/monitoring.py` module docstring).

Memory Dashboard (Bab 62) is intentionally omitted here: `memory_dashboard()`
needs a `VectorMemory` instance, and there is no memory_manager singleton
wired into `Orchestrator`/`ChatEngine` anywhere in the app today — nothing
populates it from real chat/workflow traffic. Every field but
`vector_entries` is hardcoded `None` in the source, and `vector_entries`
would only ever read 0 from a throwaway instance built just for this route.
Wiring memory data up meaningfully is a Memory-page-level integration
decision, not a one-line addition here.

Authentication (Tahap 26): both routes now require
`require_role("view_dashboard")` — the first real enforcement of that
action, defined in `security/permissions.py` since Tahap 7 (ADR-0010) but
never wired to a route until now (every role already includes it, so this
is "must be authenticated when API_KEYS is configured", same posture as
`api/routes/files.py`/`knowledge.py` — no role currently lacks
`view_dashboard`, so this isn't a finer-grained gate yet, just the first
real caller of the mechanism).

Security + Audit Dashboards (Bab 68 Backlog Prioritas 13, Tahap 34):
`monitoring.security_dashboard()`/`audit_dashboard()` read
`security/audit_log.py`'s file-based trail directly (no orchestrator
singleton involved, unlike every other dashboard here) — gated by the
same `view_dashboard` permission, no new RBAC action needed.
"""
from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.orchestrator import _orchestrator
from db.connection import get_session
from security.auth import Principal
from security.permissions import require_role
from telemetry import monitoring

router = APIRouter()


@router.get("/dashboard")
async def dashboard(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(require_role("view_dashboard")),
):
    """Bab 62 dashboards — Agent, Workflow, Provider, Cost, Latency, Health,
    Queue, Workspace (Bab 69.14, Tahap 19; Memory excluded, see module docstring),
    plus Security/Audit (Bab 68 Backlog Prioritas 13, Tahap 34)."""
    await _orchestrator._ensure_telemetry_started()
    return {
        "agent": monitoring.agent_dashboard(_orchestrator.agents, _orchestrator.metrics),
        "workflow": monitoring.workflow_dashboard(_orchestrator.metrics),
        "provider": await monitoring.provider_dashboard(_orchestrator.metrics),
        "cost": await monitoring.cost_dashboard(_orchestrator.costs),
        "latency": monitoring.latency_dashboard(_orchestrator.metrics),
        "health": await monitoring.health_dashboard(),
        "queue": await monitoring.queue_dashboard(),
        "workspace": await monitoring.workspace_dashboard(session),
        "security": monitoring.security_dashboard(),
        "audit": monitoring.audit_dashboard(),
    }


@router.get("/alerts")
async def alerts(principal: Principal = Depends(require_role("view_dashboard"))):
    """Bab 35 rule 2 threshold checks — same metrics/costs instances as `/dashboard` (one source of truth)."""
    await _orchestrator._ensure_telemetry_started()
    triggered = await monitoring.check_alerts(_orchestrator.metrics, _orchestrator.costs)
    return {"alerts": [asdict(a) for a in triggered]}
