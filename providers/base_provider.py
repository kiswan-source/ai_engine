"""Provider abstraction layer — shared interface for every LLM vendor.

Concrete implementation of Hexagonal Architecture (Bab 4.2) and Dependency
Inversion (Bab 4.3): the orchestrator/agents depend on ``BaseProvider`` (a port),
never on a concrete vendor SDK. See MASTER_INSTRUCTION.md Bab 16.

Interface required by Bab 16.1:
    generate(prompt, params) -> ProviderResponse
    stream(prompt, params)   -> AsyncIterator[Chunk]
    embed(text)              -> list[float]        (if supported)
    count_tokens(text)       -> int
    health_check()           -> bool
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, AsyncIterator

from .exceptions import ProviderCapabilityError


@dataclass(frozen=True)
class ImageInput:
    """One base64-encoded image attached to a generation call (Bab 17 Vision role).

    ``data`` is the raw base64 payload with no ``data:`` URI prefix — callers
    at the API boundary (e.g. ``api/routes/orchestrator.py``) strip that off
    before this reaches a provider, so every provider's ``_payload()`` can
    assume the same shape regardless of what the frontend sent.
    """

    data: str
    mime_type: str = "image/png"


@dataclass(frozen=True)
class GenerationParams:
    """Immutable value object holding generation parameters (Bab 7).

    A single typed object keeps the ``generate``/``stream`` signature stable as
    new knobs are added, instead of an ever-growing kwargs list.
    """

    system: str = ""
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    stop: tuple[str, ...] = ()
    use_cache: bool = True
    images: tuple[ImageInput, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    # Tool-calling (Fase 14, DCF v5 mandate — orchestrator agent tool access):
    # ``tools`` is a tuple of OpenAI/Ollama-style ``{"type": "function",
    # "function": {...}}`` schemas; ``tool_executor`` is an async callable
    # ``(name, args) -> Any`` a provider invokes for each tool call it
    # receives, so the round-trip (call model -> get tool_calls -> execute ->
    # feed result back -> call model again) stays entirely inside the
    # provider that natively supports it. Both default to "off" so every
    # existing caller (every role except EXECUTOR-capability ones, see
    # ``agents/capabilities.py``) is completely unaffected. A provider that
    # doesn't implement tool-calling simply ignores these two fields and
    # generates a plain completion — deliberate graceful degrade (Gate 1
    # decision), not an error, since only ``OllamaProvider`` implements this
    # today.
    tools: tuple[dict[str, Any], ...] = ()
    tool_executor: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None


@dataclass(frozen=True)
class ProviderResponse:
    """Normalised, vendor-agnostic result of a completion call.

    Every provider maps its raw payload into this shape so downstream consumers
    (Consensus Engine, Cost Tracker, Observability) never touch vendor formats.
    """

    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str | None = None
    raw: dict[str, Any] | None = None
    # Populated only by a provider that actually executed
    # ``GenerationParams.tools`` calls via ``tool_executor`` (Fase 14) — one
    # entry per call made across every round: ``{"name", "args", "success",
    # "file"}``. ``file`` is the produced artifact's path when the tool
    # result carried one (mirrors ``core/chat/engine.py``'s ``result["file"]``
    # convention), so callers can surface a real downloadable file without
    # re-parsing free-text output.
    tool_calls_made: tuple[dict[str, Any], ...] = ()

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class Chunk:
    """A single streamed fragment of a completion."""

    text: str
    done: bool = False


class BaseProvider(ABC):
    """Standard interface every LLM provider in AI_ENGINE must implement.

    Attributes:
        name: Stable provider identifier used by the registry/factory
            (e.g. ``"openai"``, ``"ollama"``).
        model: Concrete model id this instance talks to.
    """

    name: str = "base"

    def __init__(self, model: str) -> None:
        self.model = model

    @property
    def base_url(self) -> str:
        """Actual endpoint this provider talks to — used by
        ``security.endpoint_policy.is_internal_endpoint`` to decide whether
        PII redaction is needed (Fase 1, SEC-4: classify by real location,
        not provider name). Default reads ``self._base_url`` (the attribute
        name OpenAI/Gemini/Claude providers already use); override directly
        for providers that store it elsewhere (e.g. ``OllamaProvider`` wraps
        ``GemmaClient``, which owns its own ``base_url``)."""
        return getattr(self, "_base_url", "")

    @abstractmethod
    async def generate(self, prompt: str, params: GenerationParams | None = None) -> ProviderResponse:
        """Produce a single (non-streamed) completion.

        Args:
            prompt: User/content prompt sent to the model.
            params: Generation parameters; defaults applied when ``None``.

        Returns:
            ProviderResponse: Normalised result.

        Raises:
            ProviderTimeoutError: If the call exceeds its timeout.
            ProviderResponseError: On non-2xx status or malformed payload.
            ProviderNotConfiguredError: If required credentials are missing.
        """
        raise NotImplementedError

    @abstractmethod
    async def stream(self, prompt: str, params: GenerationParams | None = None) -> AsyncIterator[Chunk]:
        """Produce a completion as a stream of :class:`Chunk` objects."""
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Return ``True`` when the provider is reachable and usable."""
        raise NotImplementedError

    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for ``text``.

        Providers without an embedding endpoint keep the default, which raises
        :class:`ProviderCapabilityError` (embeddings are optional per Bab 16.1).
        """
        raise ProviderCapabilityError("embeddings not supported", provider=self.name)

    def count_tokens(self, text: str) -> int:
        """Estimate token count for cost & context-window budgeting (Bab 50, 56).

        The default is a cheap ~4-chars-per-token heuristic. Providers with a
        real tokenizer/endpoint should override this for accuracy.
        """
        if not text:
            return 0
        return max(1, len(text) // 4)
