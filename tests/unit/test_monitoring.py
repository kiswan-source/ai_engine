"""Unit tests for Monitoring dashboards + alerts (Bab 35, 62) — no live services (Bab 12.3).

check_readiness()/health_dashboard()/provider_dashboard()/queue_dashboard()
need a live DB/Redis/provider/RQ connection and are verified live instead —
same precedent as PostgresConversationStore/PostgresLongTermStore (Tahap 3).
"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import Workspace, WorkspaceFolder
from memory.vector_memory import VectorMemory
from messaging import EventBus, InMemoryBroker
from registry.agent_registry import AgentRegistry
from telemetry.cost_tracker import CostTracker
from telemetry.metrics import MetricsCollector
from telemetry import monitoring


@pytest.fixture
def bus():
    return EventBus(InMemoryBroker())


class _StubAgent:
    def __init__(self, role):
        self.role = role
        self.agent_id = f"{role}-stub"


def _registry_with(*roles):
    reg = AgentRegistry()
    for role in roles:
        reg.register(_StubAgent(role))
    return reg


async def test_agent_dashboard_reports_roles_and_success_rate(bus):
    metrics = MetricsCollector(event_bus=bus)
    await metrics.start()
    await bus.emit("agent.running", source="a", trace_id="t1", payload={"task_id": "1", "role": "writer"})
    await bus.emit(
        "agent.failed", source="a", trace_id="t1",
        payload={"task_id": "1", "role": "writer", "provider": "openai"},
    )

    dashboard = monitoring.agent_dashboard(_registry_with("writer"), metrics)
    assert dashboard["roles"] == ["writer"]
    assert dashboard["success_rate_by_role"]["writer"] == 0.0


async def test_workflow_dashboard_reports_state_counts_and_escalation(bus):
    metrics = MetricsCollector(event_bus=bus)
    await metrics.start()
    await bus.emit("workflow.pending", source="o", trace_id="t1", payload={"mode": "sequential"})
    await bus.emit("workflow.reviewing", source="o", trace_id="t1", payload={})
    await bus.emit("workflow.completed", source="o", trace_id="t1", payload={})

    dashboard = monitoring.workflow_dashboard(metrics)
    assert dashboard["state_counts"]["completed"] == 1
    assert dashboard["state_counts"]["reviewing"] == 1
    assert dashboard["escalation_rate"] == 1.0


async def test_cost_dashboard_aggregates(bus):
    from memory.stores import InMemoryListStore

    costs = CostTracker(event_bus=bus, store=InMemoryListStore())
    await costs.start()
    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"role": "writer", "provider": "openai", "model": "gpt-4o", "prompt_tokens": 1000, "completion_tokens": 0},
    )

    dashboard = await monitoring.cost_dashboard(costs)
    assert dashboard["total_usd"] > 0
    assert dashboard["by_provider_usd"]["openai"] > 0
    assert dashboard["by_role_usd"]["writer"] > 0


async def test_memory_dashboard_reports_vector_count():
    vm = VectorMemory()
    await vm.add("contoh dokumen")

    dashboard = await monitoring.memory_dashboard(vm)
    assert dashboard["vector_entries"] == 1
    assert dashboard["working_entries"] is None


async def test_latency_dashboard_reports_role_and_provider_breakdown(bus):
    metrics = MetricsCollector(event_bus=bus)
    await metrics.start()
    await bus.emit("agent.running", source="a", trace_id="t1", payload={"task_id": "1", "role": "writer"})
    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"task_id": "1", "role": "writer", "provider": "openai"},
    )

    dashboard = monitoring.latency_dashboard(metrics)
    assert "writer" in dashboard["by_role_ms"]
    assert "openai" in dashboard["by_provider_ms"]


# ─── Alerts ────────────────────────────────────────────────────────────────

async def test_check_alerts_error_rate_threshold(bus, monkeypatch):
    from memory.stores import InMemoryListStore

    monkeypatch.setattr("api.config.settings.ALERT_ERROR_RATE_THRESHOLD", 0.1)
    metrics = MetricsCollector(event_bus=bus)
    costs = CostTracker(event_bus=bus, store=InMemoryListStore())
    await metrics.start()
    await costs.start()

    await bus.emit("agent.running", source="a", trace_id="t1", payload={"task_id": "1", "role": "writer"})
    await bus.emit("agent.failed", source="a", trace_id="t1", payload={"task_id": "1", "role": "writer", "provider": "openai"})

    alerts = await monitoring.check_alerts(metrics, costs)
    assert any(a.kind == "error_rate" for a in alerts)


async def test_check_alerts_daily_cost_threshold(bus, monkeypatch):
    from memory.stores import InMemoryListStore

    monkeypatch.setattr("api.config.settings.COST_BUDGET_DAILY", 0.0001)
    metrics = MetricsCollector(event_bus=bus)
    costs = CostTracker(event_bus=bus, store=InMemoryListStore())
    await metrics.start()
    await costs.start()

    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"role": "writer", "provider": "openai", "model": "gpt-4o", "prompt_tokens": 1000, "completion_tokens": 0},
    )

    alerts = await monitoring.check_alerts(metrics, costs)
    assert any(a.kind == "daily_cost" for a in alerts)


async def test_check_alerts_none_when_under_thresholds(bus):
    from memory.stores import InMemoryListStore

    metrics = MetricsCollector(event_bus=bus)
    costs = CostTracker(event_bus=bus, store=InMemoryListStore())
    await metrics.start()
    await costs.start()

    alerts = await monitoring.check_alerts(metrics, costs)
    assert alerts == []


# ─── workspace_dashboard (Bab 69.14, Tahap 19) ─────────────────────────────

@pytest.fixture
async def sqlite_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Workspace.metadata.create_all, tables=[Workspace.__table__, WorkspaceFolder.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_workspace_dashboard_counts_by_status(sqlite_session):
    session = sqlite_session
    session.add_all(
        [
            Workspace(project_id="p1", status="Active"),
            Workspace(project_id="p2", status="Scanning"),
            Workspace(project_id="p3", status="Error"),
        ]
    )
    await session.commit()

    dashboard = await monitoring.workspace_dashboard(session)
    assert dashboard["total_workspaces"] == 3
    assert dashboard["active"] == 1
    assert dashboard["by_status"] == {"Active": 1, "Scanning": 1, "Indexing": 0, "Error": 1}


async def test_workspace_dashboard_excludes_soft_deleted(sqlite_session):
    from datetime import datetime

    session = sqlite_session
    session.add_all(
        [
            Workspace(project_id="p1", status="Active"),
            Workspace(project_id="p2", status="Active", deleted_at=datetime.utcnow()),
        ]
    )
    await session.commit()

    dashboard = await monitoring.workspace_dashboard(session)
    assert dashboard["total_workspaces"] == 1


async def test_workspace_dashboard_aggregates_folder_scan_counts(sqlite_session, tmp_path):
    (tmp_path / "report.txt").write_text("laporan")
    (tmp_path / "site.png").write_bytes(b"\x89PNG")

    session = sqlite_session
    ws = Workspace(project_id="p1", status="Active")
    session.add(ws)
    await session.flush()
    session.add(WorkspaceFolder(workspace_id=ws.id, source_type="Local", path=str(tmp_path)))
    await session.commit()

    dashboard = await monitoring.workspace_dashboard(session)
    assert dashboard["document_count"] == 1
    assert dashboard["image_count"] == 1
    assert dashboard["total_size_bytes"] > 0
    assert dashboard["errors"] == []


async def test_workspace_dashboard_reports_missing_folder_as_error_not_fatal(sqlite_session):
    session = sqlite_session
    ws = Workspace(project_id="p1", status="Active")
    session.add(ws)
    await session.flush()
    session.add(WorkspaceFolder(workspace_id=ws.id, source_type="Local", path="/no/such/directory"))
    await session.commit()

    dashboard = await monitoring.workspace_dashboard(session)
    assert dashboard["total_workspaces"] == 1
    assert len(dashboard["errors"]) == 1
