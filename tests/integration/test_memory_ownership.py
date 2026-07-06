"""Integration tests for Memory API ownership (Tahap 26) — closes a gap
`docs/PROGRESS.md` flagged as risky since Tahap 12: any caller who knew a
session_id could read or delete that session's memory, no authorization at
all. Reuses `api/routes/chat.py::_require_session_owner` directly (Tahap
22's exact mechanism) since this module's session_id is meant to be the
same one a ChatEngine `Session` is keyed by.

Separate file from `test_memory_api.py`, which deliberately runs with no
`API_KEYS` configured (default dev/admin-bypass) to prove the tier
read/write plumbing itself — these tests need `API_KEYS` set to exercise
the ownership check, so they're kept apart rather than retrofitting
headers onto every existing call there.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from core.chat.engine import Session, chat_engine
from memory.memory_manager import build_memory_manager


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "ownerkey:user,strangerkey:user")


@pytest.fixture(autouse=True)
def _clean_chat_sessions():
    chat_engine.sessions.clear()
    yield
    chat_engine.sessions.clear()


@pytest.fixture
def memory_manager(monkeypatch):
    import api.routes.memory as route

    manager = build_memory_manager(volatile_backend="memory", persistent_backend="memory")
    monkeypatch.setattr(route, "_memory", manager)
    return manager


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def client(app, memory_manager):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _as(key: str) -> dict:
    return {"X-API-Key": key}


async def test_unauthenticated_request_rejected(client):
    res = await client.get("/api/v1/memory/some-session")
    assert res.status_code == 401


async def test_owner_can_read_own_session_memory(client, memory_manager):
    chat_engine.sessions["s1"] = Session("s1", owner="ownerkey")
    await memory_manager.working.set("s1", "last_tool", "write_pdf")

    res = await client.get("/api/v1/memory/s1", headers=_as("ownerkey"))
    assert res.status_code == 200
    assert res.json()["working"] == {"last_tool": "write_pdf"}


async def test_stranger_cannot_read_session_memory(client):
    chat_engine.sessions["s1"] = Session("s1", owner="ownerkey")

    res = await client.get("/api/v1/memory/s1", headers=_as("strangerkey"))
    assert res.status_code == 403


async def test_stranger_cannot_delete_session_memory(client, memory_manager):
    chat_engine.sessions["s1"] = Session("s1", owner="ownerkey")
    await memory_manager.working.set("s1", "key", "value")

    res = await client.delete("/api/v1/memory/s1/working/key", headers=_as("strangerkey"))
    assert res.status_code == 403

    # Confirm the denial actually prevented the delete.
    owner_res = await client.get("/api/v1/memory/s1", headers=_as("ownerkey"))
    assert owner_res.json()["working"] == {"key": "value"}


async def test_session_unknown_to_chatengine_stays_open(client, memory_manager):
    """A session_id ChatEngine has never seen has no recorded owner — the
    same gap docs/PROGRESS.md already acknowledges (Chat doesn't populate
    memory/ yet), unaffected by this Tahap. Only sessions with a *recorded*
    owner now reject a different caller."""
    await memory_manager.working.set("never-touched-by-chatengine", "k", "v")

    res = await client.get("/api/v1/memory/never-touched-by-chatengine", headers=_as("strangerkey"))
    assert res.status_code == 200


async def test_no_api_keys_configured_behaves_as_before(client, memory_manager, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    chat_engine.sessions["s1"] = Session("s1", owner="")  # dev-default owner is the empty string
    await memory_manager.working.set("s1", "k", "v")

    res = await client.get("/api/v1/memory/s1")  # no header at all
    assert res.status_code == 200
    assert res.json()["working"] == {"k": "v"}
