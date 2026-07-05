"""Configured MCP servers (Bab 60.2 — "Aktivasi MCP dikontrol melalui
ENABLE_MCP", Bab 57). Each entry is a command line that, when run, speaks MCP
over stdio — the same shape as most real-world MCP servers (`npx
@modelcontextprotocol/server-*`, `python -m some_server`, ...).

Only one server configured for now: the demo fixture (`mcp_client/demo_server.py`,
see its docstring) — a real third-party server can be added here the same way,
no code changes elsewhere required.
"""
import sys

MCP_SERVERS: dict[str, list[str]] = {
    "demo": [sys.executable, "-m", "mcp_client.demo_server"],
}
