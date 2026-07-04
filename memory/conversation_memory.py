"""Conversation Memory — persistent chat history per session (Bab 22).

Persists user↔assistant exchanges in PostgreSQL (``conversation_messages``)
so a session survives restarts — unlike the in-process ``chat_engine.sessions``
dict of the legacy chat path. An in-memory store backs dev/CI where no
database is available (Bab 12).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.utils.logger import get_logger

logger = get_logger(__name__)


class ConversationStore(ABC):
    """Persistence backend for conversation messages."""

    @abstractmethod
    async def add(
        self,
        session_id: str,
        role: str,
        content: str,
        trace_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    async def history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Newest ``limit`` messages, oldest→newest order."""

    @abstractmethod
    async def clear(self, session_id: str) -> None: ...


class InMemoryConversationStore(ConversationStore):
    def __init__(self) -> None:
        self._sessions: dict[str, list[dict[str, Any]]] = {}

    async def add(self, session_id, role, content, trace_id=None, meta=None) -> None:
        self._sessions.setdefault(session_id, []).append(
            {"role": role, "content": content, "trace_id": trace_id, "meta": meta or {}}
        )

    async def history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return self._sessions.get(session_id, [])[-limit:]

    async def clear(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


class PostgresConversationStore(ConversationStore):
    """PostgreSQL backend over the ``conversation_messages`` table.

    Args:
        session_factory: Optional ``async_sessionmaker`` override (tests inject
            a fake); defaults to the shared pool in :mod:`db.connection`.
    """

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from db.connection import AsyncSessionFactory

            session_factory = AsyncSessionFactory
        self._sessions = session_factory

    async def add(self, session_id, role, content, trace_id=None, meta=None) -> None:
        from db.models import ConversationMessage

        async with self._sessions() as db:
            db.add(
                ConversationMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    trace_id=trace_id,
                    meta=meta,
                )
            )
            await db.commit()

    async def history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        from sqlalchemy import select

        from db.models import ConversationMessage

        async with self._sessions() as db:
            stmt = (
                select(ConversationMessage)
                .where(ConversationMessage.session_id == session_id)
                .order_by(ConversationMessage.created_at.desc())
                .limit(limit)
            )
            rows = (await db.execute(stmt)).scalars().all()
        return [
            {"role": r.role, "content": r.content, "trace_id": r.trace_id, "meta": r.meta or {}}
            for r in reversed(rows)
        ]

    async def clear(self, session_id: str) -> None:
        from sqlalchemy import delete

        from db.models import ConversationMessage

        async with self._sessions() as db:
            await db.execute(
                delete(ConversationMessage).where(ConversationMessage.session_id == session_id)
            )
            await db.commit()


class ConversationMemory:
    """Session-scoped chat history over a pluggable store."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        trace_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        await self._store.add(session_id, role, content, trace_id=trace_id, meta=meta)
        logger.info("conversation_memory.add", session_id=session_id, role=role)

    async def get_history(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return await self._store.history(session_id, limit=limit)

    async def as_chat_messages(self, session_id: str, limit: int = 50) -> list[dict[str, str]]:
        """History as ``[{role, content}]`` ready for a provider chat call."""
        return [
            {"role": m["role"], "content": m["content"]}
            for m in await self._store.history(session_id, limit=limit)
        ]

    async def clear(self, session_id: str) -> None:
        await self._store.clear(session_id)
        logger.info("conversation_memory.clear", session_id=session_id)
