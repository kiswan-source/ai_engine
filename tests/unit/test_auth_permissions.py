"""Unit tests for Authentication + RBAC (Bab 30, 58) — no live services (Bab 12.3)."""
import pytest
from fastapi import HTTPException

from security.auth import Principal, get_current_principal, verify_api_key
from security.permissions import (
    check_tool_permission,
    has_permission,
    has_workspace_permission,
    require_permission,
    require_role,
    require_workspace_permission,
)


# ─── auth.py ──────────────────────────────────────────────────────────────

def test_verify_api_key_valid_with_default_role(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "secret123")
    principal = verify_api_key("secret123")
    assert principal is not None
    assert principal.role == "user"


def test_verify_api_key_with_explicit_role(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "adminkey:admin,userkey:user")
    principal = verify_api_key("adminkey")
    assert principal.role == "admin"


def test_verify_api_key_invalid_returns_none(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "secret123")
    assert verify_api_key("wrong") is None


async def test_get_current_principal_disabled_when_no_keys_configured(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    principal = await get_current_principal(api_key=None)
    assert principal.role == "admin"


async def test_get_current_principal_rejects_missing_key_when_configured(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "secret123")
    with pytest.raises(HTTPException) as exc_info:
        await get_current_principal(api_key=None)
    assert exc_info.value.status_code == 401


async def test_get_current_principal_accepts_valid_key(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "secret123:approver")
    principal = await get_current_principal(api_key="secret123")
    assert principal.role == "approver"


# ─── permissions.py ───────────────────────────────────────────────────────

def test_admin_has_every_permission():
    assert has_permission("admin", "approve_workflow")
    assert has_permission("admin", "anything_at_all")


def test_approver_can_approve_workflow():
    assert has_permission("approver", "approve_workflow")


def test_user_cannot_approve_workflow():
    assert not has_permission("user", "approve_workflow")


def test_unknown_role_has_no_permissions():
    assert not has_permission("ghost", "view_dashboard")


def test_require_permission_raises_for_denied_role():
    with pytest.raises(PermissionError):
        require_permission("user", "approve_workflow")


def test_require_permission_passes_for_allowed_role():
    require_permission("approver", "approve_workflow")  # must not raise


# ─── Workspace Slice 2: delete_output is owner-only, unlike write_output ──

def test_owner_has_delete_output():
    assert has_workspace_permission("owner", "delete_output")


def test_editor_lacks_delete_output():
    """Editor has write_output but NOT delete_output — delete is the one
    Workspace mutation the DCF decision engine classifies HUMAN-ONLY, so it
    gets the narrowest permission tier, unlike every other mutation."""
    assert has_workspace_permission("editor", "write_output")
    assert not has_workspace_permission("editor", "delete_output")


def test_viewer_lacks_delete_output():
    assert not has_workspace_permission("viewer", "delete_output")


def test_require_workspace_permission_raises_for_editor_delete():
    with pytest.raises(PermissionError):
        require_workspace_permission("editor", "delete_output")


async def test_require_role_dependency_allows_permitted_principal():
    checker = require_role("approve_workflow")
    principal = Principal(api_key="k", role="approver")
    result = await checker(principal=principal)
    assert result is principal


async def test_require_role_dependency_rejects_denied_principal():
    checker = require_role("approve_workflow")
    principal = Principal(api_key="k", role="user")
    with pytest.raises(HTTPException) as exc_info:
        await checker(principal=principal)
    assert exc_info.value.status_code == 403


# ─── check_tool_permission (Bab 30 rule 2 pilot, ADR-0013) ────────────────

def test_check_tool_permission_noop_for_unmapped_tool():
    check_tool_permission("user", "read_txt")  # not in TOOL_RISK_ACTIONS, must not raise


def test_check_tool_permission_denies_user_for_write_pdf():
    with pytest.raises(PermissionError):
        check_tool_permission("user", "write_pdf")


def test_check_tool_permission_allows_operator_for_write_pdf():
    check_tool_permission("operator", "write_pdf")  # must not raise


def test_check_tool_permission_allows_admin_for_write_pdf():
    check_tool_permission("admin", "write_pdf")  # must not raise


# ─── plugin:weather (Bab 59) ───────────────────────────────────────────────

def test_check_tool_permission_denies_user_for_plugin_weather():
    with pytest.raises(PermissionError):
        check_tool_permission("user", "plugin_weather")


def test_check_tool_permission_allows_operator_for_plugin_weather():
    check_tool_permission("operator", "plugin_weather")  # must not raise


# ─── write_*/convert_geo/generate_code migration (Bab 30 rule 2, Tahap 18) ──

_MIGRATED_TOOLS = [
    "write_docx", "write_html", "write_txt", "write_json",
    "write_geojson", "write_shp", "convert_geo", "generate_code",
]


@pytest.mark.parametrize("tool_name", _MIGRATED_TOOLS)
def test_check_tool_permission_denies_user_for_migrated_tool(tool_name):
    with pytest.raises(PermissionError):
        check_tool_permission("user", tool_name)


@pytest.mark.parametrize("tool_name", _MIGRATED_TOOLS)
def test_check_tool_permission_allows_operator_for_migrated_tool(tool_name):
    check_tool_permission("operator", tool_name)  # must not raise


@pytest.mark.parametrize("tool_name", _MIGRATED_TOOLS)
def test_check_tool_permission_allows_admin_for_migrated_tool(tool_name):
    check_tool_permission("admin", tool_name)  # must not raise


def test_check_tool_permission_noop_for_image_tools():
    # Image transforms are deliberately left ungated (different risk profile
    # from "write filesystem" — see security/permissions.py docstring).
    check_tool_permission("user", "image_resize")
    check_tool_permission("user", "images_to_pdf")


async def test_require_role_manage_plugins_allows_admin():
    checker = require_role("manage_plugins")
    principal = Principal(api_key="k", role="admin")
    result = await checker(principal=principal)
    assert result is principal


async def test_require_role_manage_plugins_rejects_operator():
    checker = require_role("manage_plugins")
    principal = Principal(api_key="k", role="operator")
    with pytest.raises(HTTPException) as exc_info:
        await checker(principal=principal)
    assert exc_info.value.status_code == 403


# ─── mcp:call (Bab 60) ─────────────────────────────────────────────────────

def test_check_tool_permission_denies_user_for_mcp_call_tool():
    with pytest.raises(PermissionError):
        check_tool_permission("user", "mcp_call_tool")


def test_check_tool_permission_allows_operator_for_mcp_call_tool():
    check_tool_permission("operator", "mcp_call_tool")  # must not raise


def test_check_tool_permission_noop_for_mcp_list_tools():
    check_tool_permission("user", "mcp_list_tools")  # not gated — discovery only


# ─── Workspace Permission (Bab 69.7, resource-scoped via Project role, Tahap 19) ──

@pytest.mark.parametrize("action", ["read", "write_output", "generated", "knowledge", "vector", "temporary", "admin"])
@pytest.mark.parametrize("project_role", ["owner", "editor"])
def test_workspace_permission_owner_editor_get_full_access(project_role, action):
    assert has_workspace_permission(project_role, action)
    require_workspace_permission(project_role, action)  # must not raise


@pytest.mark.parametrize("action", ["read", "read_only", "knowledge", "vector"])
def test_workspace_permission_viewer_allowed_actions(action):
    # "read" added Tahap 30 — api/routes/chat.py has only ever checked
    # "read" (not "read_only", which nothing else checks for), so viewer
    # was silently locked out of Workspace Chat before this fix.
    assert has_workspace_permission("viewer", action)


@pytest.mark.parametrize("action", ["write_output", "admin", "generated", "temporary"])
def test_workspace_permission_viewer_denied_write_actions(action):
    assert not has_workspace_permission("viewer", action)
    with pytest.raises(PermissionError):
        require_workspace_permission("viewer", action)


def test_workspace_permission_non_member_denied():
    assert not has_workspace_permission(None, "read")
    with pytest.raises(PermissionError):
        require_workspace_permission(None, "read")


def test_workspace_permission_unknown_role_denied():
    assert not has_workspace_permission("stranger", "read")
