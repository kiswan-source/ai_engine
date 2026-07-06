"""Unit tests for Agent Workspace Context wiring in ChatEngine (Bab 69.5,
Tahap 23) — `_run_tool`'s workspace_id injection/override and `stream_run`'s
session-level binding persistence.

Same fake-registry + fake-streaming-Ollama technique as
`test_chat_engine_rbac.py` (`core.chat.engine.build_registry`/
`httpx.AsyncClient` monkeypatch).
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


def _echo_registry() -> ToolRegistry:
    """A fake workspace_list_files that just echoes the args it actually
    received back — lets tests assert what _run_tool injected."""
    reg = ToolRegistry()
    reg.register(
        "workspace_list_files",
        lambda **kwargs: {"success": True, "received_args": kwargs, "text": "ok"},
        "fake workspace_list_files echoing received args",
    )
    return reg


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _echo_registry())
    return ChatEngine()


async def _run(monkeypatch, engine, rounds, **stream_kwargs):
    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    events = []
    async for ev in engine.stream_run("sess-1", "lihat isi workspace", **stream_kwargs):
        events.append(ev)
    return events


# ─── _run_tool direct unit tests ────────────────────────────────────────

async def test_run_tool_injects_workspace_id_overriding_model_supplied_value(engine):
    registry = _echo_registry()
    result = await engine._run_tool(
        registry, "workspace_list_files", {"workspace_id": "fake-hallucinated-id"}, role=None, workspace_id="real-ws-id"
    )
    assert result["received_args"]["workspace_id"] == "real-ws-id"


async def test_run_tool_returns_not_connected_error_without_workspace_id(engine):
    registry = _echo_registry()
    result = await engine._run_tool(registry, "workspace_list_files", {}, role=None, workspace_id=None)
    assert result["success"] is False
    assert "belum terhubung" in result["error"].lower()


async def test_run_tool_leaves_unrelated_tools_untouched(engine):
    registry = ToolRegistry()
    registry.register("write_txt", lambda **kw: {"success": True, "received_args": kw}, "fake")
    result = await engine._run_tool(registry, "write_txt", {"filename": "a.txt", "content": "hi"}, role=None, workspace_id="real-ws-id")
    assert "workspace_id" not in result["received_args"]


# ─── stream_run integration (binding persistence across messages) ──────

async def test_stream_run_binds_workspace_id_on_first_message(monkeypatch, engine):
    rounds = [
        [_tool_call_round("workspace_list_files", {})],
        [_final_round()],
    ]
    events = await _run(monkeypatch, engine, rounds, workspace_id="ws-1")

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True
    assert engine.sessions["sess-1"].workspace_id == "ws-1"


async def test_session_keeps_bound_workspace_id_when_later_message_omits_it(monkeypatch, engine):
    # First message binds ws-1.
    await _run(monkeypatch, engine, [[_final_round()]], workspace_id="ws-1")
    # Second message on the SAME session doesn't resupply workspace_id.
    rounds = [
        [_tool_call_round("workspace_list_files", {})],
        [_final_round()],
    ]
    events = await _run(monkeypatch, engine, rounds, workspace_id=None)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True  # still connected via the session's remembered binding
    assert engine.sessions["sess-1"].workspace_id == "ws-1"
