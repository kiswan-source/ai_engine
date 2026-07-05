"""Unit tests for AIAgent's role threading into ToolRegistry.execute() (ADR-0013).

No live Ollama/registry I/O (Bab 12.3) — the registry's execute() is stubbed
per test so only AIAgent's own wiring (role passed through, PermissionError
turned into a failed StepResult + audit entry) is under test.
"""
from agent.core import AIAgent
from agent.schemas import ToolCall
from security import audit_log


def _agent(role):
    agent = AIAgent(role=role)
    return agent


async def test_execute_passes_role_to_registry(monkeypatch):
    agent = _agent("operator")
    seen = {}

    def fake_execute(name, input_data, role=None):
        seen["role"] = role
        return {"file": "out.pdf"}

    monkeypatch.setattr(agent.registry, "has", lambda name: True)
    monkeypatch.setattr(agent.registry, "execute", fake_execute)

    result = await agent._execute(ToolCall(tool="write_pdf", input={}), step_num=1)

    assert seen["role"] == "operator"
    assert result.success


async def test_execute_denied_role_becomes_failed_step_and_audit_entry(monkeypatch, tmp_path):
    agent = _agent("user")

    def fake_execute(name, input_data, role=None):
        raise PermissionError(f"role {role!r} lacks permission 'tool:write_pdf'")

    monkeypatch.setattr(agent.registry, "has", lambda name: True)
    monkeypatch.setattr(agent.registry, "execute", fake_execute)

    result = await agent._execute(ToolCall(tool="write_pdf", input={}), step_num=1)

    assert not result.success
    assert "lacks permission" in result.error

    entries = audit_log.read_recent()
    assert any(e.event_type == "tool_access.denied" and e.actor == "user" for e in entries)


async def test_execute_without_role_unaffected(monkeypatch):
    agent = _agent(None)
    seen = {}

    def fake_execute(name, input_data, role=None):
        seen["role"] = role
        return {"text": "ok"}

    monkeypatch.setattr(agent.registry, "has", lambda name: True)
    monkeypatch.setattr(agent.registry, "execute", fake_execute)

    result = await agent._execute(ToolCall(tool="read_txt", input="a.txt"), step_num=1)

    assert seen["role"] is None
    assert result.success
