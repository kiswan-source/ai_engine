"""Unit tests for Authentication + RBAC (Bab 30, 58) — no live services (Bab 12.3)."""
import pytest
from fastapi import HTTPException

from security.auth import Principal, get_current_principal, verify_api_key
from security.permissions import check_tool_permission, has_permission, require_permission, require_role


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
