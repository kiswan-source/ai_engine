"""Audit Log (MASTER_INSTRUCTION.md Bab 30, 61.3) — append-only trail of sensitive actions.

Writes one JSON line per entry to ``AUDIT_LOG_PATH`` (default
``security_audit.log``) — a dedicated file. The pre-existing ``audit.log`` at
the repo root is already this deployment's systemd stdout-capture target
(general request/access logs), not a structured trail; writing JSON entries
into it would interleave them with arbitrary log lines and defeat the point
of an audit trail. Also publishes a ``security.<event_type>`` event on the
Event Bus (Bab 23 prinsip 1) so :class:`telemetry.tracing.Tracer` folds
audit entries into a request's Execution Timeline.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.utils.logger import get_logger
from messaging import EventBus

logger = get_logger(__name__)


@dataclass(frozen=True)
class AuditEntry:
    """One append-only audit record."""

    event_type: str
    actor: str
    detail: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    timestamp: float = field(default_factory=time.time)


def _write(entry: AuditEntry) -> None:
    from api.config import settings

    line = json.dumps(asdict(entry), default=str)
    try:
        with open(settings.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as exc:
        # Audit logging must never break the caller's actual operation (Bab 10.4).
        logger.error("audit_log.write_failed", error=str(exc))


async def record(
    event_type: str,
    actor: str,
    detail: dict[str, Any] | None = None,
    trace_id: str = "",
    event_bus: EventBus | None = None,
) -> AuditEntry:
    """Append one audit entry and publish it as a ``security.<event_type>`` event."""
    entry = AuditEntry(event_type=event_type, actor=actor, detail=detail or {}, trace_id=trace_id)
    _write(entry)
    events = event_bus or EventBus()
    await events.emit(f"security.{event_type}", source=actor, trace_id=trace_id, payload=entry.detail)
    return entry


def read_recent(limit: int = 100) -> list[AuditEntry]:
    """Newest ``limit`` entries from the audit log file (best-effort; missing file = empty)."""
    from api.config import settings

    try:
        with open(settings.AUDIT_LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [AuditEntry(**json.loads(line)) for line in lines[-limit:] if line.strip()]
