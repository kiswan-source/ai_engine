"""MCP Server (MASTER_INSTRUCTION.md Bab 60) — the opposite direction from
mcp_client/: exposes AI_ENGINE's own tool registry to external MCP clients
(e.g. Claude Desktop) over stdio, so this app can be a Bab 60.1 "MCP
Server" and not just a client of others.

Scope decisions (Tahap 28, see docs/PROGRESS.md for the full write-up):
- stdio transport only, matching mcp_client/demo_server.py's precedent —
  a network transport (SSE/HTTP) would need its own auth story and path
  sandboxing review, deliberately deferred as a separate gap.
- Tool set = core.chat.tool_schemas.TOOL_SCHEMAS minus workspace_* (their
  real security boundary is ChatEngine session injection, Tahap 23 — there
  is no session here to inject from) and mcp_* (a confusing proxy-to-other-
  MCP-servers pattern with no use case yet).
- RBAC: Bab 60.1 — "MCP tidak memiliki jalur pintas keamanan" — every call
  is gated through security/permissions.py exactly like every other tool
  caller, via the SAME ToolRegistry.execute(role=...) used elsewhere. Since
  stdio has no per-request caller identity, the whole process runs as one
  fixed role for its lifetime: settings.MCP_SERVER_ROLE (default "user",
  the conservative choice — write/convert/generate tools stay denied until
  an operator opts in via the environment that spawns this process).

Run standalone: `python -m mcp_server.server` (stdio transport).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from agent.tools.registry import ToolRegistry, build_registry
from api.config import settings
from core.chat.tool_schemas import TOOL_SCHEMAS

# NOT core.utils.logger.get_logger() — its structlog setup uses
# PrintLoggerFactory(), which writes to stdout. On stdio transport, stdout
# is the JSON-RPC channel itself; anything else written there corrupts the
# protocol stream (confirmed live: an MCP client failed to parse frames
# with a real client once this module logged through the shared logger).
# stderr is the correct channel — stdio_client() on the client side already
# captures a spawned server's stderr separately for exactly this reason.
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))
logger.setLevel(logging.INFO)

# Session-bound (Tahap 23) or meta-proxy (Tahap 17) tools that don't make
# sense called directly, outside their normal caller — see module docstring.
_EXCLUDED_TOOLS = {"workspace_list_files", "workspace_read_file", "mcp_list_tools", "mcp_call_tool"}


def _allowed_schemas() -> list[dict]:
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] not in _EXCLUDED_TOOLS]


async def dispatch_tool_call(registry: ToolRegistry, role: str, name: str, arguments: dict) -> dict[str, Any]:
    """The actual call_tool logic, pulled out of the Server decorator wiring
    below so it's directly unit-testable without constructing MCP protocol
    request/result objects."""
    allowed_names = {s["function"]["name"] for s in _allowed_schemas()}
    if name not in allowed_names:
        raise ValueError(f"Tool '{name}' not exposed via MCP Server. Available: {sorted(allowed_names)}")
    # Registry tools are sync — same off-thread pattern
    # core/chat/engine.py::ChatEngine._run_tool already uses.
    return await asyncio.to_thread(registry.execute, name, arguments or None, role)


def build_server(registry: ToolRegistry, role: str) -> Server:
    """Build the MCP Server object wired to `registry`, gated as `role`.

    Low-level `mcp.server.Server` API (not `FastMCP`'s decorator style,
    which needs fixed Python function signatures) because the tool set here
    is dynamic — driven by TOOL_SCHEMAS + the registry, the same way
    core/chat/engine.py's tool-calling loop already is.
    """
    server = Server("ai-engine")
    schemas = _allowed_schemas()

    @server.list_tools()
    async def handle_list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=s["function"]["name"],
                description=s["function"]["description"],
                inputSchema=s["function"]["parameters"],
            )
            for s in schemas
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict) -> dict[str, Any]:
        return await dispatch_tool_call(registry, role, name, arguments)

    return server


async def _run() -> None:
    if not settings.ENABLE_MCP:
        logger.warning("MCP Server not started: ENABLE_MCP is false")
        return
    registry = build_registry(settings.OLLAMA_BASE_URL, settings.GEMMA_MODEL)
    server = build_server(registry, settings.MCP_SERVER_ROLE)
    logger.info("MCP Server starting role=%s tools=%d", settings.MCP_SERVER_ROLE, len(_allowed_schemas()))
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
