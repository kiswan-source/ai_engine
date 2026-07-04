"""Provider Factory — the only sanctioned way to instantiate a provider.

Callers (agents, orchestrator) must never call ``OpenAIProvider()`` directly
(Bab 16.2, Bab 45.5); they ask the factory, which reads the provider registry
(Bab 16) and model registry (Bab 20) to build a correctly configured instance.
"""
from __future__ import annotations

from core.utils.logger import get_logger
from registry import model_registry, provider_registry

from .base_provider import BaseProvider
from .claude_provider import ClaudeProvider
from .exceptions import ProviderNotConfiguredError, UnknownProviderError
from .gemini_provider import GeminiProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider

logger = get_logger(__name__)

# Registry name -> provider class.
_PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "gemini": GeminiProvider,
}


def create_provider(name: str, model: str | None = None) -> BaseProvider:
    """Instantiate the provider registered under ``name``.

    Args:
        name: Registered provider name (e.g. ``"ollama"``, ``"openai"``).
        model: Optional model override; defaults to the registry's default model.

    Returns:
        A ready-to-use :class:`BaseProvider` instance.

    Raises:
        UnknownProviderError: If ``name`` is not registered.
    """
    provider_cls = _PROVIDER_CLASSES.get(name)
    if provider_cls is None:
        raise UnknownProviderError(
            f"unknown provider {name!r} (registered: {', '.join(sorted(_PROVIDER_CLASSES))})"
        )
    cfg = provider_registry.get_provider_config(name)
    resolved_model = model or (cfg.default_model if cfg else None)
    logger.info("provider.create", provider=name, model=resolved_model)
    return provider_cls(model=resolved_model)


def create_for_role(role: str, prefer_fallback: bool = False) -> BaseProvider:
    """Build the provider for an agent ``role`` per the Model Registry (Bab 20).

    Falls back to the role's local fallback assignment when the primary provider
    is not enabled (no API key), so callers get a usable provider instead of an
    immediate failure (Bab 54 — Fallback Strategy). Set ``prefer_fallback`` to
    force the fallback assignment directly.

    Args:
        role: Agent role name (see :data:`registry.model_registry.ROLES`).
        prefer_fallback: Skip the primary and use the fallback assignment.

    Returns:
        A configured :class:`BaseProvider` for the role.
    """
    assignment = model_registry.resolve(role)

    if prefer_fallback:
        return create_provider(assignment.fallback_provider, assignment.fallback_model)

    primary_cfg = provider_registry.get_provider_config(assignment.provider)
    if primary_cfg is not None and primary_cfg.enabled:
        return create_provider(assignment.provider, assignment.model)

    logger.warning(
        "provider.role_fallback",
        role=role,
        primary=assignment.provider,
        fallback=assignment.fallback_provider,
        reason="primary provider not enabled",
    )
    return create_provider(assignment.fallback_provider, assignment.fallback_model)
