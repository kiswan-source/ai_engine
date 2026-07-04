"""Message & event contracts for the messaging layer (MASTER_INSTRUCTION.md Bab 23).

These Pydantic models are the *stable contract* of the messaging layer: swapping
the physical broker (Bab 23 prinsip 3) must never require touching them. The
``AgentMessage`` shape follows the minimal contract in Bab 17.3 verbatim.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def new_uuid() -> str:
    return uuid.uuid4().hex


def utc_now_iso() -> str:
    """ISO-8601 UTC timestamp (Bab 17.3 requires iso8601)."""
    return datetime.now(timezone.utc).isoformat()


class AgentMessage(BaseModel):
    """Point-to-point / broadcast message between agents (Bab 17.3).

    ``target_agent`` of ``"*"`` means broadcast to all subscribers.
    """

    message_id: str = Field(default_factory=new_uuid)
    sender_agent: str
    target_agent: str
    task_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default_factory=new_uuid)
    timestamp: str = Field(default_factory=utc_now_iso)


class Event(BaseModel):
    """Domain event published on the Event Bus (Bab 23, Bab 4.5).

    ``event_type`` uses dotted names from :mod:`messaging.events`
    (e.g. ``agent.running``, ``workflow.completed``).
    """

    event_id: str = Field(default_factory=new_uuid)
    event_type: str
    source: str = ""
    trace_id: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=utc_now_iso)


class QueuedTask(BaseModel):
    """Envelope for long-running work handed to the Worker Queue (Bab 23 prinsip 2)."""

    task_id: str = Field(default_factory=new_uuid)
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default_factory=new_uuid)
    enqueued_at: str = Field(default_factory=utc_now_iso)
