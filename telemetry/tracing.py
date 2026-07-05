"""Execution Tracing (MASTER_INSTRUCTION.md Bab 34) — reconstruct the Execution Timeline.

Subscribes to the Event Bus (``agent.*``, ``workflow.*``, ``consensus.decided``,
``security.*``, ``circuit.*`` — every trace_id-carrying domain event, Bab 23
prinsip 1) and
records each as a :class:`Span` keyed by trace_id, so any multi-agent task
can be reconstructed end-to-end: which agent ran, when, with which provider,
how long, what happened, and any guardrail/audit action taken along the way
(Bab 30, Tahap 7). Zero coupling to Dispatcher/Orchestrator/security — it
only ever reads what they already publish.

Reuses :mod:`memory.stores`' ``ListStore`` (Tahap 3) instead of a new storage
abstraction — a trace's spans are just another append-only list per scope
(the trace_id).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from core.utils.logger import get_logger
from memory.stores import InMemoryListStore, ListStore, RedisListStore
from messaging import EventBus
from messaging.schemas import Event

logger = get_logger(__name__)

_PATTERNS = ("agent.*", "workflow.*", "consensus.decided", "security.*", "circuit.*")


@dataclass(frozen=True)
class Span:
    """One recorded domain event, as a point in a trace_id's timeline."""

    event_type: str
    source: str
    timestamp: str
    payload: dict[str, Any]


def _default_store() -> ListStore:
    from api.config import settings

    if settings.TRACE_BACKEND.lower() == "redis":
        return RedisListStore("trace")
    return InMemoryListStore()


class Tracer:
    """Records every agent/workflow/consensus event into a per-trace_id timeline."""

    def __init__(
        self,
        event_bus: EventBus | None = None,
        store: ListStore | None = None,
        max_spans: int | None = None,
    ) -> None:
        from api.config import settings

        self._events = event_bus or EventBus()
        self._store = store or _default_store()
        self._max_spans = settings.TRACE_MAX_SPANS_PER_TRACE if max_spans is None else max_spans
        self._started = False

    async def start(self) -> None:
        """Subscribe to the Event Bus. Idempotent — safe to call more than once."""
        if self._started:
            return
        for pattern in _PATTERNS:
            await self._events.subscribe(pattern, self._on_event)
        self._started = True

    async def _on_event(self, event: Event) -> None:
        if not event.trace_id:
            return
        record = {
            "event_type": event.event_type,
            "source": event.source,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }
        await self._store.append(event.trace_id, json.dumps(record, default=str), max_len=self._max_spans)

    async def timeline(self, trace_id: str, limit: int | None = None) -> list[Span]:
        """The recorded timeline for ``trace_id``, oldest first."""
        raw = await self._store.last(trace_id, limit or self._max_spans)
        return [Span(**json.loads(r)) for r in raw]

    async def clear(self, trace_id: str) -> None:
        await self._store.clear(trace_id)
