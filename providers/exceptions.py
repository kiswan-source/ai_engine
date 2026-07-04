"""Exception hierarchy for the provider layer.

Per MASTER_INSTRUCTION.md Bab 10, every domain error derives from a shared
base ``AIEngineError``. The provider layer is the first module of the v4
enterprise stack to be built, so the shared base lives here for now; higher
layers (orchestrator, agents) may import it. It can be hoisted to a dedicated
shared module later without breaking callers, since only the import path would
change.

All vendor-specific errors (OpenAI/Anthropic/Google/Ollama HTTP failures) MUST
be normalised to one of these internal exceptions before they bubble up to the
orchestrator, so callers never depend on a particular vendor's error shape
(Bab 10.6).
"""
from __future__ import annotations


class AIEngineError(Exception):
    """Base exception for every domain error in AI_ENGINE (Bab 10)."""


class ProviderError(AIEngineError):
    """Base for all provider-layer failures.

    Args:
        message: Human-friendly description.
        provider: Name of the provider that failed (e.g. ``"openai"``).
    """

    def __init__(self, message: str, provider: str | None = None) -> None:
        self.provider = provider
        prefix = f"[{provider}] " if provider else ""
        super().__init__(f"{prefix}{message}")


class ProviderTimeoutError(ProviderError):
    """Raised when a provider call exceeds its timeout budget."""


class ProviderNotConfiguredError(ProviderError):
    """Raised when a provider is used without required config (e.g. API key)."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns an error status or malformed payload."""


class ProviderCapabilityError(ProviderError):
    """Raised when a provider is asked for a capability it does not support
    (e.g. embeddings on a model that has no embedding endpoint)."""


class UnknownProviderError(AIEngineError):
    """Raised by the factory/registry when an unregistered provider is requested."""
