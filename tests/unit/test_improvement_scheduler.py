"""Unit tests for improvement/scheduler.py (Fase 7, DCF v5 mandate) — the
tick loop that drives analyze -> record -> (maybe) apply -> review.
"""
import asyncio
import subprocess

import pytest

from improvement import ledger
from improvement.engine import ImprovementEngine
from improvement.scheduler import ImprovementScheduler
from messaging import EventBus, InMemoryBroker
from orchestrator.orchestrator import Orchestrator
from tests.unit.test_orchestrator import registry_with, StubAgent


def _git(repo_path, *args):
    subprocess.run(["git", "-C", str(repo_path), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    # A subdirectory of tmp_path, not tmp_path itself — the autouse
    # _isolated_improvement_ledger fixture (tests/conftest.py) also writes
    # into tmp_path; sharing the git repo's root with it would make the
    # ledger file itself look like "someone's uncommitted work" to
    # safe_to_commit, a test-collision false positive rather than a real
    # dirty-tree case (caught live by this exact test, not assumed away).
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    (repo_dir / "config").mkdir()
    (repo_dir / "config" / "agents.yaml").write_text("CONFIDENCE_THRESHOLD_DEFAULT: 0.6\n")
    _git(repo_dir, "add", "-A")
    _git(repo_dir, "commit", "-q", "-m", "initial")
    return repo_dir


@pytest.fixture
def bus():
    return EventBus(InMemoryBroker())


@pytest.fixture
async def orch(bus):
    o = Orchestrator(agent_registry=registry_with(StubAgent("writer")), event_bus=bus)
    await o.metrics.start()
    return o


async def test_start_and_stop_lifecycle():
    scheduler = ImprovementScheduler(tick_seconds=3600)
    assert scheduler._task is None

    await scheduler.start()
    assert scheduler._task is not None
    await scheduler.start()  # idempotent — must not create a second task

    await scheduler.stop()
    assert scheduler._task is None
    await scheduler.stop()  # idempotent


async def test_tick_records_recommendations_but_does_not_apply_when_disabled(monkeypatch, orch, bus, repo):
    monkeypatch.setattr("api.config.settings.ENABLE_AUTONOMOUS_IMPROVEMENT", False)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 10)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_REPO_PATH", str(repo))

    engine = ImprovementEngine(orchestrator=orch)
    scheduler = ImprovementScheduler(engine=engine, tick_seconds=3600)
    await engine._escalation.start()
    for i in range(20):
        await bus.emit("workflow.pending", source="o", trace_id=f"t{i}", payload={})
    for i in range(10):
        await bus.emit("workflow.reviewing", source="o", trace_id=f"t{i}", payload={})

    result = await scheduler.tick()

    recommendations = [e for e in ledger.read_recent() if e.record_type == "recommendation"]
    assert len(recommendations) >= 1
    assert result == []  # nothing applied, nothing reviewed (disabled)
    # config file untouched
    assert (repo / "config" / "agents.yaml").read_text() == "CONFIDENCE_THRESHOLD_DEFAULT: 0.6\n"


async def test_tick_applies_when_enabled(monkeypatch, orch, bus, repo):
    monkeypatch.setattr("api.config.settings.ENABLE_AUTONOMOUS_IMPROVEMENT", True)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_MIN_SAMPLES", 10)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_REPO_PATH", str(repo))

    engine = ImprovementEngine(orchestrator=orch)
    scheduler = ImprovementScheduler(engine=engine, tick_seconds=3600)
    await engine._escalation.start()
    for i in range(20):
        await bus.emit("workflow.pending", source="o", trace_id=f"t{i}", payload={})
    for i in range(10):
        await bus.emit("workflow.reviewing", source="o", trace_id=f"t{i}", payload={})

    result = await scheduler.tick()

    assert len(result) == 1
    assert "CONFIDENCE_THRESHOLD_DEFAULT: 0.55" in (repo / "config" / "agents.yaml").read_text()
