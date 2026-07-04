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

Tahap 8: pending requests live in a pluggable :class:`~memory.stores.HashStore`
(``APPROVAL_STATE_BACKEND=memory|redis``) instead of a plain dict — Bab 38
rule 1 requires every service to be stateless (state in Redis/PostgreSQL,
not process memory) so it can be replicated horizontally. :meth:`get`,
:meth:`pending`, and :meth:`overdue` are now async — the same kind of
contract change ``VectorMemory`` made in Tahap 5 for the same reason
(delegating to a store that might be remote).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from core.utils.logger import get_logger
from memory.stores import HashStore, InMemoryHashStore, RedisHashStore
from messaging import EventBus
from messaging.events import workflow_event

logger = get_logger(__name__)

_SCOPE = "approvals"


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


def _default_store() -> HashStore:
    from api.config import settings

    if settings.APPROVAL_STATE_BACKEND.lower() == "redis":
        return RedisHashStore("approvals")
    return InMemoryHashStore()


class HumanApprovalGate:
    """Tracks pending approval requests and records approve/reject decisions."""

    def __init__(
        self,
        sla_seconds: int | None = None,
        event_bus: EventBus | None = None,
        store: HashStore | None = None,
    ) -> None:
        if sla_seconds is None:
            from api.config import settings

            sla_seconds = settings.APPROVAL_SLA_SECONDS
        self._sla = sla_seconds
        self._events = event_bus or EventBus()
        self._store = store or _default_store()

    async def _save(self, req: ApprovalRequest) -> None:
        await self._store.set_field(_SCOPE, req.trace_id, json.dumps(asdict(req)))

    async def request(self, trace_id: str, reason: str) -> ApprovalRequest:
        """Open an approval request for ``trace_id`` (task should already be REVIEWING)."""
        req = ApprovalRequest(trace_id=trace_id, reason=reason, sla_seconds=self._sla)
        await self._save(req)
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

        req = await self.get(trace_id)
        if req is None:
            raise KeyError(f"no pending approval for trace_id: {trace_id!r}")
        req.decided = True
        req.approved = approved
        req.decided_by = decided_by
        req.decision_reason = reason
        req.decided_at = time.time()
        await self._save(req)
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

    async def get(self, trace_id: str) -> ApprovalRequest | None:
        raw = await self._store.get_field(_SCOPE, trace_id)
        return ApprovalRequest(**json.loads(raw)) if raw else None

    async def pending(self) -> list[ApprovalRequest]:
        all_raw = await self._store.get_all(_SCOPE)
        return [
            req
            for req in (ApprovalRequest(**json.loads(v)) for v in all_raw.values())
            if not req.decided
        ]

    async def overdue(self) -> list[ApprovalRequest]:
        """Pending requests past their SLA (Bab 61.3 rule 1 — escalation candidates)."""
        return [r for r in await self.pending() if r.overdue]
