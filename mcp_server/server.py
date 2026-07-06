"""MCP Server (MASTER_INSTRUCTION.md Bab 60) — the opposite direction from
mcp_client/: exposes AI_ENGINE's own tool registry to external MCP clients
(e.g. Claude Desktop) over stdio, so this app can be a Bab 60.1 "MCP
Server" and not just a client of others.

Scope decisions (Tahap 28, see docs/PROGRESS.md for the full write-up):
- stdio transport only, matching mcp_client/demo_server.py's precedent —
  a network transport (SSE/HTTP) would need its own auth story and path
  sandboxing review, deliberately deferred as a separate gap.
- Tool set = core.chat.tool_schemas.TOOL_SCHEMAS minus mcp_* (a confusing
  proxy-to-other-MCP-servers pattern with no use case yet) and, unless
  Workspace access is configured (Tahap 32 below), workspace_*.
- RBAC: Bab 60.1 — "MCP tidak memiliki jalur pintas keamanan" — every call
  is gated through security/permissions.py exactly like every other tool
  caller, via the SAME ToolRegistry.execute(role=...) used elsewhere. Since
  stdio has no per-request caller identity, the whole process runs as one
  fixed role for its lifetime: settings.MCP_SERVER_ROLE (default "user",
  the conservative choice — write/convert/generate tools stay denied until
  an operator opts in via the environment that spawns this process).

Workspace access via MCP Server (Tahap 32, Bab 60.1 + 69.5): the
workspace_* tools were excluded entirely in Tahap 28 because there's no
ChatEngine session here to inject an authorized workspace_id from — this
Tahap gives the whole process a config-bound identity instead, the same
idea as MCP_SERVER_ROLE above but for the Project-role-scoped Workspace
Permission system (security/permissions.py::WORKSPACE_PERMISSIONS_BY_PROJECT_ROLE):
`settings.MCP_SERVER_WORKSPACE_ID` (None by default — workspace tools stay
excluded, byte-for-byte Tahap 28's original behavior) and
`settings.MCP_SERVER_WORKSPACE_ROLE` (default "viewer", the conservative
choice — read works, write_output doesn't until explicitly configured).
There is no MCP caller identity to look up a real ProjectMember for —
whoever configures this process's environment IS the identity, same trust
model already accepted for MCP_SERVER_ROLE. workspace_id is force-injected
into every workspace tool call from this config, never trusted from the
client/model — the same "never trust the caller" boundary
core/chat/engine.py::_run_tool's WORKSPACE_TOOL_NAMES block already
established for Chat (Tahap 23).

Run standalone: `python -m mcp_server.server` (stdio transport).
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any, Optional

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from agent.tools.registry import ToolRegistry, build_registry
from api.config import settings
from core.chat.tool_schemas import TOOL_SCHEMAS
from security.permissions import require_workspace_permission

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

# Meta-proxy (Tahap 17) tools that don't make sense called directly — see
# module docstring. Always excluded, regardless of Workspace config.
_EXCLUDED_TOOLS = {"mcp_list_tools", "mcp_call_tool"}
# Session-bound in Chat (Tahap 23/29/30) — here, "session" is this whole
# process's config instead (Tahap 32). Excluded unless Workspace access is
# configured; see dispatch_tool_call for the workspace_id injection.
_WORKSPACE_TOOL_NAMES = {"workspace_list_files", "workspace_read_file", "workspace_write_file"}


def _allowed_schemas(include_workspace: bool = False) -> list[dict]:
    excluded = _EXCLUDED_TOOLS if include_workspace else _EXCLUDED_TOOLS | _WORKSPACE_TOOL_NAMES
    return [s for s in TOOL_SCHEMAS if s["function"]["name"] not in excluded]


async def dispatch_tool_call(
    registry: ToolRegistry, role: str, name: str, arguments: dict,
    workspace_id: Optional[str] = None, workspace_role: Optional[str] = None,
) -> dict[str, Any]:
    """The actual call_tool logic, pulled out of the Server decorator wiring
    below so it's directly unit-testable without constructing MCP protocol
    request/result objects."""
    allowed_names = {s["function"]["name"] for s in _allowed_schemas(include_workspace=bool(workspace_id))}
    if name not in allowed_names:
        raise ValueError(f"Tool '{name}' not exposed via MCP Server. Available: {sorted(allowed_names)}")
    arguments = dict(arguments or {})
    if name in _WORKSPACE_TOOL_NAMES:
        # Never trust a client/model-supplied workspace_id (same boundary
        # Tahap 23 established for Chat) — force this process's configured
        # Workspace regardless of what the tool call argues.
        arguments["workspace_id"] = workspace_id
        if name == "workspace_write_file":
            # Let PermissionError propagate un-caught — the MCP SDK's own
            # call_tool() wrapper already converts any raised exception
            # into a clean error result (same as the ValueError above).
            require_workspace_permission(workspace_role, "write_output")
    # Registry tools are sync — same off-thread pattern
    # core/chat/engine.py::ChatEngine._run_tool already uses.
    return await asyncio.to_thread(registry.execute, name, arguments or None, role)


def build_server(
    registry: ToolRegistry, role: str,
    workspace_id: Optional[str] = None, workspace_role: Optional[str] = None,
) -> Server:
    """Build the MCP Server object wired to `registry`, gated as `role`
    (and, if `workspace_id` is set, `workspace_role` for Workspace tools).

    Low-level `mcp.server.Server` API (not `FastMCP`'s decorator style,
    which needs fixed Python function signatures) because the tool set here
    is dynamic — driven by TOOL_SCHEMAS + the registry, the same way
    core/chat/engine.py's tool-calling loop already is.
    """
    server = Server("ai-engine")
    schemas = _allowed_schemas(include_workspace=bool(workspace_id))

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
        return await dispatch_tool_call(registry, role, name, arguments, workspace_id, workspace_role)

    return server


async def _run() -> None:
    if not settings.ENABLE_MCP:
        logger.warning("MCP Server not started: ENABLE_MCP is false")
        return
    workspace_id = settings.MCP_SERVER_WORKSPACE_ID
    workspace_role = settings.MCP_SERVER_WORKSPACE_ROLE if workspace_id else None
    if workspace_id:
        # Pure in-memory check (no DB round-trip) — fail fast on a
        # misconfigured role string before ever touching stdio. Whether
        # `workspace_id` itself actually exists is checked lazily, at the
        # first real tool call, same as Chat already does.
        try:
            require_workspace_permission(workspace_role, "read")
        except PermissionError as e:
            logger.error("MCP Server not started: invalid MCP_SERVER_WORKSPACE_ROLE: %s", e)
            return
    registry = build_registry(settings.OLLAMA_BASE_URL, settings.GEMMA_MODEL)
    server = build_server(registry, settings.MCP_SERVER_ROLE, workspace_id, workspace_role)
    logger.info(
        "MCP Server starting role=%s workspace=%s tools=%d",
        settings.MCP_SERVER_ROLE, workspace_id or "none",
        len(_allowed_schemas(include_workspace=bool(workspace_id))),
    )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
