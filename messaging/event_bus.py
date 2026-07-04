"""Event Bus — publish/subscribe domain events (Bab 23, Bab 4.5).

Every significant domain event (agent lifecycle Bab 48, workflow lifecycle
Bab 49, consensus decisions, …) **must** be published here (Bab 23 prinsip 1)
so observability (Tahap 6) and future modules can react without coupling.

Publishing is deliberately *best-effort*: a broken broker must never fail the
workflow that emits the event (Bab 10 — errors are handled, not propagated
from telemetry paths).
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from core.utils.logger import get_logger

from .broker import BaseBroker, get_broker
from .schemas import Event

logger = get_logger(__name__)

EventHandler = Callable[[Event], Awaitable[None]]

_CHANNEL_PREFIX = "evt."


class EventBus:
    """Publish :class:`Event` objects; subscribe by exact type or glob pattern."""

    def __init__(self, broker: BaseBroker | None = None) -> None:
        self._broker = broker or get_broker()

    async def publish(self, event: Event) -> int:
        """Publish ``event`` on channel ``evt.<event_type>`` (best-effort)."""
        try:
            receivers = await self._broker.publish(
                _CHANNEL_PREFIX + event.event_type, event.model_dump_json()
            )
        except Exception as exc:  # telemetry path must never break the caller
            logger.warning("event_bus.publish_failed", event_type=event.event_type, error=str(exc))
            return 0
        logger.info(
            "event_bus.publish",
            event_type=event.event_type,
            source=event.source,
            trace_id=event.trace_id,
        )
        return receivers

    async def emit(
        self,
        event_type: str,
        source: str = "",
        trace_id: str = "",
        payload: dict[str, Any] | None = None,
    ) -> int:
        """Convenience wrapper: build the :class:`Event` and publish it."""
        return await self.publish(
            Event(event_type=event_type, source=source, trace_id=trace_id, payload=payload or {})
        )

    async def subscribe(self, pattern: str, handler: EventHandler) -> None:
        """Subscribe to events whose type matches ``pattern`` (e.g. ``agent.*``)."""

        async def _on_raw(raw: str) -> None:
            await handler(Event.model_validate_json(raw))

        await self._broker.subscribe(_CHANNEL_PREFIX + pattern, _on_raw)
