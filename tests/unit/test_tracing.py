"""Unit tests for Execution Tracing (Bab 34) — no live services (Bab 12.3)."""
import pytest

from memory.stores import InMemoryListStore
from messaging import EventBus, InMemoryBroker
from telemetry.tracing import Tracer


@pytest.fixture
def bus():
    return EventBus(InMemoryBroker())


async def test_tracer_records_events_for_its_trace_id(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore())
    await tracer.start()

    await bus.emit("agent.assigned", source="writer-1", trace_id="t1", payload={"role": "writer"})
    await bus.emit("agent.running", source="writer-1", trace_id="t1", payload={"role": "writer"})
    await bus.emit("agent.completed", source="writer-1", trace_id="t1", payload={"role": "writer"})
    await bus.emit("workflow.completed", source="orchestrator", trace_id="t1", payload={})

    timeline = await tracer.timeline("t1")
    assert [s.event_type for s in timeline] == [
        "agent.assigned",
        "agent.running",
        "agent.completed",
        "workflow.completed",
    ]
    assert timeline[0].source == "writer-1"


async def test_tracer_isolates_by_trace_id(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore())
    await tracer.start()

    await bus.emit("agent.completed", source="a", trace_id="t1", payload={})
    await bus.emit("agent.completed", source="b", trace_id="t2", payload={})

    assert len(await tracer.timeline("t1")) == 1
    assert len(await tracer.timeline("t2")) == 1


async def test_tracer_ignores_events_without_trace_id(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore())
    await tracer.start()

    await bus.emit("agent.completed", source="a", trace_id="", payload={})

    assert await tracer.timeline("") == []


async def test_tracer_ignores_unmatched_event_types(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore())
    await tracer.start()

    await bus.emit("consensus.decided", source="consensus_engine", trace_id="t1", payload={})
    await bus.emit("memory.written", source="x", trace_id="t1", payload={})

    timeline = await tracer.timeline("t1")
    assert [s.event_type for s in timeline] == ["consensus.decided"]


async def test_tracer_caps_spans_per_trace(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore(), max_spans=3)
    await tracer.start()

    for _ in range(5):
        await bus.emit("agent.running", source="a", trace_id="t1", payload={})

    assert len(await tracer.timeline("t1")) == 3


async def test_tracer_clear(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore())
    await tracer.start()

    await bus.emit("agent.completed", source="a", trace_id="t1", payload={})
    await tracer.clear("t1")

    assert await tracer.timeline("t1") == []


async def test_tracer_start_is_idempotent(bus):
    tracer = Tracer(event_bus=bus, store=InMemoryListStore())
    await tracer.start()
    await tracer.start()  # second call must not double-subscribe

    await bus.emit("agent.completed", source="a", trace_id="t1", payload={})

    assert len(await tracer.timeline("t1")) == 1
