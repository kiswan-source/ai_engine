"""Memory Manager — central facade over the six memory tiers (Bab 22).

Agents and the orchestrator depend on this one object instead of individual
tiers, so backend choices stay in one place:

* ``MEMORY_BACKEND``            → volatile tiers (working/summary/reflection):
  ``memory`` (in-process, default) or ``redis``.
* ``MEMORY_PERSISTENT_BACKEND`` → durable tiers (conversation/long-term):
  ``memory`` (default) or ``postgres``.
* ``VECTOR_BACKEND``            → vector tier: ``memory`` (default) or
  ``pgvector``; ``RAG_EMBEDDING_PROVIDER`` picks the real embedder (Tahap 5,
  see ``rag/``), falling back to the offline hashed placeholder automatically.

Defaults are service-free so dev/CI runs without Redis/Postgres (Bab 12);
production opts in via ``.env``.
"""
from __future__ import annotations

from core.utils.logger import get_logger

from .conversation_memory import (
    ConversationMemory,
    InMemoryConversationStore,
    PostgresConversationStore,
)
from .long_term_memory import InMemoryLongTermStore, LongTermMemory, PostgresLongTermStore
from .reflection_memory import ReflectionMemory
from .stores import InMemoryHashStore, InMemoryListStore, RedisHashStore, RedisListStore
from .summary_memory import Summarizer, SummaryMemory
from .vector_memory import Embedder, VectorMemory
from .working_memory import WorkingMemory

logger = get_logger(__name__)


class MemoryManager:
    """Bundle of all six memory tiers (composition, not logic)."""

    def __init__(
        self,
        working: WorkingMemory,
        conversation: ConversationMemory,
        summary: SummaryMemory,
        long_term: LongTermMemory,
        vector: VectorMemory,
        reflection: ReflectionMemory,
    ) -> None:
        self.working = working
        self.conversation = conversation
        self.summary = summary
        self.long_term = long_term
        self.vector = vector
        self.reflection = reflection


def build_memory_manager(
    volatile_backend: str | None = None,
    persistent_backend: str | None = None,
    vector_backend: str | None = None,
    summarizer: Summarizer | None = None,
    embedder: Embedder | None = None,
) -> MemoryManager:
    """Assemble a :class:`MemoryManager` from settings (overridable per arg)."""
    from api.config import settings
    from rag.embeddings import default_embedder
    from rag.knowledge_store import build_knowledge_store

    volatile = (volatile_backend or settings.MEMORY_BACKEND).lower()
    persistent = (persistent_backend or settings.MEMORY_PERSISTENT_BACKEND).lower()

    if volatile == "redis":
        working_store = RedisHashStore("working")
        summary_store = RedisHashStore("summary")
        reflection_store = RedisListStore("reflection")
    else:
        working_store = InMemoryHashStore()
        summary_store = InMemoryHashStore()
        reflection_store = InMemoryListStore()

    if persistent == "postgres":
        conversation_store = PostgresConversationStore()
        long_term_store = PostgresLongTermStore()
    else:
        conversation_store = InMemoryConversationStore()
        long_term_store = InMemoryLongTermStore()

    logger.info("memory_manager.init", volatile=volatile, persistent=persistent)
    return MemoryManager(
        working=WorkingMemory(working_store, ttl=settings.WORKING_MEMORY_TTL),
        conversation=ConversationMemory(conversation_store),
        summary=SummaryMemory(summary_store, summarizer=summarizer),
        long_term=LongTermMemory(long_term_store),
        vector=VectorMemory(
            embedder=embedder or default_embedder(),
            store=build_knowledge_store(vector_backend),
            namespace="memory",
        ),
        reflection=ReflectionMemory(reflection_store),
    )


_shared_manager: MemoryManager | None = None


def get_shared_memory_manager() -> MemoryManager:
    """Process-wide singleton (Fase 3, DCF v5 mandate "Memory Intelligence
    Evolution").

    Callers that need to actually see each other's writes — ``core/chat/engine.py``
    (writes working/conversation/summary per turn) and ``api/routes/memory.py``
    (reads them for the Memory UI page) — must share this instance rather than
    each calling :func:`build_memory_manager` independently. For the in-memory
    (dev/CI) backends the store itself *is* the state, so two separately
    constructed managers would be disconnected islands that never see each
    other's writes; Postgres/Redis-backed deployments don't strictly need this
    (the data is genuinely shared external storage regardless of instance
    count) but there's no reason for the two code paths to diverge over it.

    Not used by ``agent/tools/memory_tools.py``'s ``remember_fact``/
    ``recall_facts`` for the Postgres-backend case specifically — see that
    module's docstring for why (the same asyncpg-event-loop-affinity
    constraint ``agent/tools/workspace_reader.py`` already documents).
    """
    global _shared_manager
    if _shared_manager is None:
        _shared_manager = build_memory_manager()
    return _shared_manager
