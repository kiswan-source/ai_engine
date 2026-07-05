"""Unit tests for the mcp_list_tools/mcp_call_tool bridge registered in
agent/tools/registry.py:build_registry() — real round trip against the demo
MCP server (see tests/unit/test_mcp_client.py's docstring for why that's
safe/deterministic in CI), plus the ENABLE_MCP gate (Bab 57).
"""
from agent.tools.registry import build_registry


def _registry():
    return build_registry(ollama_url="http://localhost:11434", model="gemma4:e2b")


def test_mcp_list_tools_discovers_demo_server():
    reg = _registry()
    result = reg.execute("mcp_list_tools", {"server": "demo"})
    names = {t["name"] for t in result}
    assert names == {"add", "reverse_text"}


def test_mcp_call_tool_returns_real_computed_result():
    reg = _registry()
    result = reg.execute("mcp_call_tool", {"server": "demo", "tool_name": "add", "arguments": {"a": 10, "b": 5}})
    assert result["success"] is True
    assert result["text"] == "15.0"


def test_mcp_call_tool_unknown_server():
    reg = _registry()
    result = reg.execute("mcp_call_tool", {"server": "ghost", "tool_name": "add"})
    assert result["success"] is False
    assert "tidak dikonfigurasi" in result["error"]


def test_mcp_disabled_via_settings_blocks_list(monkeypatch):
    monkeypatch.setattr("api.config.settings.ENABLE_MCP", False)
    reg = _registry()
    result = reg.execute("mcp_list_tools", {"server": "demo"})
    assert result["success"] is False
    assert "dinonaktifkan" in result["error"]


def test_mcp_disabled_via_settings_blocks_call(monkeypatch):
    monkeypatch.setattr("api.config.settings.ENABLE_MCP", False)
    reg = _registry()
    result = reg.execute("mcp_call_tool", {"server": "demo", "tool_name": "add", "arguments": {"a": 1, "b": 2}})
    assert result["success"] is False
    assert "dinonaktifkan" in result["error"]
