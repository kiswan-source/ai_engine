"""Backend store abstractions for the volatile memory tiers (Bab 22).

The memory tiers talk to two tiny storage interfaces — a hash (field→value per
named scope) and an append-only list — so the same tier code runs against an
in-process dict (dev/CI, no services required, Bab 12) or Redis (production,
``MEMORY_BACKEND=redis``). Persistent tiers (conversation, long-term) have
their own PostgreSQL stores in their modules; this file is Redis/in-memory only.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from core.utils.logger import get_logger

logger = get_logger(__name__)


class HashStore(ABC):
    """field→value mapping under a named scope, with optional scope TTL."""

    @abstractmethod
    async def set_field(self, name: str, field: str, value: str, ttl: int | None = None) -> None:
        """Set ``field`` under ``name``; ``ttl`` (s) refreshes the whole scope's expiry."""

    @abstractmethod
    async def get_field(self, name: str, field: str) -> str | None: ...

    @abstractmethod
    async def get_all(self, name: str) -> dict[str, str]: ...

    @abstractmethod
    async def delete_field(self, name: str, field: str) -> None: ...

    @abstractmethod
    async def delete(self, name: str) -> None:
        """Drop the whole scope."""


class ListStore(ABC):
    """Append-only list per named scope (newest last)."""

    @abstractmethod
    async def append(self, name: str, value: str, max_len: int | None = None) -> None:
        """Append ``value``; if ``max_len`` is set, keep only the newest entries."""

    @abstractmethod
    async def last(self, name: str, limit: int) -> list[str]:
        """Return up to ``limit`` newest entries, oldest→newest order."""

    @abstractmethod
    async def clear(self, name: str) -> None: ...


class InMemoryHashStore(HashStore):
    """Process-local hash store with lazy TTL expiry."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, str]] = {}
        self._expiry: dict[str, float] = {}

    def _alive(self, name: str) -> dict[str, str]:
        deadline = self._expiry.get(name)
        if deadline is not None and time.monotonic() > deadline:
            self._data.pop(name, None)
            self._expiry.pop(name, None)
        return self._data.setdefault(name, {})

    async def set_field(self, name: str, field: str, value: str, ttl: int | None = None) -> None:
        self._alive(name)[field] = value
        if ttl is not None:
            self._expiry[name] = time.monotonic() + ttl

    async def get_field(self, name: str, field: str) -> str | None:
        return self._alive(name).get(field)

    async def get_all(self, name: str) -> dict[str, str]:
        return dict(self._alive(name))

    async def delete_field(self, name: str, field: str) -> None:
        self._alive(name).pop(field, None)

    async def delete(self, name: str) -> None:
        self._data.pop(name, None)
        self._expiry.pop(name, None)


class InMemoryListStore(ListStore):
    def __init__(self) -> None:
        self._data: dict[str, list[str]] = {}

    async def append(self, name: str, value: str, max_len: int | None = None) -> None:
        items = self._data.setdefault(name, [])
        items.append(value)
        if max_len is not None and len(items) > max_len:
            del items[: len(items) - max_len]

    async def last(self, name: str, limit: int) -> list[str]:
        return self._data.get(name, [])[-limit:]

    async def clear(self, name: str) -> None:
        self._data.pop(name, None)


def _redis_client(client=None):
    """Shared Redis client (reuses the AI-cache connection pool)."""
    if client is not None:
        return client
    import redis.asyncio as aioredis

    from core.ai.cache import get_pool

    return aioredis.Redis(connection_pool=get_pool())


class RedisHashStore(HashStore):
    """Redis HSET-backed hash store; TTL applies to the whole scope key."""

    def __init__(self, prefix: str, client=None) -> None:
        self._prefix = f"mem:{prefix}:"
        self._redis = _redis_client(client)

    def _key(self, name: str) -> str:
        return self._prefix + name

    async def set_field(self, name: str, field: str, value: str, ttl: int | None = None) -> None:
        key = self._key(name)
        await self._redis.hset(key, field, value)
        if ttl is not None:
            await self._redis.expire(key, ttl)

    async def get_field(self, name: str, field: str) -> str | None:
        return await self._redis.hget(self._key(name), field)

    async def get_all(self, name: str) -> dict[str, str]:
        return await self._redis.hgetall(self._key(name)) or {}

    async def delete_field(self, name: str, field: str) -> None:
        await self._redis.hdel(self._key(name), field)

    async def delete(self, name: str) -> None:
        await self._redis.delete(self._key(name))


class RedisListStore(ListStore):
    """Redis RPUSH/LRANGE-backed list store."""

    def __init__(self, prefix: str, client=None) -> None:
        self._prefix = f"mem:{prefix}:"
        self._redis = _redis_client(client)

    def _key(self, name: str) -> str:
        return self._prefix + name

    async def append(self, name: str, value: str, max_len: int | None = None) -> None:
        key = self._key(name)
        await self._redis.rpush(key, value)
        if max_len is not None:
            await self._redis.ltrim(key, -max_len, -1)

    async def last(self, name: str, limit: int) -> list[str]:
        return await self._redis.lrange(self._key(name), -limit, -1) or []

    async def clear(self, name: str) -> None:
        await self._redis.delete(self._key(name))
