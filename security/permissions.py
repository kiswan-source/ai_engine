"""RBAC — Role-Based Access Control (MASTER_INSTRUCTION.md Bab 30 rule 2).

A static role -> permission matrix, deliberately simple (Bab 45.3 — no policy-
engine dependency). Bab 30 rule 2 specifically calls for gating high-risk
tool calls (filesystem write, code execution, email/calendar access) through
this — those tools live in ``agent/tools/``, a protected folder (Bab 45.1)
this session doesn't touch. The one live integration point is
``Orchestrator.finalize_approval()`` (Bab 61.3's human-approval decision),
checked only when a caller supplies a role; callers that don't keep the
pre-Tahap-7 behavior exactly (no role given = no check, same as before this
module existed).
"""
from __future__ import annotations

# role -> permitted actions. "*" means every action (checked first, so it
# doesn't need repeating per role).
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "approver": frozenset({"approve_workflow", "view_dashboard"}),
    "user": frozenset({"view_dashboard"}),
}


def has_permission(role: str, action: str) -> bool:
    """Whether ``role`` may perform ``action``."""
    permitted = _ROLE_PERMISSIONS.get(role, frozenset())
    return "*" in permitted or action in permitted


def require_permission(role: str, action: str) -> None:
    """Raise :class:`PermissionError` if ``role`` may not perform ``action``."""
    if not has_permission(role, action):
        raise PermissionError(f"role {role!r} lacks permission {action!r}")


def require_role(action: str):
    """FastAPI dependency factory: 403 unless the current principal may perform ``action``.

    Not wired into any route today — ready for one that opts in, e.g.
    ``Depends(require_role("approve_workflow"))``.
    """
    from fastapi import Depends, HTTPException

    from .auth import Principal, get_current_principal

    async def _check(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not has_permission(principal.role, action):
            raise HTTPException(status_code=403, detail=f"role {principal.role!r} lacks permission {action!r}")
        return principal

    return _check
