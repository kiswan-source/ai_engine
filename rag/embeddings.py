"""Embeddings (MASTER_INSTRUCTION.md Bab 29 step 2) — text -> vector.

Shared by the RAG document pipeline and ``memory/vector_memory.py``'s Vector
Memory tier (Bab 22 calls that tier "basis RAG" — one embedding function
instead of two copies to keep in sync). Real embedding goes through a
provider's ``.embed()`` (Bab 16.1, Bab 20); ``hashed_bow_embedder`` is the
dependency-free fallback used when no embedding-capable provider is
configured, so CI/dev without cloud keys still works (Bab 12).

Providers are never mixed automatically for embeddings the way generation
falls back across providers (Bab 54): different providers' embeddings have
different dimensions and aren't comparable, so a misconfigured/disabled
provider falls back to the deterministic hashed placeholder, not another
cloud provider that would silently produce incompatible vectors.
"""
from __future__ import annotations

import hashlib
import re
from typing import Awaitable, Callable

from core.utils.logger import get_logger

logger = get_logger(__name__)

Embedder = Callable[[str], Awaitable[list[float]]]

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Providers whose BaseProvider.embed() hits a real endpoint (Bab 16.1). Claude
# is intentionally absent — Anthropic has no embeddings API.
_EMBEDDING_CAPABLE = frozenset({"openai", "gemini", "ollama"})


def hashed_bow_embedder_factory(dim: int) -> Embedder:
    """Deterministic hashed bag-of-words embedder at a given width."""

    async def _embed(text: str) -> list[float]:
        vec = [0.0] * dim
        for token in _TOKEN_RE.findall(text.lower()):
            digest = hashlib.md5(token.encode()).digest()
            vec[int.from_bytes(digest[:4], "little") % dim] += 1.0
        return vec

    return _embed


hashed_bow_embedder: Embedder = hashed_bow_embedder_factory(512)
"""512-wide placeholder embedder — stable default for tests/offline use."""


def provider_embedder(provider_name: str) -> Embedder:
    """Build an embedder backed by a configured provider's ``.embed()``.

    Raises:
        ValueError: If ``provider_name`` has no embedding endpoint wired up.
    """
    if provider_name not in _EMBEDDING_CAPABLE:
        raise ValueError(
            f"provider {provider_name!r} has no embedding endpoint "
            f"(embedding-capable: {sorted(_EMBEDDING_CAPABLE)})"
        )

    async def _embed(text: str) -> list[float]:
        from providers.provider_factory import create_provider

        provider = create_provider(provider_name)
        return await provider.embed(text)

    return _embed


def default_embedder() -> Embedder:
    """Embedder chosen by settings: the configured provider, or hashed-BOW.

    Falls back automatically rather than raising, so dev/CI without cloud
    keys still works (Bab 12) — ``RAG_EMBEDDING_PROVIDER=hashed`` selects the
    placeholder explicitly; any other unconfigured/disabled provider falls
    back to it with a warning instead of failing every ingest/query call.
    """
    from api.config import settings
    from registry.provider_registry import get_provider_config

    name = settings.RAG_EMBEDDING_PROVIDER
    if name == "hashed":
        return hashed_bow_embedder_factory(settings.RAG_EMBEDDING_DIM)

    cfg = get_provider_config(name)
    if cfg is None or not cfg.enabled:
        logger.warning("rag.embedding_fallback", configured=name, reason="provider not enabled")
        return hashed_bow_embedder_factory(settings.RAG_EMBEDDING_DIM)

    return provider_embedder(name)
