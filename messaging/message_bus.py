"""Message Bus — point-to-point & broadcast agent messaging (Bab 23, Bab 17.3).

Agents never call each other directly across processes (Bab 17.3); they send an
:class:`~messaging.schemas.AgentMessage` here. Each agent listens on its own
channel (``msg.agent.<name>``) plus the shared broadcast channel (``msg.broadcast``).
"""
from __future__ import annotations

from typing import Awaitable, Callable

from core.utils.logger import get_logger

from .broker import BaseBroker, get_broker
from .schemas import AgentMessage

logger = get_logger(__name__)

BROADCAST = "*"

MessageHandler = Callable[[AgentMessage], Awaitable[None]]


def _channel(agent_name: str) -> str:
    return "msg.broadcast" if agent_name == BROADCAST else f"msg.agent.{agent_name}"


class MessageBus:
    """Send/receive :class:`AgentMessage` over the configured broker."""

    def __init__(self, broker: BaseBroker | None = None) -> None:
        self._broker = broker or get_broker()

    async def send(self, message: AgentMessage) -> int:
        """Deliver ``message`` to its target (or everyone if target is ``"*"``)."""
        receivers = await self._broker.publish(
            _channel(message.target_agent), message.model_dump_json()
        )
        logger.info(
            "message_bus.send",
            sender=message.sender_agent,
            target=message.target_agent,
            task_id=message.task_id,
            trace_id=message.trace_id,
            receivers=receivers,
        )
        return receivers

    async def broadcast(self, message: AgentMessage) -> int:
        """Send ``message`` to all subscribers regardless of its target field."""
        return await self._broker.publish(_channel(BROADCAST), message.model_dump_json())

    async def subscribe(self, agent_name: str, handler: MessageHandler) -> None:
        """Subscribe ``handler`` to ``agent_name``'s channel + broadcasts."""

        async def _on_raw(raw: str) -> None:
            await handler(AgentMessage.model_validate_json(raw))

        await self._broker.subscribe(_channel(agent_name), _on_raw)
        await self._broker.subscribe(_channel(BROADCAST), _on_raw)
