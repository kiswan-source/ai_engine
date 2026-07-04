"""RAG — Retrieval-Augmented Generation (MASTER_INSTRUCTION.md Bab 29, Tahap 5).

Pipeline: chunker -> embeddings -> knowledge_store -> retriever ->
hybrid_search -> reranker -> context_builder. RAG is an additive layer that
enriches prompts with retrieved context; it does not replace `core/document/`
or `core/gis/` (Bab 29 rule 4).
"""
from .chunker import Chunk, chunk_text
from .context_builder import build_context
from .embeddings import Embedder, default_embedder, hashed_bow_embedder
from .hybrid_search import hybrid_search
from .knowledge_store import (
    InMemoryKnowledgeStore,
    KnowledgeHit,
    KnowledgeStore,
    PgVectorKnowledgeStore,
    build_knowledge_store,
)
from .reranker import rerank
from .retriever import Retriever

__all__ = [
    "Chunk",
    "Embedder",
    "InMemoryKnowledgeStore",
    "KnowledgeHit",
    "KnowledgeStore",
    "PgVectorKnowledgeStore",
    "Retriever",
    "build_context",
    "build_knowledge_store",
    "chunk_text",
    "default_embedder",
    "hashed_bow_embedder",
    "hybrid_search",
    "rerank",
]
