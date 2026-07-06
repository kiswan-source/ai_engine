"""End-to-end test of the MCP Server (Bab 60, Tahap 28) — dogfoods our own
mcp_client.client.MCPClient against our own new mcp_server/server.py,
spawned as a REAL subprocess speaking the real MCP protocol over stdio.
Exact mirror of tests/unit/test_mcp_client.py's pattern against
mcp_client/demo_server.py, except this one proves the *server* side works,
and that RBAC (settings.MCP_SERVER_ROLE) actually gates a real process —
not just the fake-registry unit tests in tests/unit/test_mcp_server.py.

Safe/deterministic in CI (Bab 12.3): the subprocess is our own code, not a
live external service, same reasoning as the existing demo_server.py tests.
"""
import os
import sys

from mcp_client.client import MCPClient

_SERVER_CMD = [sys.executable, "-m", "mcp_server.server"]
_WRITTEN_FILE = os.path.expanduser("~/ai_engine/reports/mcp_server_e2e_test.txt")


def _client(role: str) -> MCPClient:
    return MCPClient(_SERVER_CMD, env={"MCP_SERVER_ROLE": role})


def teardown_function(_fn):
    if os.path.exists(_WRITTEN_FILE):
        os.remove(_WRITTEN_FILE)


async def test_list_tools_exposes_real_registry_tools_not_excluded_ones():
    client = _client("user")
    tools = await client.list_tools()
    names = {t["name"] for t in tools}
    assert "read_txt" in names
    assert "write_txt" in names
    assert "workspace_list_files" not in names
    assert "workspace_read_file" not in names
    assert "mcp_list_tools" not in names
    assert "mcp_call_tool" not in names


async def test_operator_role_can_write_and_read_a_real_file():
    writer = _client("operator")
    write_result = await writer.call_tool(
        "write_txt", {"filename": "mcp_server_e2e_test.txt", "content": "halo dari MCP client"}
    )
    assert write_result["success"] is True
    assert os.path.exists(_WRITTEN_FILE)

    reader = _client("operator")
    read_result = await reader.call_tool("read_txt", {"file_path": _WRITTEN_FILE})
    assert read_result["success"] is True
    assert "halo dari MCP client" in read_result["text"]


async def test_default_user_role_denies_write_tool_on_real_process():
    client = _client("user")
    result = await client.call_tool(
        "write_txt", {"filename": "mcp_server_e2e_test.txt", "content": "harusnya ditolak"}
    )
    assert result["success"] is False
    assert not os.path.exists(_WRITTEN_FILE)
