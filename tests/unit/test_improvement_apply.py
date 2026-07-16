"""Unit tests for improvement/apply.py (Fase 7, DCF v5 mandate) — the
apply + auto-revert loop. Every test operates on a disposable temp git
repo with its own fake config/agents.yaml — NEVER the real ai_engine repo.
"""
import subprocess
import time

import pytest

from improvement import ledger
from improvement.apply import apply_recommendation, review_pending_actions
from improvement.engine import EscalationTracker, ImprovementEngine
from improvement.models import ImprovementRecommendation
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
    # dirty-tree case (caught live in test_improvement_scheduler.py, whose
    # tick() writes to the ledger BEFORE calling apply_recommendation).
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "Test")
    (repo_dir / "config").mkdir()
    (repo_dir / "config" / "agents.yaml").write_text(
        "# comment kept as-is\nCONFIDENCE_THRESHOLD_DEFAULT: 0.6\nOTHER_KEY: 1\n"
    )
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


def _rec(suggested_value=0.55) -> ImprovementRecommendation:
    return ImprovementRecommendation(
        category="confidence_threshold_too_strict", setting="CONFIDENCE_THRESHOLD_DEFAULT",
        suggested_value=suggested_value, suggestion="turunkan ambang",
    )


def test_apply_recommendation_writes_config_and_commits(monkeypatch, repo):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_REVIEW_WINDOW_SECONDS", 100)

    action = apply_recommendation(_rec(0.55), repo_path=str(repo))

    assert action is not None
    assert action.old_value == 0.6
    assert action.new_value == 0.55
    text = (repo / "config" / "agents.yaml").read_text()
    assert "CONFIDENCE_THRESHOLD_DEFAULT: 0.55" in text
    assert "# comment kept as-is" in text  # comment survives — not a full YAML re-serialize
    assert "OTHER_KEY: 1" in text  # untouched sibling key survives

    log = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "-1"],
                          capture_output=True, text=True, check=True).stdout
    assert "improvement: auto-adjust" in log


def test_apply_recommendation_records_to_ledger(monkeypatch, repo):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)

    action = apply_recommendation(_rec(0.55), repo_path=str(repo))

    entries = ledger.read_recent()
    applied = [e for e in entries if e.record_type == "action_applied"]
    assert len(applied) == 1
    assert applied[0].payload["id"] == action.id


def test_apply_recommendation_refuses_out_of_bounds_value(monkeypatch, repo):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)

    action = apply_recommendation(_rec(0.95), repo_path=str(repo))  # above MAX

    assert action is None
    assert (repo / "config" / "agents.yaml").read_text() == \
        "# comment kept as-is\nCONFIDENCE_THRESHOLD_DEFAULT: 0.6\nOTHER_KEY: 1\n"  # untouched


def test_apply_recommendation_refuses_non_whitelisted_setting(repo):
    rec = ImprovementRecommendation(category="x", setting="SOME_OTHER_SETTING", suggested_value=1.0)
    assert apply_recommendation(rec, repo_path=str(repo)) is None


def test_apply_recommendation_refuses_dirty_tree(monkeypatch, repo):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)
    (repo / "someone_elses_work.txt").write_text("in progress, uncommitted\n")

    from improvement.git_ops import DirtyTreeError

    with pytest.raises(DirtyTreeError):
        apply_recommendation(_rec(0.55), repo_path=str(repo))


async def test_review_reverts_when_problem_persists(monkeypatch, repo, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_LOW", 0.02)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_REVIEW_WINDOW_SECONDS", -1)  # already due

    action = apply_recommendation(_rec(0.55), repo_path=str(repo))
    assert action is not None

    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()
    for i in range(20):
        await bus.emit("workflow.pending", source="o", trace_id=f"t{i}", payload={})
    for i in range(15):  # 75% — still way outside the healthy band
        await bus.emit("workflow.reviewing", source="o", trace_id=f"t{i}", payload={})

    processed = await review_pending_actions(engine, repo_path=str(repo))

    assert len(processed) == 1
    assert processed[0].outcome == "reverted"
    assert (repo / "config" / "agents.yaml").read_text().count("CONFIDENCE_THRESHOLD_DEFAULT: 0.6") == 1

    reviewed_entries = [e for e in ledger.read_recent() if e.record_type == "action_reviewed"]
    assert len(reviewed_entries) == 1
    assert reviewed_entries[0].payload["outcome"] == "reverted"


async def test_review_keeps_change_when_problem_resolved(monkeypatch, repo, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_HIGH", 0.3)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_ESCALATE_RATE_LOW", 0.02)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_REVIEW_WINDOW_SECONDS", -1)

    action = apply_recommendation(_rec(0.55), repo_path=str(repo))
    assert action is not None

    engine = ImprovementEngine(orchestrator=orch)
    await engine._escalation.start()
    for i in range(20):
        await bus.emit("workflow.pending", source="o", trace_id=f"t{i}", payload={})
    for i in range(2):  # 10% — comfortably healthy now
        await bus.emit("workflow.reviewing", source="o", trace_id=f"t{i}", payload={})

    processed = await review_pending_actions(engine, repo_path=str(repo))

    assert len(processed) == 1
    assert processed[0].outcome == "kept"
    assert "CONFIDENCE_THRESHOLD_DEFAULT: 0.55" in (repo / "config" / "agents.yaml").read_text()


async def test_review_skips_actions_not_yet_due(monkeypatch, repo, orch, bus):
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MIN", 0.4)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_CONFIDENCE_MAX", 0.9)
    monkeypatch.setattr("api.config.settings.IMPROVEMENT_REVIEW_WINDOW_SECONDS", 100_000)  # far in the future

    apply_recommendation(_rec(0.55), repo_path=str(repo))

    engine = ImprovementEngine(orchestrator=orch)
    processed = await review_pending_actions(engine, repo_path=str(repo))

    assert processed == []
