"""Unit tests for Metrics (Bab 34) — no live services (Bab 12.3)."""
import pytest

from messaging import EventBus, InMemoryBroker
from telemetry.metrics import MetricsCollector, percentile


@pytest.fixture
def bus():
    return EventBus(InMemoryBroker())


# ─── percentile() ─────────────────────────────────────────────────────────────

def test_percentile_empty_returns_zero():
    assert percentile([], 50) == 0.0


def test_percentile_single_value():
    assert percentile([42.0], 95) == 42.0


def test_percentile_median_of_odd_count():
    assert percentile([1.0, 2.0, 3.0], 50) == 2.0


def test_percentile_p100_is_max():
    assert percentile([1.0, 5.0, 3.0], 100) == 5.0


# ─── MetricsCollector: agent lifecycle ────────────────────────────────────────

async def test_agent_completed_records_latency_and_counts(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()

    await bus.emit("agent.running", source="writer-1", trace_id="t1", payload={"task_id": "task-1", "role": "writer"})
    await bus.emit(
        "agent.completed",
        source="writer-1",
        trace_id="t1",
        payload={"task_id": "task-1", "role": "writer", "provider": "openai"},
    )

    assert m.counts["agent.completed"] == 1
    assert m.error_rate() == 0.0
    p = m.agent_latency_percentiles("role:writer")
    assert p["p50"] >= 0.0


async def test_agent_failed_increments_error_rate(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()

    await bus.emit("agent.running", source="writer-1", trace_id="t1", payload={"task_id": "task-1", "role": "writer"})
    await bus.emit(
        "agent.failed",
        source="writer-1",
        trace_id="t1",
        payload={"task_id": "task-1", "role": "writer", "provider": "openai", "error": "boom"},
    )

    assert m.error_rate() == 1.0
    assert m.error_rate_by_provider()["openai"] == 1.0
    assert m.error_rate_by_role()["writer"] == 1.0


async def test_agent_event_without_task_id_is_ignored(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()

    await bus.emit("agent.assigned", source="writer-1", trace_id="t1", payload={"role": "writer"})

    assert m.counts["agent.assigned"] == 1
    assert m.agent_latency_keys() == []


async def test_completed_without_running_does_not_crash(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()

    await bus.emit(
        "agent.completed",
        source="writer-1",
        trace_id="t1",
        payload={"task_id": "task-1", "role": "writer", "provider": "openai"},
    )

    assert m.counts["agent.completed"] == 1
    assert m.agent_latency_percentiles("role:writer") == {"p50": 0.0, "p95": 0.0, "p99": 0.0}


# ─── MetricsCollector: workflow lifecycle ─────────────────────────────────────

async def test_workflow_completed_records_latency_by_mode(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()

    await bus.emit("workflow.pending", source="orchestrator", trace_id="t1", payload={"mode": "sequential"})
    await bus.emit("workflow.completed", source="orchestrator", trace_id="t1", payload={})

    assert m.counts["workflow.completed"] == 1
    assert m.workflow_latency_percentiles("sequential")["p50"] >= 0.0
    assert m.workflow_latency_percentiles()["p50"] >= 0.0  # "_all"


async def test_success_rate_mix_of_outcomes(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()

    for trace_id in ("t1", "t2", "t3"):
        await bus.emit("workflow.pending", source="o", trace_id=trace_id, payload={"mode": "sequential"})
    await bus.emit("workflow.completed", source="o", trace_id="t1", payload={})
    await bus.emit("workflow.completed", source="o", trace_id="t2", payload={})
    await bus.emit("workflow.failed", source="o", trace_id="t3", payload={})

    assert m.success_rate() == pytest.approx(2 / 3)


async def test_snapshot_shape(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()
    snap = m.snapshot()
    assert set(snap) == {
        "counts",
        "error_rate",
        "error_rate_by_provider",
        "error_rate_by_role",
        "success_rate",
        "workflow_latency_ms",
    }


async def test_start_is_idempotent(bus):
    m = MetricsCollector(event_bus=bus)
    await m.start()
    await m.start()

    await bus.emit(
        "agent.completed",
        source="a",
        trace_id="t1",
        payload={"task_id": "task-1", "role": "writer", "provider": "openai"},
    )
    assert m.counts["agent.completed"] == 1  # not double-counted
