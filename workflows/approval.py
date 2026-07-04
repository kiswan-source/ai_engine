"""Human Approval gate (MASTER_INSTRUCTION.md Bab 24, 61).

Deliberately **not** a :class:`~workflows.base.BaseWorkflow`: Human Approval
doesn't produce a result from a graph, it gates a result another workflow
already produced. A task lands here by transitioning to ``State.REVIEWING``
(Bab 49) and stays there until a human calls :meth:`HumanApprovalGate.decide`
— this module never auto-decides anything (Bab 61.3 rule 1: approval must not
become a silent bottleneck, but resolving that is an SLA/escalation concern
for the caller, not a timeout that fabricates a decision).

Tahap 7: every decision is recorded in the append-only security audit trail
with the approver's identity and reason (Bab 61.3 rule 2), not just the
structured logger — RBAC-gating *who* may call :meth:`decide` is the
caller's job (``Orchestrator.finalize_approval``), since this class has no
notion of a principal.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.utils.logger import get_logger
from messaging import EventBus
from messaging.events import workflow_event

logger = get_logger(__name__)


@dataclass
class ApprovalRequest:
    """One pending (or resolved) Human Approval request (Bab 61)."""

    trace_id: str
    reason: str
    requested_at: float = field(default_factory=time.time)
    sla_seconds: int = 3600
    decided: bool = False
    approved: bool | None = None
    decided_by: str = ""
    decision_reason: str = ""
    decided_at: float | None = None

    @property
    def overdue(self) -> bool:
        """Past its SLA without a decision (Bab 61.3 rule 1 — needs escalation)."""
        return not self.decided and (time.time() - self.requested_at) > self.sla_seconds


class HumanApprovalGate:
    """Tracks pending approval requests and records approve/reject decisions."""

    def __init__(self, sla_seconds: int | None = None, event_bus: EventBus | None = None) -> None:
        if sla_seconds is None:
            from api.config import settings

            sla_seconds = settings.APPROVAL_SLA_SECONDS
        self._sla = sla_seconds
        self._events = event_bus or EventBus()
        self._pending: dict[str, ApprovalRequest] = {}

    async def request(self, trace_id: str, reason: str) -> ApprovalRequest:
        """Open an approval request for ``trace_id`` (task should already be REVIEWING)."""
        req = ApprovalRequest(trace_id=trace_id, reason=reason, sla_seconds=self._sla)
        self._pending[trace_id] = req
        await self._events.emit(
            workflow_event("reviewing"),
            source="human_approval",
            trace_id=trace_id,
            payload={"reason": reason},
        )
        logger.info("approval.requested", trace_id=trace_id, reason=reason)
        return req

    async def decide(self, trace_id: str, approved: bool, decided_by: str, reason: str = "") -> ApprovalRequest:
        """Record a human approve/reject decision (Bab 61.3 rule 2 — audited here)."""
        from security import audit_log

        req = self._pending.get(trace_id)
        if req is None:
            raise KeyError(f"no pending approval for trace_id: {trace_id!r}")
        req.decided = True
        req.approved = approved
        req.decided_by = decided_by
        req.decision_reason = reason
        req.decided_at = time.time()
        event = workflow_event("approved") if approved else workflow_event("cancelled")
        await self._events.emit(
            event,
            source="human_approval",
            trace_id=trace_id,
            payload={"decided_by": decided_by, "reason": reason},
        )
        await audit_log.record(
            "human_approval.decided",
            actor=decided_by,
            detail={"approved": approved, "request_reason": req.reason, "decision_reason": reason},
            trace_id=trace_id,
            event_bus=self._events,
        )
        logger.info("approval.decided", trace_id=trace_id, approved=approved, decided_by=decided_by)
        return req

    def get(self, trace_id: str) -> ApprovalRequest | None:
        return self._pending.get(trace_id)

    def pending(self) -> list[ApprovalRequest]:
        return [r for r in self._pending.values() if not r.decided]

    def overdue(self) -> list[ApprovalRequest]:
        """Pending requests past their SLA (Bab 61.3 rule 1 — escalation candidates)."""
        return [r for r in self.pending() if r.overdue]
