"""Unit tests for the Continuous Improvement Engine's analysis (Fase 7,
DCF v5 mandate) — pure read + detection, no side effects.
"""
import pytest

from improvement.engine import EscalationTracker, ImprovementEngine
from messaging import EventBus, InMemoryBroker
from orchestrator.orchestrator import Orchestrator
from tests.unit.test_orchestrator import registry_with, StubAgent


@pytest.fixture
def bus():
    return EventBus(InMemoryBroker())


@pytest.fixture
async def orch(bus):
    o = Orchestrator(agent_registry=registry_with(StubAgent("writer")), event_bus=bus)
    # Orchestrator.metrics only subscribes to the event bus inside run()/
    # run_single() (via _ensure_telemetry_started) — these tests emit raw
    # events directly without ever calling run(), so start it explicitly.
    await o.metrics.start()
    return o


async def _emit_pending(bus, trace_id):
    await bus.emit("workflow.pending", source="orchestrator", trace_id=trace_id, payload={})


async def _emit_reviewing(bus, trace_id):
    await bus.emit("workflow.reviewing", source="orchestrator", trace_id=trace_id, payload={})


# ─── EscalationTracker ────────────────────────────────────────────────────────

async def test_escalation_tracker_rate_none_with_no_data(bus):
    tracker = EscalationTracker(bus)
    await tracker.start()
    assert tracker.escalate_rate() is None


async def test_escalation_tracker_computes_rate(bus):
    tracker = EscalationTracker(bus)
    await tracker.start()
    for i in range(10):
        await _emit_pending(bus, f"t{i}")
    for i in range(3):
        await _emit_reviewing(bus, f"t{i}")

    assert tracker.escalate_rate() == pytest.approx(0.3)


# ─── ImprovementEngine.analyze() — confidence threshold category ─────────────

async def test_no_recommendation_below_minimum_samples(monkeypatch, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 30)
    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()  # subscribe BEFORE emitting — a subscription never replays past events
    for i in range(10):
        await _emit_pending(bus, f"t{i}")
    for i in range(9):  # 90% escalate rate, but too few samples
        await _emit_reviewing(bus, f"t{i}")

    recs = await engine.analyze()

    assert recs == []


async def test_recommends_lowering_threshold_when_escalate_rate_too_high(monkeypatch, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 10)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.CONFIDENCE_THRESHOLD_DEFAULT", 0.6)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_STEP", 0.05)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)

    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()  # subscribe BEFORE emitting — a subscription never replays past events
    for i in range(20):
        await _emit_pending(bus, f"t{i}")
    for i in range(10):  # 50% escalate rate > 30% high band
        await _emit_reviewing(bus, f"t{i}")

    recs = await engine.analyze()

    threshold_recs = [r for r in recs if r.category == "confidence_threshold_too_strict"]
    assert len(threshold_recs) == 1
    assert threshold_recs[0].setting == "CONFIDENCE_THRESHOLD_DEFAULT"
    assert threshold_recs[0].suggested_value == 0.55
    assert threshold_recs[0].evidence["escalate_rate"] == pytest.approx(0.5)


async def test_recommendation_never_exceeds_the_configured_minimum(monkeypatch, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 10)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.CONFIDENCE_THRESHOLD_DEFAULT", 0.4)  # already at the floor
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_STEP", 0.05)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)

    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()
    for i in range(20):
        await _emit_pending(bus, f"t{i}")
    for i in range(15):
        await _emit_reviewing(bus, f"t{i}")

    recs = await engine.analyze()

    # Already at the floor — no recommendation to go lower still.
    assert not any(r.category == "confidence_threshold_too_strict" for r in recs)


async def test_recommends_raising_threshold_when_escalate_rate_too_low(monkeypatch, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 10)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_LOW", 0.02)
    monkeypatch.setattr("api.config.settings.CONFIDENCE_THRESHOLD_DEFAULT", 0.6)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_STEP", 0.05)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)

    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()
    for i in range(100):
        await _emit_pending(bus, f"t{i}")
    # 0 escalations out of 100 — suspiciously low

    recs = await engine.analyze()

    threshold_recs = [r for r in recs if r.category == "confidence_threshold_too_lax"]
    assert len(threshold_recs) == 1
    assert threshold_recs[0].suggested_value == 0.65


async def test_no_recommendation_within_healthy_band(monkeypatch, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 10)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_LOW", 0.02)

    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()
    for i in range(100):
        await _emit_pending(bus, f"t{i}")
    for i in range(10):  # 10% — comfortably inside [0.02, 0.3]
        await _emit_reviewing(bus, f"t{i}")

    recs = await engine.analyze()

    assert not any(r.category.startswith("confidence_threshold") for r in recs)


# ─── ImprovementEngine.analyze() — per-role error rate category ──────────────

async def test_recommends_investigating_high_error_rate_role(monkeypatch, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 5)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)

    for i in range(10):
        event_type = "agent.failed" if i < 6 else "agent.completed"
        await bus.emit(event_type, source="a", trace_id=f"t{i}", payload={"task_id": str(i), "role": "writer"})

    engine = ImprovementEngine(orchestrator=orch)
    recs = await engine.analyze()

    role_recs = [r for r in recs if r.category == "role_error_rate"]
    assert len(role_recs) == 1
    assert role_recs[0].evidence["role"] == "writer"
    assert role_recs[0].setting is None  # never auto-appliable
    assert role_recs[0].suggested_value is None
