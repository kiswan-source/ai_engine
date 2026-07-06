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
``TOOL_RISK_ACTIONS`` started as a single entry, migrated the rest of the
``write_*``/``convert_geo``/``generate_code`` tools in Tahap 18 (same
strangler pattern, one line per tool, no registry/engine changes needed).

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

Tahap 18 finishes the ``write_*``/``convert_geo``/``generate_code`` migration
Tahap 10's docstring promised: ``write_docx``, ``write_html``, ``write_txt``,
``write_json``, ``write_geojson``, ``write_shp``, ``convert_geo``, and
``generate_code`` all get a ``tool:<name>`` action, same shape as
``tool:write_pdf``. Image tools (``image_*``, ``images_to_pdf``) are
deliberately left out — they transform an existing file already on disk
rather than writing new content from an arbitrary prompt, a materially
different risk profile from "write filesystem" (Bab 30 rule 2). Read-only
tools (``read_*``, ``calculate_area``) stay ungated for the same reason
``mcp_list_tools`` does — no write, no risk category to gate.

Tahap 19 (Workspace, Bab 69.7/ADR-0005) adds Workspace Permission
(``read``/``write_output``/``read_only``/``temporary``/``generated``/
``knowledge``/``vector``/``admin``) — but this one is **not** shaped like
``TOOL_RISK_ACTIONS`` or ``_ROLE_PERMISSIONS``, because a Workspace is
always a resource belonging to exactly one ``Project`` (Bab 69.11: "Workspace
adalah bagian dari Project"), so access is mediated through that Project's
membership role (owner/editor/viewer — the same roles
``api/routes/projects.py::_role_for``/``_require`` already compute), not a
global system role. ``WORKSPACE_PERMISSIONS_BY_PROJECT_ROLE`` below is that
second, deliberately separate mapping.
"""
from __future__ import annotations

# role -> permitted actions. "*" means every action (checked first, so it
# doesn't need repeating per role).
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": frozenset({"*"}),
    "operator": frozenset({
        "tool:write_pdf", "tool:write_docx", "tool:write_html", "tool:write_txt",
        "tool:write_json", "tool:write_geojson", "tool:write_shp", "tool:convert_geo",
        "tool:generate_code", "view_dashboard", "plugin:weather", "mcp:call",
    }),
    "approver": frozenset({"approve_workflow", "view_dashboard"}),
    "user": frozenset({"view_dashboard"}),
}

# tool name -> permission action, for tools gated via ToolRegistry.execute()
# (agent/tools/registry.py). A tool absent from this mapping is unaffected
# regardless of role.
TOOL_RISK_ACTIONS: dict[str, str] = {
    "write_pdf": "tool:write_pdf",
    "write_docx": "tool:write_docx",
    "write_html": "tool:write_html",
    "write_txt": "tool:write_txt",
    "write_json": "tool:write_json",
    "write_geojson": "tool:write_geojson",
    "write_shp": "tool:write_shp",
    "convert_geo": "tool:convert_geo",
    "generate_code": "tool:generate_code",
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


# Project role -> permitted Workspace Permission actions (Bab 69.7). Separate
# from _ROLE_PERMISSIONS on purpose — see module docstring, Tahap 19. Owner
# and editor get the same set here (PROJECT_SPECIFICATION.md leaves no
# owner/editor distinction for Workspace specifically, unlike e.g. archiving
# a Project, which projects.py restricts to owner-only).
WORKSPACE_PERMISSIONS_BY_PROJECT_ROLE: dict[str, frozenset[str]] = {
    "owner": frozenset({"read", "write_output", "generated", "knowledge", "vector", "temporary", "admin"}),
    "editor": frozenset({"read", "write_output", "generated", "knowledge", "vector", "temporary", "admin"}),
    "viewer": frozenset({"read_only", "knowledge", "vector"}),
}


def has_workspace_permission(project_role: str | None, action: str) -> bool:
    """Whether a caller with ``project_role`` on the owning Project may perform
    Workspace ``action`` (one of ``WORKSPACE_PERMISSIONS_BY_PROJECT_ROLE``'s values).
    ``project_role=None`` (not a member at all) always denies."""
    if project_role is None:
        return False
    return action in WORKSPACE_PERMISSIONS_BY_PROJECT_ROLE.get(project_role, frozenset())


def require_workspace_permission(project_role: str | None, action: str) -> None:
    """Raise :class:`PermissionError` if ``project_role`` may not perform Workspace ``action``."""
    if not has_workspace_permission(project_role, action):
        raise PermissionError(f"project role {project_role!r} lacks workspace permission {action!r}")


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
