"""Reflection Memory — agent self-evaluation records (Bab 22, feeds Bab 25).

Stores what worked and what failed per role, so the Reflection Engine
(Tahap 4) can learn iteratively and the Archived lifecycle state (Bab 48.3
aturan 4) has an audit trail. Entries are append-only per role, capped to the
newest ``max_entries``.
"""
from __future__ import annotations

import json
from typing import Any

from core.utils.logger import get_logger

from .stores import ListStore

logger = get_logger(__name__)


class ReflectionMemory:
    """Append-only journal of agent outcomes over a pluggable list store."""

    def __init__(self, store: ListStore, max_entries: int = 200) -> None:
        self._store = store
        self._max = max_entries

    async def record(
        self,
        role: str,
        task_id: str,
        trace_id: str,
        success: bool,
        score: float = 0.0,
        lesson: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Journal one outcome for ``role`` (called after a task finishes/archives)."""
        entry = {
            "role": role,
            "task_id": task_id,
            "trace_id": trace_id,
            "success": success,
            "score": score,
            "lesson": lesson,
            **(extra or {}),
        }
        await self._store.append(role, json.dumps(entry, default=str), max_len=self._max)
        logger.info("reflection_memory.record", role=role, success=success, trace_id=trace_id)

    async def recent(self, role: str, limit: int = 20) -> list[dict[str, Any]]:
        """Newest ``limit`` entries for ``role``, oldest→newest."""
        return [json.loads(raw) for raw in await self._store.last(role, limit)]

    async def lessons_for(self, role: str, limit: int = 20) -> list[str]:
        """Non-empty lessons for ``role`` — prompt-ready input for Reflection (Bab 25)."""
        return [e["lesson"] for e in await self.recent(role, limit) if e.get("lesson")]

    async def clear(self, role: str) -> None:
        await self._store.clear(role)
