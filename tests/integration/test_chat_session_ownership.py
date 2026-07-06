"""Integration tests for Chat session ownership over HTTP (Tahap 22, closes
the gap Tahap 20 explicitly left open: `session_id` wasn't bound to any
identity — whoever knew an ID could read/continue/delete anyone's session).

Same fake-streaming-Ollama technique as `test_chat_api_rbac.py`/
`test_chat_engine_rbac.py` (`core.chat.engine.build_registry`/
`httpx.AsyncClient` monkeypatch) — simplified here since ownership doesn't
care about tool-calling at all, just that a turn completes.
"""
import json

import pytest
from httpx import ASGITransport, AsyncClient

from agent.tools.registry import ToolRegistry
from core.chat.engine import chat_engine


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "userakey:user,userbkey:user")


@pytest.fixture(autouse=True)
def _clean_chat_engine_state():
    chat_engine._registries.clear()
    chat_engine.sessions.clear()
    yield
    chat_engine._registries.clear()
    chat_engine.sessions.clear()


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


_FINAL_ROUND = json.dumps({"message": {"content": "Halo."}, "done": True})


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None):
        return _FakeStreamCM([_FINAL_ROUND])


@pytest.fixture(autouse=True)
def _fake_tool_backend(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: ToolRegistry())
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", _FakeAsyncClient)


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _sse_events(response_text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in response_text.splitlines() if line.startswith("data: ")]


async def _create_session_as(client, api_key: str) -> str:
    res = await client.post("/api/v1/chat/stream", json={"message": "halo"}, headers={"X-API-Key": api_key})
    assert res.status_code == 200
    session_event = next(e for e in _sse_events(res.text) if e.get("type") == "session")
    return session_event["session_id"]


async def test_owner_can_read_own_session_history(client):
    session_id = await _create_session_as(client, "userakey")

    res = await client.get(f"/api/v1/chat/sessions/{session_id}", headers={"X-API-Key": "userakey"})
    assert res.status_code == 200
    assert res.json()["session_id"] == session_id


async def test_stranger_cannot_read_session_history(client):
    session_id = await _create_session_as(client, "userakey")

    res = await client.get(f"/api/v1/chat/sessions/{session_id}", headers={"X-API-Key": "userbkey"})
    assert res.status_code == 403


async def test_stranger_cannot_continue_session_via_stream(client):
    session_id = await _create_session_as(client, "userakey")

    res = await client.post(
        "/api/v1/chat/stream",
        json={"session_id": session_id, "message": "lanjutkan"},
        headers={"X-API-Key": "userbkey"},
    )
    assert res.status_code == 403


async def test_stranger_cannot_delete_session(client):
    session_id = await _create_session_as(client, "userakey")

    res = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers={"X-API-Key": "userbkey"})
    assert res.status_code == 403

    # Confirm it's still there — the denial actually prevented the delete.
    owner_res = await client.get(f"/api/v1/chat/sessions/{session_id}", headers={"X-API-Key": "userakey"})
    assert owner_res.status_code == 200


async def test_owner_can_delete_own_session(client):
    session_id = await _create_session_as(client, "userakey")

    res = await client.delete(f"/api/v1/chat/sessions/{session_id}", headers={"X-API-Key": "userakey"})
    assert res.status_code == 200
    assert res.json()["deleted"] is True


async def test_stranger_cannot_upload_into_session(client, tmp_path):
    session_id = await _create_session_as(client, "userakey")

    f = tmp_path / "sneaky.txt"
    f.write_text("data")
    with open(f, "rb") as fh:
        res = await client.post(
            "/api/v1/chat/upload",
            data={"session_id": session_id},
            files={"files": ("sneaky.txt", fh, "text/plain")},
            headers={"X-API-Key": "userbkey"},
        )
    assert res.status_code == 403


async def test_list_sessions_only_shows_own(client):
    session_a = await _create_session_as(client, "userakey")
    session_b = await _create_session_as(client, "userbkey")

    res_a = await client.get("/api/v1/chat/sessions", headers={"X-API-Key": "userakey"})
    ids_a = {s["id"] for s in res_a.json()["sessions"]}
    assert session_a in ids_a
    assert session_b not in ids_a

    res_b = await client.get("/api/v1/chat/sessions", headers={"X-API-Key": "userbkey"})
    ids_b = {s["id"] for s in res_b.json()["sessions"]}
    assert session_b in ids_b
    assert session_a not in ids_b


async def test_no_api_keys_configured_behaves_as_before(client, monkeypatch):
    """Dev default (no API_KEYS at all): every caller shares the same
    Principal(api_key="", role="admin") — ownership checks must be a total
    no-op, identical to behavior before Tahap 22."""
    monkeypatch.setattr("api.config.settings.API_KEYS", "")

    session_id = await _create_session_as(client, "irrelevant-since-auth-disabled")

    res = await client.get(f"/api/v1/chat/sessions/{session_id}")  # no header at all
    assert res.status_code == 200
