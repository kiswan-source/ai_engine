"""Unit tests for agent capability classification (Fase 2, R-08)."""
import pytest

from agents.capabilities import AgentCapability, ROLE_CAPABILITY, capability_for
from registry.model_registry import ROLES


def test_every_canonical_role_is_classified():
    assert set(ROLE_CAPABILITY) == set(ROLES)


@pytest.mark.parametrize(
    "role,expected",
    [
        ("planner", AgentCapability.SPECIALIST),
        ("research", AgentCapability.SPECIALIST),
        ("analyst", AgentCapability.SPECIALIST),
        ("writer", AgentCapability.EXECUTOR),
        ("tool", AgentCapability.EXECUTOR),
        ("reviewer", AgentCapability.VALIDATOR),
        ("critic", AgentCapability.VALIDATOR),
        ("consensus", AgentCapability.VALIDATOR),
        ("guardrail", AgentCapability.VALIDATOR),
        ("reflection", AgentCapability.VALIDATOR),
        ("confidence", AgentCapability.VALIDATOR),
    ],
)
def test_capability_for_known_roles(role, expected):
    assert capability_for(role) is expected


def test_capability_for_unknown_role_raises_key_error():
    with pytest.raises(KeyError):
        capability_for("not_a_real_role")
