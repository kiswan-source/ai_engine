"""Vector Memory — embedding store for semantic recall (Bab 22, basis RAG Bab 29).

Tahap 3 ships the *interface* plus a dependency-free implementation: an
injected async ``embedder`` produces vectors, cosine similarity ranks them.
The default embedder is a deterministic hashed bag-of-words — good enough for
keyword-ish recall offline, and explicitly a placeholder until Tahap 5 wires
real embedding models (Ollama/OpenAI) and a proper vector store behind this
same interface (``add``/``search`` must not change).
"""
from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from core.utils.logger import get_logger

logger = get_logger(__name__)

Embedder = Callable[[str], Awaitable[list[float]]]

_DIM = 512
_TOKEN_RE = re.compile(r"[a-z0-9]+")


async def hashed_bow_embedder(text: str) -> list[float]:
    """Placeholder embedding: tokens hashed into a fixed-size frequency vector."""
    vec = [0.0] * _DIM
    for token in _TOKEN_RE.findall(text.lower()):
        digest = hashlib.md5(token.encode()).digest()
        vec[int.from_bytes(digest[:4], "little") % _DIM] += 1.0
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@dataclass(frozen=True)
class VectorHit:
    """One semantic search result."""

    text: str
    score: float
    entry_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorMemory:
    """In-process vector index with pluggable embedder (swap-in point for Tahap 5)."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or hashed_bow_embedder
        self._entries: list[tuple[str, str, dict[str, Any], list[float]]] = []

    async def add(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Index ``text``; returns the entry id."""
        entry_id = uuid.uuid4().hex
        vector = await self._embedder(text)
        self._entries.append((entry_id, text, metadata or {}, vector))
        return entry_id

    async def search(self, query: str, top_k: int = 5, min_score: float = 0.0) -> list[VectorHit]:
        """Rank indexed entries by cosine similarity to ``query``."""
        if not self._entries:
            return []
        qvec = await self._embedder(query)
        hits = [
            VectorHit(text=text, score=_cosine(qvec, vec), entry_id=eid, metadata=meta)
            for eid, text, meta, vec in self._entries
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return [h for h in hits[:top_k] if h.score >= min_score]

    def count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
