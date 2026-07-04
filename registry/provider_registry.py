"""Provider Registry — catalogue of available LLM providers and their config.

Pure metadata layer (no provider class imports) so it stays free of heavy
dependencies and import cycles. The factory (``providers/provider_factory.py``)
reads this to decide which providers are enabled and how to configure them.

A provider is considered *enabled* when its prerequisite is satisfied:
Ollama is always available (local); cloud providers require their API key in
the environment. See MASTER_INSTRUCTION.md Bab 16.2 and Bab 20.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.config import settings


@dataclass(frozen=True)
class ProviderConfig:
    """Static description of a provider entry in the registry."""

    name: str
    default_model: str
    requires_api_key: bool
    env_key_name: str  # informational: which env var holds the credential
    enabled: bool


def _cloud_enabled(api_key: str) -> bool:
    return bool(api_key and api_key.strip())


def build_provider_registry() -> dict[str, ProviderConfig]:
    """Return the current provider catalogue, computed from settings.

    Recomputed from ``settings`` on each call so tests can monkeypatch env
    values without stale module-level state.
    """
    return {
        "ollama": ProviderConfig(
            name="ollama",
            default_model=settings.GEMMA_MODEL,
            requires_api_key=False,
            env_key_name="",
            enabled=True,  # local, always available
        ),
        "openai": ProviderConfig(
            name="openai",
            default_model=settings.OPENAI_MODEL,
            requires_api_key=True,
            env_key_name="OPENAI_API_KEY",
            enabled=_cloud_enabled(settings.OPENAI_API_KEY),
        ),
        "claude": ProviderConfig(
            name="claude",
            default_model=settings.CLAUDE_MODEL,
            requires_api_key=True,
            env_key_name="ANTHROPIC_API_KEY",
            enabled=_cloud_enabled(settings.ANTHROPIC_API_KEY),
        ),
        "gemini": ProviderConfig(
            name="gemini",
            default_model=settings.GEMINI_MODEL,
            requires_api_key=True,
            env_key_name="GOOGLE_API_KEY",
            enabled=_cloud_enabled(settings.GOOGLE_API_KEY),
        ),
    }


def get_provider_config(name: str) -> ProviderConfig | None:
    """Return the config for ``name``, or ``None`` if not registered."""
    return build_provider_registry().get(name)


def list_providers() -> list[str]:
    """All registered provider names (enabled or not)."""
    return list(build_provider_registry().keys())


def list_enabled_providers() -> list[str]:
    """Provider names that are currently usable (local or key-configured)."""
    return [name for name, cfg in build_provider_registry().items() if cfg.enabled]
