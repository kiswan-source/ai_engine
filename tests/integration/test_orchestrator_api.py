"""Integration tests for /api/v1/orchestrator/* (the web UI's Multi-Agent panel).

Agents are stubbed exactly like tests/unit/test_orchestrator.py — no live
provider/network calls (Bab 12.3). The module-level ``_orchestrator`` singleton
in api.routes.orchestrator is swapped per-test via monkeypatch so state
(pending approvals) doesn't leak between tests.
"""
import dataclasses

import pytest
from httpx import ASGITransport, AsyncClient

from agents.base_agent import AgentResult, BaseAgent, Task
from orchestrator import Orchestrator
from registry.agent_registry import AgentRegistry


class StubAgent(BaseAgent):
    def __init__(self, role, output="ok", provider="stub"):
        self.role = role
        self.agent_id = f"{role}-stub"
        self.default_provider = provider
        self._output = output
        self._provider = provider

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult(
            output=self._output, confidence=0.8, trace_id=task.trace_id,
            provider_used=self._provider, model_used="stub-m", role=self.role, agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


class UnconfidentAgent(StubAgent):
    async def execute(self, task):
        res = await super().execute(task)
        return dataclasses.replace(res, confidence=0.01)


def registry_with(*agents) -> AgentRegistry:
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg


@pytest.fixture
async def app():
    from api.main import app as _app
    yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def stub_orchestrator(monkeypatch):
    """Install a fresh Orchestrator backed by stub agents as the route's singleton."""
    import api.routes.orchestrator as route

    def _install(*agents):
        orch = Orchestrator(agent_registry=registry_with(*agents))
        monkeypatch.setattr(route, "_orchestrator", orch)
        return orch

    return _install


async def test_list_roles(client):
    res = await client.get("/api/v1/orchestrator/roles")
    assert res.status_code == 200
    roles = res.json()["roles"]
    assert "writer" in roles and "planner" in roles


async def test_list_modes(client):
    res = await client.get("/api/v1/orchestrator/modes")
    assert res.status_code == 200
    assert set(res.json()["modes"]) == {"sequential", "parallel", "reflection", "voting", "consensus"}


async def test_run_rejects_empty_roles(client):
    res = await client.post("/api/v1/orchestrator/run", json={"prompt": "hi", "roles": []})
    assert res.status_code == 400


async def test_run_rejects_unknown_mode(client, stub_orchestrator):
    stub_orchestrator(StubAgent("writer"))
    res = await client.post(
        "/api/v1/orchestrator/run", json={"prompt": "hi", "roles": ["writer"], "mode": "nope"}
    )
    assert res.status_code == 400


async def test_run_sequential_completes(client, stub_orchestrator):
    stub_orchestrator(StubAgent("writer", output="hasil"))
    res = await client.post(
        "/api/v1/orchestrator/run", json={"prompt": "tulis", "roles": ["writer"], "mode": "sequential"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "completed"
    assert data["final_output"] == "hasil"
    assert data["results"][0]["role"] == "writer"


async def test_run_escalates_and_appears_in_pending_approvals(client, stub_orchestrator):
    stub_orchestrator(UnconfidentAgent("writer", output="jawaban lemah"))
    run_res = await client.post(
        "/api/v1/orchestrator/run", json={"prompt": "tulis", "roles": ["writer"], "mode": "reflection"}
    )
    assert run_res.status_code == 200
    data = run_res.json()
    assert data["state"] == "reviewing"
    assert data["escalate"] is True

    approvals_res = await client.get("/api/v1/orchestrator/approvals")
    assert approvals_res.status_code == 200
    pending = approvals_res.json()["approvals"]
    assert any(a["trace_id"] == data["trace_id"] for a in pending)


async def test_decide_approval_completes_workflow(client, stub_orchestrator):
    stub_orchestrator(UnconfidentAgent("writer", output="jawaban lemah"))
    run_res = await client.post(
        "/api/v1/orchestrator/run", json={"prompt": "tulis", "roles": ["writer"], "mode": "reflection"}
    )
    trace_id = run_res.json()["trace_id"]

    decide_res = await client.post(
        f"/api/v1/orchestrator/approvals/{trace_id}/decide",
        json={"approved": True, "decided_by": "rudy"},
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["state"] == "completed"


async def test_decide_approval_unknown_trace_id_404(client, stub_orchestrator):
    stub_orchestrator(StubAgent("writer"))
    res = await client.post(
        "/api/v1/orchestrator/approvals/does-not-exist/decide",
        json={"approved": True, "decided_by": "rudy"},
    )
    assert res.status_code == 404


async def test_decide_approval_denies_insufficient_role(client, stub_orchestrator, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "userkey:user")
    stub_orchestrator(UnconfidentAgent("writer", output="jawaban lemah"))
    run_res = await client.post(
        "/api/v1/orchestrator/run", json={"prompt": "tulis", "roles": ["writer"], "mode": "reflection"}
    )
    trace_id = run_res.json()["trace_id"]

    res = await client.post(
        f"/api/v1/orchestrator/approvals/{trace_id}/decide",
        json={"approved": True, "decided_by": "eve"},
        headers={"X-API-Key": "userkey"},
    )
    assert res.status_code == 403
