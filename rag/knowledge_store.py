"""Knowledge Store (MASTER_INSTRUCTION.md Bab 29 step 3) — vector + metadata storage.

Shared low-level primitive behind both the RAG document corpus and
``memory/vector_memory.py``'s Vector Memory tier (Bab 22 calls that tier
"disimpan di vector store" — this is that store). Two backends behind one
contract:

* :class:`InMemoryKnowledgeStore` — cosine similarity over a Python list;
  dependency-free and deterministic, the Bab 12 default for dev/CI.
* :class:`PgVectorKnowledgeStore` — real pgvector-backed storage in the
  shared ``vector_embeddings`` table (Tahap 5; needs ``VECTOR_BACKEND=pgvector``
  and the Postgres ``vector`` extension).

Entries are namespaced (e.g. ``"memory:writer"`` vs ``"rag:documents"``) so
unrelated collections never leak into each other's search results, without
needing a separate table per collection.
"""
from __future__ import annotations

import math
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class KnowledgeHit:
    """One semantic search result."""

    entry_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeStore(ABC):
    """Namespace-scoped vector index: add embedded text, search by embedded query."""

    @abstractmethod
    async def add(
        self, namespace: str, text: str, embedding: list[float], metadata: dict[str, Any] | None = None
    ) -> str:
        """Index ``text``/``embedding`` under ``namespace``; returns the entry id."""

    @abstractmethod
    async def search(
        self, namespace: str, query_embedding: list[float], top_k: int = 5, min_score: float = 0.0
    ) -> list[KnowledgeHit]:
        """Rank ``namespace``'s entries by similarity to ``query_embedding``."""

    @abstractmethod
    async def count(self, namespace: str) -> int:
        """Number of entries indexed under ``namespace``."""

    @abstractmethod
    async def clear(self, namespace: str) -> None:
        """Drop every entry under ``namespace``."""


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class InMemoryKnowledgeStore(KnowledgeStore):
    """Process-local store — dev/CI default (Bab 12), no services required."""

    def __init__(self) -> None:
        self._entries: dict[str, list[tuple[str, str, dict[str, Any], list[float]]]] = {}

    async def add(
        self, namespace: str, text: str, embedding: list[float], metadata: dict[str, Any] | None = None
    ) -> str:
        entry_id = uuid.uuid4().hex
        self._entries.setdefault(namespace, []).append((entry_id, text, metadata or {}, embedding))
        return entry_id

    async def search(
        self, namespace: str, query_embedding: list[float], top_k: int = 5, min_score: float = 0.0
    ) -> list[KnowledgeHit]:
        rows = self._entries.get(namespace, [])
        if not rows:
            return []
        hits = [
            KnowledgeHit(entry_id=eid, text=text, score=_cosine(query_embedding, vec), metadata=meta)
            for eid, text, meta, vec in rows
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits[:top_k] if h.score >= min_score]

    async def count(self, namespace: str) -> int:
        return len(self._entries.get(namespace, []))

    async def clear(self, namespace: str) -> None:
        self._entries.pop(namespace, None)


class PgVectorKnowledgeStore(KnowledgeStore):
    """PostgreSQL + pgvector backend over the shared ``vector_embeddings`` table.

    Args:
        session_factory: Optional pre-built async session factory (injected in
            tests); defaults to ``db.connection.AsyncSessionFactory``.
    """

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from db.connection import AsyncSessionFactory

            session_factory = AsyncSessionFactory
        self._sessions = session_factory

    async def add(
        self, namespace: str, text: str, embedding: list[float], metadata: dict[str, Any] | None = None
    ) -> str:
        from db.models import VectorEmbedding

        row = VectorEmbedding(namespace=namespace, text=text, meta=metadata or {}, embedding=embedding)
        async with self._sessions() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row.id

    async def search(
        self, namespace: str, query_embedding: list[float], top_k: int = 5, min_score: float = 0.0
    ) -> list[KnowledgeHit]:
        from sqlalchemy import select

        from db.models import VectorEmbedding

        distance = VectorEmbedding.embedding.cosine_distance(query_embedding)
        stmt = (
            select(VectorEmbedding, distance.label("distance"))
            .where(VectorEmbedding.namespace == namespace)
            .order_by(distance)
            .limit(top_k)
        )
        async with self._sessions() as db:
            rows = (await db.execute(stmt)).all()

        hits = []
        for row, distance_value in rows:
            score = 1.0 - float(distance_value)  # pgvector cosine_distance = 1 - cosine_similarity
            if score >= min_score:
                hits.append(KnowledgeHit(entry_id=row.id, text=row.text, score=score, metadata=row.meta or {}))
        return hits

    async def count(self, namespace: str) -> int:
        from sqlalchemy import func, select

        from db.models import VectorEmbedding

        stmt = select(func.count()).select_from(VectorEmbedding).where(VectorEmbedding.namespace == namespace)
        async with self._sessions() as db:
            return (await db.execute(stmt)).scalar_one()

    async def clear(self, namespace: str) -> None:
        from sqlalchemy import delete

        from db.models import VectorEmbedding

        async with self._sessions() as db:
            await db.execute(delete(VectorEmbedding).where(VectorEmbedding.namespace == namespace))
            await db.commit()


def build_knowledge_store(backend: str | None = None) -> KnowledgeStore:
    """Construct the configured :class:`KnowledgeStore` (``memory`` default, or ``pgvector``)."""
    from api.config import settings

    chosen = (backend or settings.VECTOR_BACKEND).lower()
    if chosen == "pgvector":
        logger.info("knowledge_store.init", backend="pgvector")
        return PgVectorKnowledgeStore()
    logger.info("knowledge_store.init", backend="memory")
    return InMemoryKnowledgeStore()
