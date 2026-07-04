"""Working Memory — active context of one running session/task (Bab 22).

Volatile and short-lived by design: scoped to a ``trace_id``/session id, stored
in Redis (production) or in-process (dev/CI), and expires via TTL
(``WORKING_MEMORY_TTL``). Optimised for latency, not durability — anything an
agent must keep across sessions belongs in Long-Term Memory instead.
"""
from __future__ import annotations

import json
from typing import Any

from core.utils.logger import get_logger

from .stores import HashStore

logger = get_logger(__name__)


class WorkingMemory:
    """Per-scope key→value context with TTL.

    Args:
        store: Hash backend (in-memory or Redis).
        ttl: Scope expiry in seconds; refreshed on every write.
    """

    def __init__(self, store: HashStore, ttl: int = 3600) -> None:
        self._store = store
        self._ttl = ttl

    async def set(self, scope: str, key: str, value: Any) -> None:
        """Store a JSON-serialisable ``value`` under ``scope``/``key``."""
        await self._store.set_field(scope, key, json.dumps(value, default=str), ttl=self._ttl)

    async def get(self, scope: str, key: str, default: Any = None) -> Any:
        raw = await self._store.get_field(scope, key)
        return default if raw is None else json.loads(raw)

    async def get_all(self, scope: str) -> dict[str, Any]:
        """Entire active context for ``scope`` (e.g. to build an agent prompt)."""
        raw = await self._store.get_all(scope)
        return {k: json.loads(v) for k, v in raw.items()}

    async def forget(self, scope: str, key: str) -> None:
        await self._store.delete_field(scope, key)

    async def clear(self, scope: str) -> None:
        """Drop the whole scope (task finished / session closed)."""
        await self._store.delete(scope)
        logger.info("working_memory.clear", scope=scope)
