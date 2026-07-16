"""Unit tests for Memory <-> Chat Engine wiring (Fase 3, DCF v5 mandate
"Memory Intelligence Evolution"). Reuses test_chat_engine_rbac.py's fake
Ollama-stream plumbing rather than rebuilding it.
"""
import asyncio

import pytest

from agent.tools.registry import ToolRegistry
from core.chat.engine import MEMORY_SUMMARY_EVERY_N_TURNS, ChatEngine
from tests.unit.test_chat_engine_rbac import _FakeAsyncClient, _final_round


def _fake_registry_with_memory_tools() -> ToolRegistry:
    """Real remember_fact/recall_facts (not stubs) — these need no real
    provider/network call, unlike write_txt-style tools, so there's no
    reason to fake them."""
    from agent.tools.memory_tools import recall_facts, remember_fact

    reg = ToolRegistry()
    reg.register("remember_fact", remember_fact, "fake registration of the real tool")
    reg.register("recall_facts", recall_facts, "fake registration of the real tool")
    return reg


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _fake_registry_with_memory_tools())
    return ChatEngine()


async def _run(monkeypatch, engine, rounds, session_id="sess-mem", user_text="halo", owner=None):
    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    events = []
    async for ev in engine.stream_run(session_id, user_text, owner=owner):
        events.append(ev)
    return events


async def test_conversation_memory_records_user_and_assistant_messages(monkeypatch, engine):
    await _run(monkeypatch, engine, [[_final_round("Halo juga!")]], session_id="sess-conv", user_text="halo bot")

    history = await engine.memory.conversation.get_history("sess-conv")
    assert [h["role"] for h in history] == ["user", "assistant"]
    assert history[0]["content"] == "halo bot"
    assert history[1]["content"] == "Halo juga!"


async def test_working_memory_reflects_last_turn_files(monkeypatch, engine):
    await _run(monkeypatch, engine, [[_final_round("ok")]], session_id="sess-work")

    last_files = await engine.memory.working.get("sess-work", "last_files")
    assert last_files == {"uploaded": [], "produced": []}
    assert await engine.memory.working.get("sess-work", "last_message_at") is not None


async def test_summary_only_refreshed_every_n_turns(monkeypatch, engine):
    async def _fake_summarizer(text: str) -> str:
        return f"ringkasan: {text[:20]}"

    monkeypatch.setattr(engine.memory.summary, "_summarizer", _fake_summarizer)

    for i in range(MEMORY_SUMMARY_EVERY_N_TURNS - 1):
        await _run(monkeypatch, engine, [[_final_round(f"balasan {i}")]], session_id="sess-sum", user_text=f"pesan {i}")

    assert await engine.memory.summary.get_summary("sess-sum") is None

    await _run(monkeypatch, engine, [[_final_round("balasan terakhir")]], session_id="sess-sum", user_text="pesan terakhir")

    assert await engine.memory.summary.get_summary("sess-sum") is not None


async def test_memory_failure_does_not_crash_the_turn(monkeypatch, engine):
    async def _boom(*args, **kwargs):
        raise RuntimeError("redis is down")

    monkeypatch.setattr(engine.memory.conversation, "add_message", _boom)

    events = await _run(monkeypatch, engine, [[_final_round("tetap jalan")]], session_id="sess-fail")

    assert not any(e["type"] == "error" for e in events)
    assert events[-1]["type"] == "done"
    assert any(e["type"] == "token" for e in events)


async def test_remember_fact_and_recall_facts_use_injected_owner_not_model_supplied_one(monkeypatch, engine):
    """The model could try to pass its own `owner` arg to escape its
    session's identity — _run_tool must override it unconditionally, the
    same rule already enforced for workspace_id (Tahap 23)."""
    from tests.unit.test_chat_engine_rbac import _tool_call_round

    rounds = [
        [_tool_call_round("remember_fact", {"key": "bahasa", "value": "Indonesia", "owner": "attacker-supplied"})],
        [_final_round("Sudah diingat.")],
    ]
    events = await _run(monkeypatch, engine, rounds, session_id="sess-remember", owner="real-owner")
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True

    from agent.tools.memory_tools import recall_facts

    # recall_facts runs via asyncio.run() internally (see its docstring —
    # designed for the asyncio.to_thread worker-thread path _run_tool
    # actually uses, which has no ambient event loop); calling it directly
    # from this async test would hit "asyncio.run() cannot be called from a
    # running event loop", so bridge through a thread here too, same as
    # production actually does.
    real_owner_facts = await asyncio.to_thread(recall_facts, owner="real-owner")
    attacker_facts = await asyncio.to_thread(recall_facts, owner="attacker-supplied")
    assert real_owner_facts["facts"] == {"bahasa": "Indonesia"}
    assert attacker_facts["facts"] == {}


async def test_run_tool_injects_actor_for_workspace_write_file(engine):
    """Fase 4 — workspace_write_file's version snapshot/audit trail needs to
    know who triggered an overwrite. Same never-trust-the-model rule as
    owner/workspace_id: _run_tool must inject it, not the caller-supplied args."""
    captured = {}

    def fake_workspace_write_file(**kwargs):
        captured.update(kwargs)
        return {"success": True, "path": kwargs.get("relative_path"), "action": "created"}

    registry = ToolRegistry()
    registry.register("workspace_write_file", fake_workspace_write_file, "fake")

    await engine._run_tool(
        registry, "workspace_write_file",
        {"folder_id": "f1", "relative_path": "a.txt", "content": "x", "actor": "attacker-supplied"},
        role=None, workspace_id="ws-1", workspace_role="editor", owner="real-owner",
    )

    assert captured["actor"] == "real-owner"
