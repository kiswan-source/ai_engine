"""Integration test for RBAC over HTTP through /api/v1/chat/stream (Tahap 20).

Exercises the *real* route -> `chat_engine` singleton -> `ToolRegistry.execute`
path, confirming `X-API-Key` -> `Principal.role` -> tool-call gate works
end-to-end — not just the engine-level unit tests in
`test_chat_engine_rbac.py`. Same fake-registry + fake-streaming-Ollama
technique (`core.chat.engine.build_registry`/`httpx.AsyncClient` monkeypatch)
since `core/chat/` has no other test precedent to follow.

The route uses the module-level `chat_engine` singleton (not a fresh
instance per request), so `_registries`/`sessions` are cleared per test to
avoid cross-test state bleeding through what is, by design, process-lifetime
state (`core/chat/engine.py` docstring: "Sessions are in-memory").
"""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from agent.tools.registry import ToolRegistry
from core.chat.engine import chat_engine


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "userkey:user,opkey:operator")


@pytest.fixture(autouse=True)
def _clean_chat_engine_state():
    chat_engine._registries.clear()
    chat_engine.sessions.clear()
    yield
    chat_engine._registries.clear()
    chat_engine.sessions.clear()


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


@pytest.fixture(autouse=True)
def _fake_tool_backend(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _fake_registry())
    rounds = [
        [_tool_call_round("write_txt", {"filename": "out.txt", "content": "hi"})],
        [_final_round("Selesai.")],
    ]

    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _sse_events(response_text: str) -> list[dict]:
    events = []
    for line in response_text.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: "):]))
    return events


async def test_user_role_denied_write_txt_over_http(client):
    res = await client.post(
        "/api/v1/chat/stream", json={"message": "tolong buat file txt"}, headers={"X-API-Key": "userkey"}
    )
    assert res.status_code == 200
    events = _sse_events(res.text)

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0]["ok"] is False
    assert "ditolak" in tool_results[0]["summary"].lower()
    assert any(e.get("type") == "done" for e in events)


async def test_operator_role_allowed_write_txt_over_http(client):
    res = await client.post(
        "/api/v1/chat/stream", json={"message": "tolong buat file txt"}, headers={"X-API-Key": "opkey"}
    )
    assert res.status_code == 200
    events = _sse_events(res.text)

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert tool_results[0]["ok"] is True
    assert any(e.get("type") == "file" for e in events)


async def test_missing_api_key_rejected_when_api_keys_configured(client):
    res = await client.post("/api/v1/chat/stream", json={"message": "halo"})
    assert res.status_code == 401
