"""Task Queue — FIFO hand-off to the Worker Queue (Bab 23 prinsip 2).

For work that must not block an HTTP request (large document generation, GIS
processing, long PDF extraction). Producers ``enqueue`` a
:class:`~messaging.schemas.QueuedTask`; a worker loop ``dequeue``\\ s and executes.

Note: the legacy RQ queues (``worker/``) keep serving the existing pipeline
routes; this queue is the v4-native path used by the orchestrator/agents.
"""
from __future__ import annotations

from core.utils.logger import get_logger

from .broker import BaseBroker, get_broker
from .schemas import QueuedTask

logger = get_logger(__name__)


class TaskQueue:
    """Named FIFO queue of :class:`QueuedTask` over the configured broker."""

    def __init__(self, name: str, broker: BaseBroker | None = None) -> None:
        self.name = name
        self._broker = broker or get_broker()
        self._queue_key = f"queue.{name}"

    async def enqueue(self, task: QueuedTask) -> None:
        await self._broker.push(self._queue_key, task.model_dump_json())
        logger.info("task_queue.enqueue", queue=self.name, kind=task.kind, task_id=task.task_id)

    async def dequeue(self, timeout: float = 0.0) -> QueuedTask | None:
        """Pop the next task, waiting up to ``timeout`` seconds (0 = no wait)."""
        raw = await self._broker.pop(self._queue_key, timeout=timeout)
        return QueuedTask.model_validate_json(raw) if raw else None

    async def size(self) -> int:
        return await self._broker.queue_length(self._queue_key)
