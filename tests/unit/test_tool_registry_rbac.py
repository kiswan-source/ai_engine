"""Unit tests for ToolRegistry's optional RBAC gate (Bab 30 rule 2, ADR-0013).

The ``role`` kwarg on ``ToolRegistry.execute()`` is additive: omitting it
(as core/chat/'s ChatEngine still does) must behave exactly as before this
change existed. Only ``write_pdf`` is gated today (TOOL_RISK_ACTIONS pilot).
"""
import pytest

from agent.tools.registry import ToolRegistry


def _registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("write_pdf", lambda **kw: {"file": "x.pdf", **kw}, "pilot high-risk tool")
    reg.register("read_txt", lambda **kw: {"text": "hi"}, "unrelated, ungated tool")
    return reg


def test_execute_without_role_is_unaffected():
    reg = _registry()
    assert reg.execute("write_pdf", {"filename": "a.pdf"}) == {"file": "x.pdf", "filename": "a.pdf"}


def test_execute_with_role_denies_write_pdf_for_user():
    reg = _registry()
    with pytest.raises(PermissionError):
        reg.execute("write_pdf", {"filename": "a.pdf"}, role="user")


def test_execute_with_role_allows_write_pdf_for_operator():
    reg = _registry()
    assert reg.execute("write_pdf", {"filename": "a.pdf"}, role="operator")["file"] == "x.pdf"


def test_execute_with_role_allows_write_pdf_for_admin():
    reg = _registry()
    assert reg.execute("write_pdf", {"filename": "a.pdf"}, role="admin")["file"] == "x.pdf"


def test_execute_with_role_unaffected_for_ungated_tool():
    reg = _registry()
    # "user" lacks tool:write_pdf but read_txt isn't in TOOL_RISK_ACTIONS at all.
    assert reg.execute("read_txt", None, role="user") == {"text": "hi"}
