"""MCP Client (MASTER_INSTRUCTION.md Bab 60) — connects to an MCP server over
stdio, does Tool/Capability Discovery, and normalizes tool results into a
plain dict (Bab 60.2: "Hasil dinormalisasi ke ToolResult").

Session Management here is deliberately simple for this first pass: one
short-lived connection (spawn subprocess → initialize → do one thing →
close) per call, not a persistent session kept alive across calls. Simpler
and safer to reason about than pooling/reconnect logic; the tradeoff (a
fresh subprocess per call) is an accepted gap for a pilot, not hidden.
"""
from __future__ import annotations

from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _normalize_result(result) -> dict[str, Any]:
    text_parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
    return {
        "success": not result.isError,
        "text": "\n".join(text_parts),
    }


class MCPClient:
    """Talks to one MCP server, launched via `command` (Bab 60.1's MCP Server)."""

    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        # `env` (Tahap 28) is merged on top of a safe default environment by
        # stdio_client itself, not a replacement — used by tests to launch
        # mcp_server/server.py under a specific MCP_SERVER_ROLE.
        self._params = StdioServerParameters(command=command[0], args=command[1:], env=env)

    async def list_tools(self) -> list[dict[str, Any]]:
        """Tool Discovery (Bab 60.1)."""
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {"name": t.name, "description": t.description, "input_schema": t.inputSchema}
                    for t in result.tools
                ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute one discovered tool and return a normalized result."""
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                return _normalize_result(result)
