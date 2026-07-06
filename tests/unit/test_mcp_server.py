"""Unit tests for the MCP Server (Bab 60, Tahap 28) — the opposite direction
from mcp_client/: exposing AI_ENGINE's own tools to external MCP clients.

Uses a fake ToolRegistry (same pattern as test_tool_registry_rbac.py) so
these stay fast/hermetic — no real file I/O, no real subprocess. The real
protocol round trip against a real subprocess lives in
tests/integration/test_mcp_server_e2e.py.
"""
import pytest

from agent.tools.registry import ToolRegistry
from mcp_server.server import _allowed_schemas, dispatch_tool_call


def _fake_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("read_txt", lambda **kw: {"text": "isi file", **kw}, "unrelated, ungated tool")
    reg.register("write_txt", lambda **kw: {"success": True, "file": "x.txt", **kw}, "pilot high-risk tool")
    return reg


def _workspace_echo_registry() -> ToolRegistry:
    """Echoes received kwargs back — lets tests assert what dispatch_tool_call injected."""
    reg = ToolRegistry()
    reg.register(
        "workspace_write_file",
        lambda **kwargs: {"success": True, "received_args": kwargs},
        "fake workspace_write_file echoing received args",
    )
    reg.register(
        "workspace_read_file",
        lambda **kwargs: {"success": True, "received_args": kwargs},
        "fake workspace_read_file echoing received args",
    )
    return reg


def test_allowed_schemas_excludes_workspace_and_mcp_meta_tools_by_default():
    names = {s["function"]["name"] for s in _allowed_schemas()}
    assert "workspace_list_files" not in names
    assert "workspace_read_file" not in names
    assert "workspace_write_file" not in names
    assert "mcp_list_tools" not in names
    assert "mcp_call_tool" not in names


def test_allowed_schemas_includes_workspace_tools_when_configured():
    names = {s["function"]["name"] for s in _allowed_schemas(include_workspace=True)}
    assert "workspace_list_files" in names
    assert "workspace_read_file" in names
    assert "workspace_write_file" in names
    # mcp_* stays excluded regardless of Workspace config — unrelated reason.
    assert "mcp_list_tools" not in names
    assert "mcp_call_tool" not in names


def test_allowed_schemas_includes_known_tools():
    names = {s["function"]["name"] for s in _allowed_schemas()}
    assert "read_txt" in names
    assert "write_pdf" in names


async def test_dispatch_unknown_tool_raises():
    reg = _fake_registry()
    with pytest.raises(ValueError):
        await dispatch_tool_call(reg, "admin", "does_not_exist", {})


async def test_dispatch_excluded_tool_raises_even_if_in_registry():
    reg = ToolRegistry()
    reg.register("workspace_list_files", lambda **kw: {"files": []}, "excluded")
    with pytest.raises(ValueError):
        await dispatch_tool_call(reg, "admin", "workspace_list_files", {})


async def test_dispatch_denies_write_for_default_user_role():
    reg = _fake_registry()
    with pytest.raises(PermissionError):
        await dispatch_tool_call(reg, "user", "write_txt", {"filename": "a.txt", "content": "hi"})


async def test_dispatch_allows_write_for_operator_role():
    reg = _fake_registry()
    result = await dispatch_tool_call(reg, "operator", "write_txt", {"filename": "a.txt", "content": "hi"})
    assert result["success"] is True
    assert result["file"] == "x.txt"


async def test_dispatch_read_tool_unaffected_by_role():
    reg = _fake_registry()
    result = await dispatch_tool_call(reg, "user", "read_txt", {"file_path": "a.txt"})
    assert result["text"] == "isi file"


# ─── Workspace access via MCP Server (Bab 60.1 + 69.5, Tahap 32) ────────

async def test_dispatch_workspace_tool_without_workspace_id_configured_raises():
    reg = _workspace_echo_registry()
    with pytest.raises(ValueError):
        await dispatch_tool_call(reg, "user", "workspace_read_file", {"folder_id": "f1", "relative_path": "a.txt"})


async def test_dispatch_injects_configured_workspace_id_overriding_caller_supplied_value():
    reg = _workspace_echo_registry()
    result = await dispatch_tool_call(
        reg, "user", "workspace_read_file",
        {"folder_id": "f1", "relative_path": "a.txt", "workspace_id": "fake-hallucinated-id"},
        workspace_id="real-ws-id", workspace_role="viewer",
    )
    assert result["received_args"]["workspace_id"] == "real-ws-id"


async def test_dispatch_denies_workspace_write_for_viewer_role():
    reg = _workspace_echo_registry()
    with pytest.raises(PermissionError):
        await dispatch_tool_call(
            reg, "user", "workspace_write_file", {"folder_id": "f1", "relative_path": "a.txt", "content": "x"},
            workspace_id="real-ws-id", workspace_role="viewer",
        )


async def test_dispatch_allows_workspace_write_for_editor_role():
    reg = _workspace_echo_registry()
    result = await dispatch_tool_call(
        reg, "user", "workspace_write_file", {"folder_id": "f1", "relative_path": "a.txt", "content": "x"},
        workspace_id="real-ws-id", workspace_role="editor",
    )
    assert result["success"] is True
    assert result["received_args"]["workspace_id"] == "real-ws-id"
