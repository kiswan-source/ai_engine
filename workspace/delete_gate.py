"""Workspace Delete Gate (Workspace Slice 2, Fase 12).

Delete is the one Workspace mutation the DCF decision engine classifies
HUMAN-ONLY (irreversible action) rather than SHARED/AUTONOMOUS — this module
is the mechanism Owner approved to satisfy that: a two-step, token-gated
confirmation mirroring `workflows/approval.py::HumanApprovalGate`'s shape
(pending state until a human explicitly confirms, requester/approver identity
recorded, never auto-decides) rather than a full async approval queue —
delete confirmation is meant to be an immediate, same-session two-click flow,
not a multi-day SLA-tracked review, so there's no `overdue`/escalation
concept here, just a short TTL on the token.

Deliberately not reachable from chat (Owner decision, mirrors why
`workspace/versioning.py`'s restore is API-only, not a chat tool) — see
`api/routes/workspace.py`'s delete-request/delete-confirm routes, the only
callers.
"""
from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass, field

from core.utils.logger import get_logger
from memory.stores import HashStore, InMemoryHashStore, RedisHashStore

logger = get_logger(__name__)

_SCOPE = "workspace_delete_requests"
# Long enough for a human to read a confirmation dialog and click confirm,
# short enough to limit a leaked/stale token's exposure window.
DEFAULT_TTL_SECONDS = 300


@dataclass
class DeleteRequest:
    """One pending (or resolved) delete confirmation."""

    token: str
    workspace_id: str
    folder_id: str
    relative_path: str
    requested_by: str
    requested_at: float = field(default_factory=time.time)
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    decided: bool = False
    confirmed: bool | None = None
    decided_by: str = ""
    reason: str = ""
    decided_at: float | None = None

    @property
    def expired(self) -> bool:
        return not self.decided and (time.time() - self.requested_at) > self.ttl_seconds


def _default_store() -> HashStore:
    from api.config import settings

    if settings.APPROVAL_STATE_BACKEND.lower() == "redis":
        return RedisHashStore("workspace_delete")
    return InMemoryHashStore()


class WorkspaceDeleteGate:
    """Tracks pending delete-confirmation tokens — never deletes anything
    itself (that's the caller's job, in `api/routes/workspace.py`, only
    after :meth:`confirm` succeeds); this class only tracks the
    human-in-the-loop state, same separation of concerns
    `HumanApprovalGate` already has from whatever workflow it gates."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS, store: HashStore | None = None) -> None:
        self._ttl = ttl_seconds
        self._store = store or _default_store()

    async def _save(self, req: DeleteRequest) -> None:
        # Best-effort store-level cleanup, NOT the source of truth for
        # whether a token is usable — HashStore's ttl applies to the whole
        # "workspace_delete_requests" scope key, not per-token field (both
        # InMemoryHashStore and RedisHashStore expire per-name, not
        # per-field), so writing a new request resets every other pending
        # token's cleanup timer too. `DeleteRequest.expired` (wall-clock,
        # per-request `requested_at`) is what `confirm()` actually checks —
        # this ttl only bounds how long a fully-idle store hangs onto stale
        # entries, same non-guarantee HumanApprovalGate accepts by not
        # passing a ttl here at all.
        await self._store.set_field(_SCOPE, req.token, json.dumps(asdict(req)), ttl=req.ttl_seconds + 60)

    async def request(
        self, workspace_id: str, folder_id: str, relative_path: str, requested_by: str,
    ) -> DeleteRequest:
        """Open a delete confirmation request — does not touch the filesystem."""
        token = secrets.token_urlsafe(24)
        req = DeleteRequest(
            token=token, workspace_id=workspace_id, folder_id=folder_id,
            relative_path=relative_path, requested_by=requested_by, ttl_seconds=self._ttl,
        )
        await self._save(req)
        logger.info(
            "workspace_delete.requested", workspace_id=workspace_id, folder_id=folder_id,
            relative_path=relative_path, requested_by=requested_by,
        )
        return req

    async def get(self, token: str) -> DeleteRequest | None:
        raw = await self._store.get_field(_SCOPE, token)
        return DeleteRequest(**json.loads(raw)) if raw else None

    async def confirm(self, token: str, decided_by: str, reason: str = "") -> DeleteRequest:
        """Mark ``token`` as confirmed — raises if it doesn't exist, was
        already decided, or has expired. Does NOT perform the actual delete;
        the caller only does that after this call succeeds, then should
        treat the request as consumed (a token is single-use by construction
        — a second :meth:`confirm` call with the same token always raises)."""
        req = await self.get(token)
        if req is None:
            raise KeyError(f"no pending delete request for token: {token!r}")
        if req.decided:
            raise ValueError("delete confirmation token was already used")
        if req.expired:
            raise ValueError("delete confirmation token has expired")
        req.decided = True
        req.confirmed = True
        req.decided_by = decided_by
        req.reason = reason
        req.decided_at = time.time()
        await self._save(req)
        logger.info("workspace_delete.confirmed", token=token, decided_by=decided_by)
        return req


_shared_gate: WorkspaceDeleteGate | None = None


def get_shared_delete_gate() -> WorkspaceDeleteGate:
    """Process-wide singleton — the delete-request and delete-confirm HTTP
    calls are two separate requests, so a fresh `WorkspaceDeleteGate()` per
    call (each with its own `InMemoryHashStore()`) would lose every pending
    token between them for the in-memory (dev/CI default) backend. Same
    singleton pattern `memory/memory_manager.py::get_shared_memory_manager()`
    and `orchestrator/orchestrator.py::get_shared_orchestrator()` already
    established for this exact reason."""
    global _shared_gate
    if _shared_gate is None:
        _shared_gate = WorkspaceDeleteGate()
    return _shared_gate
