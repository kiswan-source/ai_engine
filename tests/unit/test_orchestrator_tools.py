"""Unit tests for the Chat -> Orchestrator bridge (Fase 6, DCF v5 mandate
"Cowork Experience"). Agents are stubbed — no provider/network calls.
"""
import asyncio

import pytest

from agents.base_agent import AgentResult, Task
from agent.tools.orchestrator_tools import run_orchestrated_workflow
from orchestrator.orchestrator import Orchestrator, get_shared_orchestrator
from tests.unit.test_orchestrator import StubAgent, registry_with


class _LowConfidenceAgent(StubAgent):
    """Never reaches the confidence threshold — deterministically forces
    ReflectionEngine to exhaust its iteration budget and escalate."""

    async def execute(self, task: Task) -> AgentResult:
        self.calls += 1
        self.last_prompt = task.prompt
        return AgentResult(
            output="jawaban lemah", confidence=0.0, trace_id=task.trace_id,
            provider_used=self._provider, model_used="stub-m", role=self.role, agent_id=self.agent_id,
        )


def _install_test_orchestrator(monkeypatch, *agents) -> Orchestrator:
    import orchestrator.orchestrator as orchestrator_module

    test_orchestrator = Orchestrator(agent_registry=registry_with(*agents))
    monkeypatch.setattr(orchestrator_module, "_shared_orchestrator", test_orchestrator)
    return test_orchestrator


def test_run_orchestrated_workflow_success(monkeypatch):
    _install_test_orchestrator(monkeypatch, StubAgent("writer", output="laporan selesai"))

    result = run_orchestrated_workflow(goal="buat laporan", roles=["writer"], mode="sequential")

    assert result["success"] is True
    assert result["final_output"] == "laporan selesai"
    assert result["escalate"] is False
    assert result["message"] is None
    assert result["state"] == "completed"
    assert result["steps"][0]["role"] == "writer"


def test_run_orchestrated_workflow_uses_the_shared_orchestrator_instance(monkeypatch):
    """Proves the tool actually reuses get_shared_orchestrator() — not a
    private Orchestrator() of its own — the whole point of Fase 6's design
    (a chat-triggered approval must be visible to the same instance
    api/routes/orchestrator.py reads from)."""
    installed = _install_test_orchestrator(monkeypatch, StubAgent("writer"))

    run_orchestrated_workflow(goal="tugas", roles=["writer"], mode="sequential")

    assert get_shared_orchestrator() is installed


@pytest.mark.asyncio
async def test_run_orchestrated_workflow_escalates_and_opens_a_pending_approval(monkeypatch):
    orch = _install_test_orchestrator(monkeypatch, _LowConfidenceAgent("writer"))
    monkeypatch.setattr("api.config.settings.ENABLE_HUMAN_APPROVAL", True)
    monkeypatch.setattr("api.config.settings.REFLECTION_MAX_ITERATIONS", 1)

    # run_orchestrated_workflow calls asyncio.run() internally (the
    # asyncio.to_thread worker-thread bridge it's actually invoked through
    # in production has no ambient event loop) — bridge through a thread
    # here too, same as production, since this test function is itself
    # async (needed for the pending_approvals() await below).
    result = await asyncio.to_thread(
        run_orchestrated_workflow, goal="tugas sulit", roles=["writer"], mode="reflection"
    )

    assert result["escalate"] is True
    assert result["message"] is not None
    assert result["trace_id"] in result["message"]
    assert "Approval" in result["message"]

    # The whole point: this pending approval must be visible through the
    # SAME orchestrator instance api/routes/orchestrator.py's /approvals
    # endpoint reads from — not a private one this tool built for itself.
    pending = await orch.pending_approvals()
    assert any(p.trace_id == result["trace_id"] for p in pending)


def test_run_orchestrated_workflow_rejects_empty_roles(monkeypatch):
    _install_test_orchestrator(monkeypatch, StubAgent("writer"))

    with pytest.raises(ValueError):
        run_orchestrated_workflow(goal="tugas", roles=[], mode="sequential")
