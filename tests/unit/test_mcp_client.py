"""Unit tests for MCPClient (Bab 60) against the real demo MCP server
(`mcp_client/demo_server.py`) — a local subprocess we ship ourselves, not a
live external service, so this is safe and deterministic in CI (Bab 12.3)
the same way a CLI-tool subprocess test would be.
"""
from mcp_client.client import MCPClient
from mcp_client.config import MCP_SERVERS


async def test_list_tools_discovers_demo_server_tools():
    client = MCPClient(MCP_SERVERS["demo"])
    tools = await client.list_tools()
    names = {t["name"] for t in tools}
    assert names == {"add", "reverse_text"}


async def test_call_tool_add_returns_real_computed_result():
    client = MCPClient(MCP_SERVERS["demo"])
    result = await client.call_tool("add", {"a": 3, "b": 4})
    assert result["success"] is True
    assert result["text"] == "7.0"


async def test_call_tool_reverse_text():
    client = MCPClient(MCP_SERVERS["demo"])
    result = await client.call_tool("reverse_text", {"text": "AI Engine"})
    assert result["success"] is True
    assert result["text"] == "enignE IA"


async def test_call_tool_unknown_tool_is_error():
    client = MCPClient(MCP_SERVERS["demo"])
    result = await client.call_tool("does_not_exist", {})
    assert result["success"] is False
