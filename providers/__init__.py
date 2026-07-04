"""Provider abstraction layer for AI_ENGINE (MASTER_INSTRUCTION.md Bab 16).

Public surface — import providers via the factory, never instantiate concrete
provider classes directly in business logic (Bab 16.2, Bab 45.5).
"""
from .base_provider import BaseProvider, Chunk, GenerationParams, ProviderResponse
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
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIProvider
from .provider_factory import create_for_role, create_provider

__all__ = [
    "AIEngineError",
    "BaseProvider",
    "Chunk",
    "ClaudeProvider",
    "GeminiProvider",
    "GenerationParams",
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
