"""Unit tests for RBAC wired into ChatEngine (Tahap 20, closes the gap every
RBAC Tahap since 10 acknowledged: `core/chat/engine.py` never passed a role).

Follows `test_tool_registry_rbac.py`'s pattern of a minimal, fresh
`ToolRegistry()` with a fake tool registered under a name that's already in
`security.permissions.TOOL_RISK_ACTIONS` (`write_txt`) — not the real
`agent/tools/registry.py::build_registry()`, which would pull in real
readers/writers/GIS/image modules and write to the real reports/ dir. Only
the streaming Ollama HTTP call is faked (`core.chat.engine.httpx.AsyncClient`),
same monkeypatch-the-module-attribute style as `test_providers.py`.
"""
import json

import pytest

from agent.tools.registry import ToolRegistry
from core.chat.engine import ChatEngine


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCM:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return _FakeStreamResponse(self._lines)

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    """Minimal async context-manager stand-in for httpx.AsyncClient's
    `.stream()` — one scripted list of JSON-lines per tool-calling round."""

    rounds: list[list[str]] = []

    def __init__(self, *args, **kwargs):
        self._round_index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None):
        idx = min(self._round_index, len(self.rounds) - 1)
        self._round_index += 1
        return _FakeStreamCM(self.rounds[idx])


def _tool_call_round(tool_name: str, arguments: dict) -> str:
    return json.dumps(
        {"message": {"content": "", "tool_calls": [{"function": {"name": tool_name, "arguments": arguments}}]}, "done": True}
    )


def _final_round(text: str = "Selesai.") -> str:
    return json.dumps({"message": {"content": text}, "done": True})


def _fake_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        "write_txt",
        lambda filename, content: {
            "success": True, "file": f"/fake/reports/{filename}", "filename": filename,
            "size": len(content), "type": "txt",
        },
        "fake write_txt, gated via TOOL_RISK_ACTIONS same as the real tool",
    )
    return reg


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _fake_registry())
    return ChatEngine()


async def _run(monkeypatch, engine, rounds, role):
    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    events = []
    async for ev in engine.stream_run("sess-1", "tolong buat file txt", role=role):
        events.append(ev)
    return events


async def test_denied_tool_call_is_a_normal_result_not_a_crashed_stream(monkeypatch, engine):
    rounds = [
        [_tool_call_round("write_txt", {"filename": "out.txt", "content": "hi"})],
        [_final_round("Maaf, saya tidak berhak menulis file ini.")],
    ]
    events = await _run(monkeypatch, engine, rounds, role="user")  # user lacks tool:write_txt

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["ok"] is False
    assert "ditolak" in tool_results[0]["summary"].lower()
    assert not any(e["type"] == "file" for e in events)
    assert not any(e["type"] == "error" for e in events)  # denial != stream error
    assert events[-1]["type"] == "done"  # stream completed normally


async def test_allowed_tool_call_succeeds_for_operator(monkeypatch, engine):
    rounds = [
        [_tool_call_round("write_txt", {"filename": "out.txt", "content": "hi"})],
        [_final_round("Sudah dibuat.")],
    ]
    events = await _run(monkeypatch, engine, rounds, role="operator")  # operator has tool:write_txt

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True
    file_events = [e for e in events if e["type"] == "file"]
    assert len(file_events) == 1
    assert file_events[0]["filename"] == "out.txt"
    assert events[-1]["type"] == "done"


async def test_role_none_is_unchanged_default_behavior(monkeypatch, engine):
    """role=None (every caller before Tahap 20, and any that still doesn't
    opt in) must behave exactly as before — no gate at all."""
    rounds = [
        [_tool_call_round("write_txt", {"filename": "out.txt", "content": "hi"})],
        [_final_round("Sudah dibuat.")],
    ]
    events = await _run(monkeypatch, engine, rounds, role=None)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True


async def test_admin_role_bypasses_gate(monkeypatch, engine):
    rounds = [
        [_tool_call_round("write_txt", {"filename": "out.txt", "content": "hi"})],
        [_final_round("Sudah dibuat.")],
    ]
    events = await _run(monkeypatch, engine, rounds, role="admin")

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True
