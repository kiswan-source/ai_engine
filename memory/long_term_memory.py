"""Long-Term Memory — durable knowledge/preferences across sessions (Bab 22).

Facts are namespaced (``user:kiswan``, ``project:ai_engine``, …) and keyed, so
agents can recall "what do we know about X" without replaying conversations.
Backed by PostgreSQL (``memory_entries``) in production; an in-memory store
serves dev/CI (Bab 12).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.utils.logger import get_logger

logger = get_logger(__name__)


class LongTermStore(ABC):
    @abstractmethod
    async def put(self, namespace: str, key: str, value: Any) -> None: ...

    @abstractmethod
    async def get(self, namespace: str, key: str) -> Any | None: ...

    @abstractmethod
    async def get_namespace(self, namespace: str) -> dict[str, Any]: ...

    @abstractmethod
    async def delete(self, namespace: str, key: str) -> None: ...


class InMemoryLongTermStore(LongTermStore):
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def put(self, namespace: str, key: str, value: Any) -> None:
        self._data.setdefault(namespace, {})[key] = value

    async def get(self, namespace: str, key: str) -> Any | None:
        return self._data.get(namespace, {}).get(key)

    async def get_namespace(self, namespace: str) -> dict[str, Any]:
        return dict(self._data.get(namespace, {}))

    async def delete(self, namespace: str, key: str) -> None:
        self._data.get(namespace, {}).pop(key, None)


class PostgresLongTermStore(LongTermStore):
    """PostgreSQL backend over the ``memory_entries`` table (upsert by namespace+key)."""

    def __init__(self, session_factory=None) -> None:
        if session_factory is None:
            from db.connection import AsyncSessionFactory

            session_factory = AsyncSessionFactory
        self._sessions = session_factory

    async def put(self, namespace: str, key: str, value: Any) -> None:
        from sqlalchemy import select

        from db.models import MemoryEntry

        async with self._sessions() as db:
            stmt = select(MemoryEntry).where(
                MemoryEntry.namespace == namespace, MemoryEntry.key == key
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                db.add(MemoryEntry(namespace=namespace, key=key, value={"v": value}))
            else:
                row.value = {"v": value}
            await db.commit()

    async def get(self, namespace: str, key: str) -> Any | None:
        from sqlalchemy import select

        from db.models import MemoryEntry

        async with self._sessions() as db:
            stmt = select(MemoryEntry).where(
                MemoryEntry.namespace == namespace, MemoryEntry.key == key
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
        return None if row is None or row.value is None else row.value.get("v")

    async def get_namespace(self, namespace: str) -> dict[str, Any]:
        from sqlalchemy import select

        from db.models import MemoryEntry

        async with self._sessions() as db:
            stmt = select(MemoryEntry).where(MemoryEntry.namespace == namespace)
            rows = (await db.execute(stmt)).scalars().all()
        return {r.key: (r.value or {}).get("v") for r in rows}

    async def delete(self, namespace: str, key: str) -> None:
        from sqlalchemy import delete as sa_delete

        from db.models import MemoryEntry

        async with self._sessions() as db:
            await db.execute(
                sa_delete(MemoryEntry).where(
                    MemoryEntry.namespace == namespace, MemoryEntry.key == key
                )
            )
            await db.commit()


class LongTermMemory:
    """Namespaced fact store over a pluggable backend."""

    def __init__(self, store: LongTermStore) -> None:
        self._store = store

    async def remember(self, namespace: str, key: str, value: Any) -> None:
        await self._store.put(namespace, key, value)
        logger.info("long_term_memory.remember", namespace=namespace, key=key)

    async def recall(self, namespace: str, key: str) -> Any | None:
        return await self._store.get(namespace, key)

    async def recall_all(self, namespace: str) -> dict[str, Any]:
        return await self._store.get_namespace(namespace)

    async def forget(self, namespace: str, key: str) -> None:
        await self._store.delete(namespace, key)
        logger.info("long_term_memory.forget", namespace=namespace, key=key)
