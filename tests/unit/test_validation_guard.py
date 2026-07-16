"""Unit tests for the validator-independence guard (Fase 2, R-08)."""
import pytest

from agents.base_agent import AgentResult, BaseAgent, Task
from agents.validation_guard import ValidatorNotIndependentError, assert_independent_validator


class _StubAgent(BaseAgent):
    """Minimal BaseAgent subclass — proves `.capability` is inherited from
    `role` with no override needed (Fase 2 design goal: zero changes required
    to existing agent subclasses, including test doubles)."""

    def __init__(self, role: str, agent_id: str) -> None:
        self.role = role
        self.agent_id = agent_id
        self.default_provider = "stub"

    async def execute(self, task: Task) -> AgentResult:  # pragma: no cover - not exercised
        raise NotImplementedError

    async def health_check(self) -> bool:  # pragma: no cover - not exercised
        return True


def test_generic_base_agent_subclass_gets_capability_from_role():
    """No override needed on BaseAgent subclasses — this is what keeps the
    guard additive rather than a breaking change to every existing agent."""
    reviewer = _StubAgent(role="reviewer", agent_id="reviewer-1")
    writer = _StubAgent(role="writer", agent_id="writer-1")
    from agents.capabilities import AgentCapability

    assert reviewer.capability is AgentCapability.VALIDATOR
    assert writer.capability is AgentCapability.EXECUTOR


def test_passes_for_independent_validator():
    validator = _StubAgent(role="consensus", agent_id="consensus-agent")
    assert_independent_validator(["writer-agent", "analyst-agent"], validator) is None


def test_rejects_non_validator_capability():
    non_validator = _StubAgent(role="writer", agent_id="writer-agent-2")
    with pytest.raises(ValidatorNotIndependentError, match="cannot act as a validator"):
        assert_independent_validator(["writer-agent"], non_validator)


def test_rejects_validator_that_is_also_the_producer():
    self_validating = _StubAgent(role="critic", agent_id="critic-agent")
    with pytest.raises(ValidatorNotIndependentError, match="cannot validate its own output"):
        assert_independent_validator(["writer-agent", "critic-agent"], self_validating)


def test_rejects_specialist_capability_too():
    specialist = _StubAgent(role="planner", agent_id="planner-agent")
    with pytest.raises(ValidatorNotIndependentError, match="cannot act as a validator"):
        assert_independent_validator(["writer-agent"], specialist)
