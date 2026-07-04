"""Unit tests for the Audit Log (Bab 30, 61.3) — isolated to a temp file (Bab 12.3)."""
import pytest

from messaging import EventBus, InMemoryBroker
from security import audit_log


@pytest.fixture(autouse=True)
def _isolated_path(tmp_path, monkeypatch):
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_PATH", str(tmp_path / "security_audit.log"))


async def test_record_appends_and_returns_entry():
    entry = await audit_log.record("prompt_guard.blocked", actor="writer-agent", detail={"score": 1.0}, trace_id="t1")
    assert entry.event_type == "prompt_guard.blocked"
    assert entry.actor == "writer-agent"
    assert entry.detail == {"score": 1.0}
    assert entry.trace_id == "t1"


async def test_record_is_readable_back():
    await audit_log.record("output_validator.violation", actor="a", detail={"violations": ["empty"]})
    await audit_log.record("human_approval.decided", actor="rudy", detail={"approved": True})

    recent = audit_log.read_recent(10)
    assert [e.event_type for e in recent] == ["output_validator.violation", "human_approval.decided"]


async def test_read_recent_respects_limit():
    for i in range(5):
        await audit_log.record("test.event", actor="a", detail={"i": i})

    recent = audit_log.read_recent(2)
    assert len(recent) == 2
    assert recent[-1].detail["i"] == 4


def test_read_recent_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_PATH", str(tmp_path / "does-not-exist.log"))
    assert audit_log.read_recent() == []


async def test_record_publishes_security_event():
    bus = EventBus(InMemoryBroker())
    seen = []

    async def collect(event):
        seen.append(event)

    await bus.subscribe("security.*", collect)
    await audit_log.record("prompt_guard.blocked", actor="a", trace_id="t1", event_bus=bus)

    assert len(seen) == 1
    assert seen[0].event_type == "security.prompt_guard.blocked"
    assert seen[0].trace_id == "t1"


async def test_write_failure_does_not_raise(monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _boom)
    entry = await audit_log.record("test.event", actor="a")  # must not raise
    assert entry.event_type == "test.event"
