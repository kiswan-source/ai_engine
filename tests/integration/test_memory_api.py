"""Integration tests for /api/v1/memory/* — real memory/ tiers (Tahap 3)
behind an isolated MemoryManager per test (in-memory backends), swapped into
api.routes.memory's module-level singleton the same way
tests/integration/test_orchestrator_api.py swaps `_orchestrator`.

These tests populate tiers directly through MemoryManager to prove the route
reads/deletes real data correctly — they do NOT prove ChatEngine populates
these tiers from a real chat turn, because it doesn't yet
(docs/PROGRESS.md Tahap 12 gap, confirmed with the user rather than hidden).
"""
import pytest
from httpx import ASGITransport, AsyncClient

from memory.memory_manager import build_memory_manager


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
def memory_manager(monkeypatch):
    import api.routes.memory as route

    manager = build_memory_manager(volatile_backend="memory", persistent_backend="memory")
    monkeypatch.setattr(route, "_memory", manager)
    return manager


@pytest.fixture
async def client(app, memory_manager):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_empty_session_returns_empty_tiers(client):
    res = await client.get("/api/v1/memory/unknown-session")
    assert res.status_code == 200
    assert res.json() == {
        "session_id": "unknown-session",
        "working": {},
        "conversation_history": [],
        "summary": None,
        "long_term": {},
    }


async def test_working_memory_read_and_forget(client, memory_manager):
    await memory_manager.working.set("s1", "last_tool", "write_pdf")

    res = await client.get("/api/v1/memory/s1")
    assert res.json()["working"] == {"last_tool": "write_pdf"}

    del_res = await client.delete("/api/v1/memory/s1/working/last_tool")
    assert del_res.status_code == 200

    res2 = await client.get("/api/v1/memory/s1")
    assert res2.json()["working"] == {}


async def test_conversation_history_read_and_clear(client, memory_manager):
    await memory_manager.conversation.add_message("s2", "user", "halo")
    await memory_manager.conversation.add_message("s2", "assistant", "hai juga")

    res = await client.get("/api/v1/memory/s2")
    history = res.json()["conversation_history"]
    assert [h["content"] for h in history] == ["halo", "hai juga"]

    clear_res = await client.delete("/api/v1/memory/s2/conversation")
    assert clear_res.status_code == 200

    res2 = await client.get("/api/v1/memory/s2")
    assert res2.json()["conversation_history"] == []


async def test_long_term_read_and_forget(client, memory_manager):
    await memory_manager.long_term.remember("s3", "preferred_language", "id")

    res = await client.get("/api/v1/memory/s3")
    assert res.json()["long_term"] == {"preferred_language": "id"}

    del_res = await client.delete("/api/v1/memory/s3/long-term/preferred_language")
    assert del_res.status_code == 200

    res2 = await client.get("/api/v1/memory/s3")
    assert res2.json()["long_term"] == {}


async def test_summary_read_and_clear(client, memory_manager):
    await memory_manager.summary.save_summary("s4", "Pengguna bertanya soal circuit breaker.")

    res = await client.get("/api/v1/memory/s4")
    assert res.json()["summary"] == "Pengguna bertanya soal circuit breaker."

    clear_res = await client.delete("/api/v1/memory/s4/summary")
    assert clear_res.status_code == 200

    res2 = await client.get("/api/v1/memory/s4")
    assert res2.json()["summary"] is None
