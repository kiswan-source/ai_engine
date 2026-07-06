"""Integration tests for Chat download ownership over HTTP (Tahap 24, closes
the gap Tahap 22/23 explicitly left open: `/download/{filename}` had no
session concept at all — any caller could fetch anything in `reports/` by
filename alone).

Same fake-registry + fake-streaming-Ollama technique as
`test_chat_api_rbac.py` — a fake `write_txt` that returns a `file` key so a
real entry lands in `ChatEngine.Session.produced_files`.

`api/routes/chat.py` imports `REPORTS_DIR` via `from core.chat.engine import
... REPORTS_DIR` (a name binding) — monkeypatching
`core.chat.engine.REPORTS_DIR` would NOT reach it, so this patches
`api.routes.chat.REPORTS_DIR` directly, pointing it at `tmp_path`.
"""
import json
import os

import pytest
from httpx import ASGITransport, AsyncClient

from agent.tools.registry import ToolRegistry
from core.chat.engine import chat_engine


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    # operator, not user: write_txt is gated by Tahap 20's RBAC
    # (TOOL_RISK_ACTIONS applies by tool *name*, regardless of which function
    # is actually registered under it) — role is orthogonal to what this
    # file tests (session/download ownership), so both callers get a role
    # that can actually produce a file.
    monkeypatch.setattr("api.config.settings.API_KEYS", "userakey:operator,userbkey:operator")


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


def _sse_events(response_text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in response_text.splitlines() if line.startswith("data: ")]


@pytest.fixture
def reports_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("api.routes.chat.REPORTS_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture(autouse=True)
def _fake_registry_with_write_txt(monkeypatch, reports_dir):
    def _write_txt(filename: str, content: str):
        path = os.path.join(str(reports_dir), filename)
        with open(path, "w") as f:
            f.write(content)
        return {"success": True, "file": path, "filename": filename, "size": len(content), "type": "txt"}

    def _build(base_url, model):
        reg = ToolRegistry()
        reg.register("write_txt", _write_txt, "fake write_txt")
        return reg

    monkeypatch.setattr("core.chat.engine.build_registry", _build)


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _produce_file_as(client, monkeypatch, api_key: str, filename: str = "out.txt") -> str:
    """Real turn where the (fake) model calls write_txt — returns session_id."""
    rounds = [
        [_tool_call_round("write_txt", {"filename": filename, "content": "isi rahasia"})],
        [_final_round()],
    ]

    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    res = await client.post("/api/v1/chat/stream", json={"message": "buat file"}, headers={"X-API-Key": api_key})
    assert res.status_code == 200
    session_event = next(e for e in _sse_events(res.text) if e.get("type") == "session")
    return session_event["session_id"]


async def test_owner_can_download_file_produced_in_own_session(client, reports_dir, monkeypatch):
    session_id = await _produce_file_as(client, monkeypatch, "userakey", "out.txt")

    res = await client.get(
        f"/api/v1/chat/download/out.txt?session_id={session_id}", headers={"X-API-Key": "userakey"}
    )
    assert res.status_code == 200
    assert res.content == b"isi rahasia"


async def test_stranger_cannot_download_with_owners_session_id(client, monkeypatch):
    session_id = await _produce_file_as(client, monkeypatch, "userakey", "out.txt")

    res = await client.get(
        f"/api/v1/chat/download/out.txt?session_id={session_id}", headers={"X-API-Key": "userbkey"}
    )
    assert res.status_code == 403


async def test_download_404_when_file_not_produced_in_that_session(client, monkeypatch):
    session_id = await _produce_file_as(client, monkeypatch, "userakey", "out.txt")

    res = await client.get(
        f"/api/v1/chat/download/someone_elses_file.txt?session_id={session_id}",
        headers={"X-API-Key": "userakey"},
    )
    assert res.status_code == 404


async def test_download_404_for_unknown_session(client):
    res = await client.get(
        "/api/v1/chat/download/out.txt?session_id=does-not-exist", headers={"X-API-Key": "userakey"}
    )
    assert res.status_code == 404


async def test_download_requires_session_id_query_param(client):
    # A valid key so the auth dependency doesn't mask the query-param
    # validation this test actually targets.
    res = await client.get("/api/v1/chat/download/out.txt", headers={"X-API-Key": "userakey"})
    assert res.status_code == 422  # FastAPI validation: missing required query param


async def test_no_api_keys_configured_behaves_as_before(client, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    session_id = await _produce_file_as(client, monkeypatch, "irrelevant-since-auth-disabled", "out.txt")

    res = await client.get(f"/api/v1/chat/download/out.txt?session_id={session_id}")
    assert res.status_code == 200
    assert res.content == b"isi rahasia"
