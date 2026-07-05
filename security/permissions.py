"""RBAC — Role-Based Access Control (MASTER_INSTRUCTION.md Bab 30 rule 2).

A static role -> permission matrix, deliberately simple (Bab 45.3 — no policy-
engine dependency). The one long-standing integration point is
``Orchestrator.finalize_approval()`` (Bab 61.3's human-approval decision),
checked only when a caller supplies a role; callers that don't keep the
pre-Tahap-7 behavior exactly (no role given = no check, same as before this
module existed).

Tahap 10 (ADR-0013) adds the first real tool-call gate into ``agent/tools/``
(a protected folder, Bab 45.1) via the strangler pattern: ``write_pdf`` is
the pilot high-risk tool (Bab 30 rule 2's "write filesystem" category).
``TOOL_RISK_ACTIONS`` is deliberately a single entry for now — the plan is
to migrate the rest of the ``write_*``/``convert_geo`` tools one at a time
in later sessions, not all at once.

Tahap 16 (Plugin, Bab 59) adds ``plugin:weather`` the same way — gated via
``TOOL_RISK_ACTIONS`` when a caller passes a role (only ``/api/v1/agent/run``
does today; ``core/chat/`` still doesn't pass a role at all, same
long-standing gap ``write_pdf`` already has). ``manage_plugins`` gates the
Settings-area enable/disable toggle (``api/routes/plugins.py``) via
``require_role`` — the first real caller of that dependency factory.

Tahap 17 (MCP, Bab 60) adds ``mcp:call`` — Bab 60.1: "Setiap tool yang
diekspos via MCP tunduk pada validasi ``security/permissions.py`` yang sama
seperti tool internal... MCP tidak memiliki jalur pintas keamanan." One
action covers every MCP server/tool a caller might reach through
``mcp_call_tool`` — fine-grained per-server-per-tool permissions would be
premature for a client that talks to exactly one configured (demo) server
today. ``mcp_list_tools`` (read-only discovery) stays ungated, same
posture as ``ToolRegistry.list_tools()`` for internal tools.
"""
from __future__ import annotations

# role -> permitted actions. "*" means every action (checked first, so it
# doesn't need repeating per role).
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "operator": frozenset({"tool:write_pdf", "view_dashboard", "plugin:weather", "mcp:call"}),
    "approver": frozenset({"approve_workflow", "view_dashboard"}),
    "user": frozenset({"view_dashboard"}),
}

# tool name -> permission action, for tools gated via ToolRegistry.execute()
# (agent/tools/registry.py). A tool absent from this mapping is unaffected
# regardless of role — this is a pilot for a couple of high-risk tools, not a
# blanket policy over every tool in the registry.
TOOL_RISK_ACTIONS: dict[str, str] = {
    "write_pdf": "tool:write_pdf",
    "plugin_weather": "plugin:weather",
    "mcp_call_tool": "mcp:call",
}


def has_permission(role: str, action: str) -> bool:
    """Whether ``role`` may perform ``action``."""
    permitted = _ROLE_PERMISSIONS.get(role, frozenset())
    return "*" in permitted or action in permitted


def require_permission(role: str, action: str) -> None:
    """Raise :class:`PermissionError` if ``role`` may not perform ``action``."""
    if not has_permission(role, action):
        raise PermissionError(f"role {role!r} lacks permission {action!r}")


def check_tool_permission(role: str, tool_name: str) -> None:
    """Raise :class:`PermissionError` if ``role`` may not call ``tool_name``.

    A no-op for any tool not listed in :data:`TOOL_RISK_ACTIONS` — only the
    pilot tool is gated today.
    """
    action = TOOL_RISK_ACTIONS.get(tool_name)
    if action is None:
        return
    require_permission(role, action)


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
