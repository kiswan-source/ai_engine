"""Agent capability classification (Fase 2, R-08 — DCF v5 mandate "Agent
Ecosystem Evolution": AGENT MANAGER > SPECIALIST / EXECUTOR / VALIDATOR).

This is deliberately metadata, not a new class hierarchy: all 15 roles are
still one ``GenericLLMAgent`` class (see that module's docstring for why a
full ``SpecialistAgent``/``ExecutorAgent``/``ValidatorAgent`` subclass split
was rejected for this pass — regression risk against the 685-test suite for
a benefit ``agents/validation_guard.py`` already delivers without it). What
actually closes R-08 ("builder tidak boleh menjadi validator dirinya
sendiri") is that guard module, which reads the ``AgentCapability`` this file
assigns — this file alone is just a label, same category of promise the v5
blueprint explicitly warned isn't evidence on its own.
"""
from __future__ import annotations

from enum import Enum

from registry.model_registry import ROLES


class AgentCapability(Enum):
    """Which of the mandate's three authority tiers a role belongs to."""

    SPECIALIST = "specialist"  # reasoning / research / analysis / knowledge
    EXECUTOR = "executor"  # performs actions, runs tools, produces artifacts
    VALIDATOR = "validator"  # critiques, tests, arbitrates, approves


ROLE_CAPABILITY: dict[str, AgentCapability] = {
    "planner": AgentCapability.SPECIALIST,
    "research": AgentCapability.SPECIALIST,
    "analyst": AgentCapability.SPECIALIST,
    "vision": AgentCapability.SPECIALIST,
    "prompt_optimizer": AgentCapability.SPECIALIST,
    "cost_optimizer": AgentCapability.SPECIALIST,
    "memory": AgentCapability.SPECIALIST,
    "writer": AgentCapability.EXECUTOR,
    "tool": AgentCapability.EXECUTOR,
    "reviewer": AgentCapability.VALIDATOR,
    "critic": AgentCapability.VALIDATOR,
    "consensus": AgentCapability.VALIDATOR,
    "guardrail": AgentCapability.VALIDATOR,
    "reflection": AgentCapability.VALIDATOR,
    "confidence": AgentCapability.VALIDATOR,
}

_missing = set(ROLES) - set(ROLE_CAPABILITY)
if _missing:
    raise RuntimeError(
        f"agents.capabilities.ROLE_CAPABILITY is missing an entry for: {sorted(_missing)} "
        "— every canonical role in registry.model_registry.ROLES must be classified"
    )


def capability_for(role: str) -> AgentCapability:
    """Return the :class:`AgentCapability` for ``role``.

    Raises:
        KeyError: If ``role`` isn't a canonical role (see ``ROLES``).
    """
    try:
        return ROLE_CAPABILITY[role]
    except KeyError as exc:
        raise KeyError(
            f"unknown agent role: {role!r} (known: {', '.join(sorted(ROLE_CAPABILITY))})"
        ) from exc
