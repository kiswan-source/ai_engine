"""Minimal MCP server used ONLY to prove the MCP Client (Bab 60) works
end-to-end against the real protocol — this is a dev/test fixture, not a
shipped AI_ENGINE capability. Real usage points `MCP_SERVERS` (see
`mcp_client/config.py`) at a genuine third-party MCP server; this script
stands in for one so the client can be exercised without depending on an
external service that isn't ours to rely on in tests or demos.

Run standalone: `python -m mcp_client.demo_server` (stdio transport).
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-engine-demo")


@mcp.tool()
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@mcp.tool()
def reverse_text(text: str) -> str:
    """Reverse a string."""
    return text[::-1]


if __name__ == "__main__":
    mcp.run(transport="stdio")
