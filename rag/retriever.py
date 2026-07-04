"""Retriever (MASTER_INSTRUCTION.md Bab 29 step 4) — initial semantic search.

Embeds a query with the same :class:`~rag.embeddings.Embedder` used at ingest
time and searches one namespace of a :class:`~rag.knowledge_store.KnowledgeStore`.
Downstream steps (hybrid_search, reranker, context_builder) refine what this
returns; the retriever itself only does the vector lookup (Bab 29 diagram).
"""
from __future__ import annotations

from core.utils.logger import get_logger

from .chunker import chunk_text
from .embeddings import Embedder, default_embedder
from .knowledge_store import KnowledgeHit, KnowledgeStore, build_knowledge_store

logger = get_logger(__name__)


class Retriever:
    """Indexes and searches one namespace of a knowledge store."""

    def __init__(
        self,
        namespace: str,
        store: KnowledgeStore | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self._namespace = namespace
        self._store = store or build_knowledge_store()
        self._embedder = embedder or default_embedder()

    async def index(self, text: str, metadata: dict | None = None) -> str:
        """Embed and store one (already-chunked) piece of text. Prefer
        :meth:`index_document` for whole documents so chunking stays
        consistent (Bab 29 rule 1)."""
        vector = await self._embedder(text)
        entry_id = await self._store.add(self._namespace, text, vector, metadata)
        logger.info("retriever.index", namespace=self._namespace, entry_id=entry_id)
        return entry_id

    async def index_document(
        self,
        text: str,
        metadata: dict | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> list[str]:
        """Chunk a whole document (Bab 29 step 1) and index every piece.

        Each chunk's metadata carries the caller's ``metadata`` plus
        ``chunk_index``/``start_char``/``end_char`` for citation (Bab 29 rule 3).
        """
        entry_ids = []
        for chunk in chunk_text(text, chunk_size=chunk_size, overlap=overlap):
            chunk_metadata = {
                **(metadata or {}),
                "chunk_index": chunk.index,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
            }
            entry_ids.append(await self.index(chunk.text, chunk_metadata))
        logger.info("retriever.index_document", namespace=self._namespace, chunks=len(entry_ids))
        return entry_ids

    async def retrieve(
        self, query: str, top_k: int | None = None, min_score: float = 0.0
    ) -> list[KnowledgeHit]:
        """Semantic search for ``query`` within this retriever's namespace."""
        from api.config import settings

        top_k = settings.RAG_TOP_K if top_k is None else top_k
        query_vector = await self._embedder(query)
        hits = await self._store.search(self._namespace, query_vector, top_k=top_k, min_score=min_score)
        logger.info("retriever.retrieve", namespace=self._namespace, query_len=len(query), hits=len(hits))
        return hits
