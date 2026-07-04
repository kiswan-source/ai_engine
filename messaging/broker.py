"""Physical broker adapters (MASTER_INSTRUCTION.md Bab 23).

``BaseBroker`` is the only seam between the messaging layer and the transport.
Swapping brokers (Bab 23 prinsip 3) means adding a subclass here — the
contracts in :mod:`messaging.schemas` / :mod:`messaging.events` stay untouched.

Two implementations:

* :class:`InMemoryBroker` — in-process, deterministic; default for dev/CI
  where no Redis is available (Bab 12 — tests must not need live services).
* :class:`RedisBroker` — Redis Pub/Sub for channels + Redis lists for queues;
  the production transport, selected via ``MESSAGE_BROKER=redis``.

Channel subscriptions accept glob patterns (``agent.*``), mapped to
``fnmatch`` in-memory and to ``PSUBSCRIBE`` on Redis.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from fnmatch import fnmatch
from typing import Awaitable, Callable

from core.utils.logger import get_logger

logger = get_logger(__name__)

Handler = Callable[[str], Awaitable[None]]

_PREFIX = "ai_engine:"  # namespaces all channels/queues on shared brokers


def _is_pattern(channel: str) -> bool:
    return any(ch in channel for ch in "*?[")


class BaseBroker(ABC):
    """Transport-agnostic pub/sub + queue interface."""

    @abstractmethod
    async def publish(self, channel: str, data: str) -> int:
        """Publish ``data`` on ``channel``; returns receivers reached (best effort)."""

    @abstractmethod
    async def subscribe(self, pattern: str, handler: Handler) -> None:
        """Register ``handler`` for channels matching ``pattern`` (glob allowed)."""

    @abstractmethod
    async def push(self, queue: str, data: str) -> None:
        """Append ``data`` to the tail of ``queue`` (FIFO)."""

    @abstractmethod
    async def pop(self, queue: str, timeout: float = 0.0) -> str | None:
        """Pop from the head of ``queue``; block up to ``timeout`` s (0 = no wait)."""

    @abstractmethod
    async def queue_length(self, queue: str) -> int:
        """Current number of items waiting in ``queue``."""

    async def close(self) -> None:  # noqa: B027 — optional hook
        """Release transport resources (subclass hook)."""


class InMemoryBroker(BaseBroker):
    """Single-process broker: handlers are awaited inline on publish.

    Deterministic (no background readers), which is exactly what unit tests
    want; obviously not shared across processes — use Redis for that.
    """

    def __init__(self) -> None:
        self._subs: list[tuple[str, Handler]] = []
        self._queues: dict[str, asyncio.Queue[str]] = {}

    async def publish(self, channel: str, data: str) -> int:
        delivered = 0
        for pattern, handler in list(self._subs):
            if fnmatch(channel, pattern):
                try:
                    await handler(data)
                    delivered += 1
                except Exception as exc:  # a bad subscriber must not break publishers
                    logger.warning("broker.handler_error", channel=channel, error=str(exc))
        return delivered

    async def subscribe(self, pattern: str, handler: Handler) -> None:
        self._subs.append((pattern, handler))

    def _queue(self, queue: str) -> asyncio.Queue[str]:
        return self._queues.setdefault(queue, asyncio.Queue())

    async def push(self, queue: str, data: str) -> None:
        await self._queue(queue).put(data)

    async def pop(self, queue: str, timeout: float = 0.0) -> str | None:
        q = self._queue(queue)
        try:
            if timeout <= 0:
                return q.get_nowait()
            return await asyncio.wait_for(q.get(), timeout=timeout)
        except (asyncio.QueueEmpty, asyncio.TimeoutError):
            return None

    async def queue_length(self, queue: str) -> int:
        return self._queue(queue).qsize()


class RedisBroker(BaseBroker):
    """Redis Pub/Sub (channels) + Redis lists (queues).

    Args:
        client: Optional pre-built ``redis.asyncio.Redis`` (injected in tests).
    """

    def __init__(self, client=None) -> None:
        if client is None:
            import redis.asyncio as aioredis

            from api.config import settings

            client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._redis = client
        self._readers: list[tuple[object, asyncio.Task]] = []

    async def publish(self, channel: str, data: str) -> int:
        return await self._redis.publish(_PREFIX + channel, data)

    async def subscribe(self, pattern: str, handler: Handler) -> None:
        pubsub = self._redis.pubsub()
        name = _PREFIX + pattern
        if _is_pattern(pattern):
            await pubsub.psubscribe(name)
        else:
            await pubsub.subscribe(name)
        task = asyncio.create_task(self._reader(pubsub, handler))
        self._readers.append((pubsub, task))

    async def _reader(self, pubsub, handler: Handler) -> None:
        try:
            async for message in pubsub.listen():
                if message.get("type") not in ("message", "pmessage"):
                    continue
                try:
                    await handler(message["data"])
                except Exception as exc:
                    logger.warning("broker.handler_error", error=str(exc))
        except asyncio.CancelledError:  # normal shutdown path via close()
            pass

    async def push(self, queue: str, data: str) -> None:
        await self._redis.rpush(_PREFIX + queue, data)

    async def pop(self, queue: str, timeout: float = 0.0) -> str | None:
        name = _PREFIX + queue
        if timeout <= 0:
            return await self._redis.lpop(name)
        item = await self._redis.blpop(name, timeout=timeout)
        return item[1] if item else None

    async def queue_length(self, queue: str) -> int:
        return await self._redis.llen(_PREFIX + queue)

    async def close(self) -> None:
        for pubsub, task in self._readers:
            task.cancel()
            try:
                await pubsub.aclose()
            except Exception:  # closing best-effort; connection may already be gone
                pass
        self._readers.clear()
        await self._redis.aclose()


_broker: BaseBroker | None = None


def get_broker() -> BaseBroker:
    """Process-wide broker singleton, selected by ``settings.MESSAGE_BROKER``."""
    global _broker
    if _broker is None:
        from api.config import settings

        backend = settings.MESSAGE_BROKER.lower()
        _broker = RedisBroker() if backend == "redis" else InMemoryBroker()
        logger.info("broker.init", backend=backend)
    return _broker


def reset_broker() -> None:
    """Drop the singleton (tests / reconfiguration)."""
    global _broker
    _broker = None
