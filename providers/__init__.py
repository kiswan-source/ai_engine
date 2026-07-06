"""Provider abstraction layer for AI_ENGINE (MASTER_INSTRUCTION.md Bab 16).

Public surface — import providers via the factory, never instantiate concrete
provider classes directly in business logic (Bab 16.2, Bab 45.5).
"""
from .base_provider import BaseProvider, Chunk, GenerationParams, ImageInput, ProviderResponse
from .circuit_breaker import BreakerConfig, CircuitBreaker, CircuitBreakerRegistry, CircuitState
from .claude_provider import ClaudeProvider
from .exceptions import (
    AIEngineError,
    ProviderCapabilityError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResponseError,
    ProviderTimeoutError,
    UnknownProviderError,
)
from .gemini_provider import GeminiProvider
from .mock_provider import MockProvider
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .provider_factory import create_for_role, create_provider

__all__ = [
    "AIEngineError",
    "BaseProvider",
    "BreakerConfig",
    "Chunk",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitState",
    "ClaudeProvider",
    "GeminiProvider",
    "GenerationParams",
    "ImageInput",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "ProviderCapabilityError",
    "ProviderError",
    "ProviderNotConfiguredError",
    "ProviderResponse",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "UnknownProviderError",
    "create_for_role",
    "create_provider",
]
