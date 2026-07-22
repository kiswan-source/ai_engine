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


# ─── Output-path confinement (Gate 3 AEGIS audit, 2026-07-23) ────────────────
# write_docx/write_pdf/write_xlsx/write_pptx/write_txt/write_json/write_html
# all honor a directory component or absolute path in `filename` as-is when
# called directly as a Python function (relied on by Workspace-integrated
# writes and by tests that call the writers directly) — but a model-supplied
# `filename` reaching ToolRegistry.execute() has no such validation behind
# it. This used to let a chat tool call escape `reports/` entirely via
# `../` or an absolute path; execute() now strips to basename for exactly
# this set of tools before dispatching.

def _confined_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("write_docx", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("write_pdf", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("write_xlsx", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("write_pptx", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("write_txt", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("write_json", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("write_html", lambda **kw: {"seen_filename": kw["filename"]}, "confined")
    reg.register("read_txt", lambda **kw: {"seen_filename": kw.get("filename")}, "not confined")
    return reg


@pytest.mark.parametrize("tool_name", [
    "write_docx", "write_pdf", "write_xlsx", "write_pptx",
    "write_txt", "write_json", "write_html",
])
def test_execute_strips_absolute_path_to_basename_for_confined_writers(tool_name):
    reg = _confined_registry()
    result = reg.execute(tool_name, {"filename": "/etc/cron.d/evil", "title": "t", "content": "c"})
    assert result["seen_filename"] == "evil"


@pytest.mark.parametrize("tool_name", [
    "write_docx", "write_pdf", "write_xlsx", "write_pptx",
    "write_txt", "write_json", "write_html",
])
def test_execute_strips_directory_traversal_to_basename_for_confined_writers(tool_name):
    reg = _confined_registry()
    result = reg.execute(tool_name, {"filename": "../../../../etc/passwd", "title": "t", "content": "c"})
    assert result["seen_filename"] == "passwd"


def test_execute_leaves_plain_filename_untouched_for_confined_writer():
    reg = _confined_registry()
    result = reg.execute("write_docx", {"filename": "laporan.docx", "title": "t", "content": "c"})
    assert result["seen_filename"] == "laporan.docx"


def test_execute_does_not_confine_unrelated_tools():
    reg = _confined_registry()
    result = reg.execute("read_txt", {"filename": "/etc/passwd"})
    assert result["seen_filename"] == "/etc/passwd"
