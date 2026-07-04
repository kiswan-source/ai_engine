"""Model Registry — maps agent *roles* to concrete *provider + model*.

This is the single place that decides "which model runs this role", separating
that decision from agent code (MASTER_INSTRUCTION.md Bab 20). Swapping a model
or migrating a role to another vendor is a config change here, not a code change.

Each role has a primary assignment and a fallback used by the Fallback Strategy
(Bab 54) when the primary provider is unavailable. Defaults follow the table in
Bab 17.1 / Bab 20.

NOTE: In this environment only Ollama is wired to a live key, so every default
below also carries an Ollama-based fallback — the system degrades to local
inference instead of failing when a cloud key is absent. Once cloud keys are
configured, the primaries activate automatically.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.config import settings

# Canonical agent roles (Bab 17.1).
ROLES = (
    "planner",
    "research",
    "analyst",
    "writer",
    "reviewer",
    "memory",
    "guardrail",
    "prompt_optimizer",
    "tool",
    "vision",
    "reflection",
    "critic",
    "consensus",
    "cost_optimizer",
    "confidence",
)


@dataclass(frozen=True)
class ModelAssignment:
    """Resolved routing target for a role: which provider + model to call."""

    role: str
    provider: str
    model: str
    fallback_provider: str
    fallback_model: str


def _local() -> tuple[str, str]:
    """Local Ollama fallback pair (provider, model)."""
    return ("ollama", settings.GEMMA_MODEL)


def build_model_registry() -> dict[str, ModelAssignment]:
    """Return the role→model routing table, computed from settings.

    Primary providers follow Bab 20; fallbacks default to local Ollama so the
    platform stays functional without cloud keys.
    """
    local_provider, local_model = _local()

    # (role, primary_provider, primary_model)
    primaries: dict[str, tuple[str, str]] = {
        "planner": ("openai", settings.OPENAI_MODEL),
        "research": ("gemini", settings.GEMINI_MODEL),
        "analyst": ("claude", settings.CLAUDE_MODEL),
        "writer": ("claude", settings.CLAUDE_MODEL),
        "reviewer": ("openai", settings.OPENAI_MODEL),
        "vision": ("gemini", settings.GEMINI_MODEL),
        "reflection": ("claude", settings.CLAUDE_MODEL),
        "critic": ("claude", settings.CLAUDE_MODEL),
        "consensus": ("openai", settings.OPENAI_MODEL),
        "confidence": ("claude", settings.CLAUDE_MODEL),
        # Low-cost / local-first roles (Bab 17.1).
        "memory": (local_provider, local_model),
        "guardrail": (local_provider, local_model),
        "prompt_optimizer": (local_provider, local_model),
        "tool": (local_provider, local_model),
        "cost_optimizer": (local_provider, local_model),
    }

    registry: dict[str, ModelAssignment] = {}
    for role, (provider, model) in primaries.items():
        registry[role] = ModelAssignment(
            role=role,
            provider=provider,
            model=model,
            fallback_provider=local_provider,
            fallback_model=local_model,
        )
    return registry


def resolve(role: str) -> ModelAssignment:
    """Return the :class:`ModelAssignment` for ``role``.

    Raises:
        KeyError: If the role is unknown (not in :data:`ROLES`).
    """
    registry = build_model_registry()
    if role not in registry:
        raise KeyError(f"unknown agent role: {role!r} (known: {', '.join(sorted(registry))})")
    return registry[role]
