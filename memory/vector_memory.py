"""Vector Memory — embedding store for semantic recall (Bab 22, basis RAG Bab 29).

Tahap 3 shipped the *interface* plus a dependency-free implementation, with a
promise (ADR-0006) that Tahap 5 would wire a real embedder and a real vector
store behind the same ``add``/``search`` contract. This is that wiring: the
embedding + storage mechanics now live in ``rag/`` (Bab 22 itself calls this
tier "basis RAG" — one shared implementation instead of two to keep in sync),
and this module stays the Shared Memory tier facade over them.

``memory_manager.build_memory_manager()`` decides the actual embedder/store
from settings (real provider + pgvector, or the offline defaults); this
class's own constructor defaults stay dependency-free, so a bare
``VectorMemory()`` never needs a network call or a database (Bab 12).
"""
from __future__ import annotations

from typing import Any

from rag.embeddings import Embedder, hashed_bow_embedder
from rag.knowledge_store import InMemoryKnowledgeStore, KnowledgeHit, KnowledgeStore

VectorHit = KnowledgeHit
"""Alias kept for backward compatibility — this tier named its result type
``VectorHit`` since Tahap 3; it's the same shape as
:class:`rag.knowledge_store.KnowledgeHit` now that the storage is shared."""


class VectorMemory:
    """Semantic index over one namespace of a pluggable :class:`KnowledgeStore`."""

    def __init__(
        self,
        embedder: Embedder | None = None,
        store: KnowledgeStore | None = None,
        namespace: str = "memory",
    ) -> None:
        self._embedder = embedder or hashed_bow_embedder
        self._store = store or InMemoryKnowledgeStore()
        self._namespace = namespace

    async def add(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Index ``text``; returns the entry id."""
        vector = await self._embedder(text)
        return await self._store.add(self._namespace, text, vector, metadata)

    async def search(self, query: str, top_k: int = 5, min_score: float = 0.0) -> list[VectorHit]:
        """Rank indexed entries by similarity to ``query``."""
        query_vector = await self._embedder(query)
        return await self._store.search(self._namespace, query_vector, top_k=top_k, min_score=min_score)

    async def count(self) -> int:
        return await self._store.count(self._namespace)

    async def clear(self) -> None:
        await self._store.clear(self._namespace)
