"""Unit tests for the Chat -> Orchestrator bridge surfacing correctly in the
chat UI's existing tool_result event (Fase 6, DCF v5 mandate "Cowork
Experience") — no new SSE event type, reusing ChatEngine._summarize_result.
"""
import pytest

from agent.tools.registry import ToolRegistry
from core.chat.engine import ChatEngine
from orchestrator.orchestrator import Orchestrator
from tests.unit.test_chat_engine_rbac import _FakeAsyncClient, _final_round, _tool_call_round
from tests.unit.test_orchestrator import StubAgent, registry_with
from tests.unit.test_orchestrator_tools import _CapturingAgent, _LowConfidenceAgent


def test_summarize_result_success_shows_final_output():
    result = {
        "success": True, "final_output": "Laporan lengkap selesai.", "escalate": False,
        "message": None, "steps": [], "trace_id": "t1", "state": "completed",
    }
    assert ChatEngine._summarize_result(result) == "Laporan lengkap selesai."


def test_summarize_result_escalate_shows_message_not_partial_output():
    result = {
        "success": False, "final_output": "jawaban belum matang", "escalate": True,
        "message": "Alur kerja ini membutuhkan persetujuan manusia (trace_id=abc).",
        "steps": [], "trace_id": "abc", "state": "reviewing",
    }
    summary = ChatEngine._summarize_result(result)
    assert "persetujuan manusia" in summary
    assert "jawaban belum matang" not in summary


def _fake_registry_with_orchestrator_tool() -> ToolRegistry:
    from agent.tools.orchestrator_tools import run_orchestrated_workflow

    reg = ToolRegistry()
    reg.register("run_orchestrated_workflow", run_orchestrated_workflow, "fake registration of the real tool")
    return reg


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _fake_registry_with_orchestrator_tool())
    return ChatEngine()


async def _run(monkeypatch, engine, rounds, session_id="sess-orch", role=None):
    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    events = []
    async for ev in engine.stream_run(session_id, "analisa dokumen ini dan buat laporan lengkap", role=role):
        events.append(ev)
    return events


async def test_chat_turn_surfaces_orchestrated_workflow_success(monkeypatch, engine):
    import orchestrator.orchestrator as orchestrator_module

    orchestrator_module._shared_orchestrator = Orchestrator(
        agent_registry=registry_with(StubAgent("writer", output="Laporan jadi."))
    )

    rounds = [
        [_tool_call_round("run_orchestrated_workflow", {"goal": "buat laporan", "roles": ["writer"], "mode": "sequential"})],
        [_final_round("Selesai, ini laporannya.")],
    ]
    events = await _run(monkeypatch, engine, rounds)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True
    assert tool_results[0]["summary"] == "Laporan jadi."
    assert events[-1]["type"] == "done"


async def test_chat_turn_surfaces_orchestrated_workflow_escalation(monkeypatch, engine):
    import orchestrator.orchestrator as orchestrator_module

    monkeypatch.setattr("api.config.settings.ENABLE_HUMAN_APPROVAL", True)
    monkeypatch.setattr("api.config.settings.REFLECTION_MAX_ITERATIONS", 1)
    orchestrator_module._shared_orchestrator = Orchestrator(
        agent_registry=registry_with(_LowConfidenceAgent("writer"))
    )

    rounds = [
        [_tool_call_round("run_orchestrated_workflow", {"goal": "tugas sulit", "roles": ["writer"], "mode": "reflection"})],
        [_final_round("Ini butuh persetujuanmu dulu.")],
    ]
    events = await _run(monkeypatch, engine, rounds)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True  # the tool call itself succeeded — escalation isn't a tool failure
    assert "persetujuan manusia" in tool_results[0]["summary"]
    assert events[-1]["type"] == "done"


# ── Fase 14 (DCF v5 mandate — orchestrator agent tool access) ──────────────


async def test_chat_turn_injects_the_session_role_as_caller_role(monkeypatch, engine):
    """caller_role must come from the chat session's own already-resolved
    RBAC role (never a model-supplied argument) — same never-trust-the-model
    rule as workspace_id/owner injection."""
    import orchestrator.orchestrator as orchestrator_module

    agent = _CapturingAgent("writer", tool_calls=())
    orchestrator_module._shared_orchestrator = Orchestrator(agent_registry=registry_with(agent))

    rounds = [
        [_tool_call_round("run_orchestrated_workflow", {"goal": "buat laporan", "roles": ["writer"], "mode": "sequential"})],
        [_final_round("Selesai.")],
    ]
    await _run(monkeypatch, engine, rounds, role="operator")

    assert agent.last_task.metadata.get("caller_role") == "operator"


async def test_chat_turn_surfaces_produced_files_as_downloadable_cards(monkeypatch, engine):
    """The "text only" half of the original gap: a file an EXECUTOR step
    actually wrote during the workflow must reach the chat UI as a real
    "file" event, not just be mentioned in the summary text."""
    import orchestrator.orchestrator as orchestrator_module

    agent = _CapturingAgent(
        "writer",
        tool_calls=({"name": "write_docx", "args": {}, "success": True, "file": "/fake/reports/laporan.docx"},),
    )
    orchestrator_module._shared_orchestrator = Orchestrator(agent_registry=registry_with(agent))

    rounds = [
        [_tool_call_round("run_orchestrated_workflow", {"goal": "buat laporan", "roles": ["writer"], "mode": "sequential"})],
        [_final_round("Selesai, filenya sudah dibuat.")],
    ]
    events = await _run(monkeypatch, engine, rounds)

    file_events = [e for e in events if e["type"] == "file"]
    assert len(file_events) == 1
    assert file_events[0]["filename"] == "laporan.docx"
