"""Memory Manager — central facade over the six memory tiers (Bab 22).

Agents and the orchestrator depend on this one object instead of individual
tiers, so backend choices stay in one place:

* ``MEMORY_BACKEND``            → volatile tiers (working/summary/reflection):
  ``memory`` (in-process, default) or ``redis``.
* ``MEMORY_PERSISTENT_BACKEND`` → durable tiers (conversation/long-term):
  ``memory`` (default) or ``postgres``.

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
    summarizer: Summarizer | None = None,
    embedder: Embedder | None = None,
) -> MemoryManager:
    """Assemble a :class:`MemoryManager` from settings (overridable per arg)."""
    from api.config import settings

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
        vector=VectorMemory(embedder=embedder),
        reflection=ReflectionMemory(reflection_store),
    )
