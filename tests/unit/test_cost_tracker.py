"""Unit tests for Cost Tracking (Bab 27, 34, 56) — no live services (Bab 12.3)."""
import datetime as dt

import pytest

from memory.stores import InMemoryListStore
from messaging import EventBus, InMemoryBroker
from telemetry.cost_tracker import CostTracker, estimate_cost, price_for


@pytest.fixture
def bus():
    return EventBus(InMemoryBroker())


# ─── Pricing ───────────────────────────────────────────────────────────────

def test_price_for_known_model():
    prompt_price, completion_price = price_for("openai", "gpt-4o")
    assert prompt_price > 0 and completion_price > 0


def test_price_for_unknown_model_is_free():
    assert price_for("ollama", "gemma4:e2b") == (0.0, 0.0)


def test_estimate_cost_known_model():
    cost = estimate_cost("openai", "gpt-4o", prompt_tokens=1000, completion_tokens=500)
    prompt_price, completion_price = price_for("openai", "gpt-4o")
    assert cost == pytest.approx(prompt_price + completion_price * 0.5)


def test_estimate_cost_unknown_model_is_zero():
    assert estimate_cost("ollama", "gemma4:e2b", 100000, 100000) == 0.0


# ─── CostTracker ───────────────────────────────────────────────────────────

async def test_cost_tracker_records_from_agent_completed_event(bus):
    tracker = CostTracker(event_bus=bus, store=InMemoryListStore())
    await tracker.start()

    await bus.emit(
        "agent.completed",
        source="writer-1",
        trace_id="t1",
        payload={
            "task_id": "task-1",
            "role": "writer",
            "provider": "openai",
            "model": "gpt-4o",
            "prompt_tokens": 1000,
            "completion_tokens": 500,
        },
    )

    cost = await tracker.cost_for_trace("t1")
    assert cost == pytest.approx(estimate_cost("openai", "gpt-4o", 1000, 500))


async def test_cost_tracker_isolates_by_trace_id(bus):
    tracker = CostTracker(event_bus=bus, store=InMemoryListStore())
    await tracker.start()

    for trace_id in ("t1", "t2"):
        await bus.emit(
            "agent.completed",
            source="writer-1",
            trace_id=trace_id,
            payload={"role": "writer", "provider": "openai", "model": "gpt-4o", "prompt_tokens": 1000, "completion_tokens": 0},
        )

    assert await tracker.cost_for_trace("t1") == await tracker.cost_for_trace("t2")
    assert await tracker.total_cost() == pytest.approx(2 * await tracker.cost_for_trace("t1"))


async def test_cost_by_provider_and_role(bus):
    tracker = CostTracker(event_bus=bus, store=InMemoryListStore())
    await tracker.start()

    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"role": "writer", "provider": "openai", "model": "gpt-4o", "prompt_tokens": 1000, "completion_tokens": 0},
    )
    await bus.emit(
        "agent.completed", source="b", trace_id="t1",
        payload={"role": "analyst", "provider": "claude", "model": "claude-sonnet-5", "prompt_tokens": 1000, "completion_tokens": 0},
    )

    by_provider = await tracker.cost_by_provider()
    by_role = await tracker.cost_by_role()
    assert set(by_provider) == {"openai", "claude"}
    assert set(by_role) == {"writer", "analyst"}


async def test_cost_for_day_filters_by_date(bus):
    tracker = CostTracker(event_bus=bus, store=InMemoryListStore())
    await tracker.start()

    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"role": "writer", "provider": "openai", "model": "gpt-4o", "prompt_tokens": 1000, "completion_tokens": 0},
    )

    today = dt.datetime.now(dt.timezone.utc).date()
    yesterday = today - dt.timedelta(days=1)
    assert await tracker.cost_for_day(today) > 0
    assert await tracker.cost_for_day(yesterday) == 0.0


async def test_unknown_provider_model_records_zero_cost(bus):
    tracker = CostTracker(event_bus=bus, store=InMemoryListStore())
    await tracker.start()

    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"role": "memory", "provider": "ollama", "model": "gemma4:e2b", "prompt_tokens": 5000, "completion_tokens": 5000},
    )

    assert await tracker.cost_for_trace("t1") == 0.0


async def test_start_is_idempotent(bus):
    tracker = CostTracker(event_bus=bus, store=InMemoryListStore())
    await tracker.start()
    await tracker.start()

    await bus.emit(
        "agent.completed", source="a", trace_id="t1",
        payload={"role": "writer", "provider": "openai", "model": "gpt-4o", "prompt_tokens": 1000, "completion_tokens": 0},
    )
    single = estimate_cost("openai", "gpt-4o", 1000, 0)
    assert await tracker.cost_for_trace("t1") == pytest.approx(single)
