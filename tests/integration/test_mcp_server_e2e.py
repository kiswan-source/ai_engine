"""End-to-end test of the MCP Server (Bab 60, Tahap 28) — dogfoods our own
mcp_client.client.MCPClient against our own new mcp_server/server.py,
spawned as a REAL subprocess speaking the real MCP protocol over stdio.
Exact mirror of tests/unit/test_mcp_client.py's pattern against
mcp_client/demo_server.py, except this one proves the *server* side works,
and that RBAC (settings.MCP_SERVER_ROLE) actually gates a real process —
not just the fake-registry unit tests in tests/unit/test_mcp_server.py.

Safe/deterministic in CI (Bab 12.3): the subprocess is our own code, not a
live external service, same reasoning as the existing demo_server.py tests.

Workspace access (Bab 60.1 + 69.5, Tahap 32) needs a real Workspace/
WorkspaceFolder row the SUBPROCESS's own fresh-engine-per-call
(agent/tools/workspace_reader.py::_build_fresh_engine) can see — a
file-backed sqlite (not :memory:) passed via the DATABASE_URL env var,
same reasoning tests/unit/test_workspace_reader.py's sync-wrapper tests
already use for the asyncio.run() plumbing.
"""
import os
import sys
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import Workspace, WorkspaceFolder
from mcp_client.client import MCPClient

_SERVER_CMD = [sys.executable, "-m", "mcp_server.server"]
_WRITTEN_FILE = os.path.expanduser("~/ai_engine/reports/mcp_server_e2e_test.txt")


def _client(role: str) -> MCPClient:
    return MCPClient(_SERVER_CMD, env={"MCP_SERVER_ROLE": role})


def _workspace_client(workspace_id: str, workspace_role: str, database_url: str) -> MCPClient:
    return MCPClient(
        _SERVER_CMD,
        env={
            "MCP_SERVER_ROLE": "user",
            "MCP_SERVER_WORKSPACE_ID": workspace_id,
            "MCP_SERVER_WORKSPACE_ROLE": workspace_role,
            "DATABASE_URL": database_url,
        },
    )


async def _setup_workspace_sqlite_file(tmp_path, folder_path):
    """Mirrors test_workspace_reader.py's _setup_sqlite_file — a file-backed
    sqlite DB so a separate subprocess's own fresh engine can see the seed
    data (:memory: would not survive across processes at all). Async here
    (unlike that helper) because these e2e tests are already inside an
    event loop — asyncio.run() can't nest inside one."""
    db_path = tmp_path / "test.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Workspace.metadata.create_all, tables=[Workspace.__table__, WorkspaceFolder.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        ws = Workspace(project_id=f"p-{uuid.uuid4().hex}", status="Active")
        session.add(ws)
        await session.flush()
        folder = WorkspaceFolder(workspace_id=ws.id, source_type="Local", path=str(folder_path))
        session.add(folder)
        await session.commit()
        ids = (ws.id, folder.id)
    await engine.dispose()
    return database_url, ids


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


# ─── Workspace access via MCP Server (Bab 60.1 + 69.5, Tahap 32) ────────

async def test_list_tools_includes_workspace_tools_when_configured(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    database_url, (workspace_id, _) = await _setup_workspace_sqlite_file(tmp_path, content_dir)

    client = _workspace_client(workspace_id, "viewer", database_url)
    tools = await client.list_tools()
    names = {t["name"] for t in tools}
    assert "workspace_list_files" in names
    assert "workspace_read_file" in names
    assert "workspace_write_file" in names


async def test_editor_role_writes_a_real_file_into_the_real_workspace_folder(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    database_url, (workspace_id, folder_id) = await _setup_workspace_sqlite_file(tmp_path, content_dir)

    client = _workspace_client(workspace_id, "editor", database_url)
    result = await client.call_tool(
        "workspace_write_file",
        {"folder_id": folder_id, "relative_path": "catatan.txt", "content": "ditulis via MCP"},
    )
    assert result["success"] is True
    assert (content_dir / "catatan.txt").read_text() == "ditulis via MCP"


async def test_viewer_role_can_read_but_not_write_real_workspace(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "seed.txt").write_text("isi seed")
    database_url, (workspace_id, folder_id) = await _setup_workspace_sqlite_file(tmp_path, content_dir)

    reader = _workspace_client(workspace_id, "viewer", database_url)
    read_result = await reader.call_tool("workspace_read_file", {"folder_id": folder_id, "relative_path": "seed.txt"})
    assert read_result["success"] is True
    assert "isi seed" in read_result["text"]

    writer = _workspace_client(workspace_id, "viewer", database_url)
    write_result = await writer.call_tool(
        "workspace_write_file", {"folder_id": folder_id, "relative_path": "seed.txt", "content": "harusnya ditolak"}
    )
    assert write_result["success"] is False
    assert (content_dir / "seed.txt").read_text() == "isi seed"


async def test_workspace_write_ignores_client_supplied_workspace_id(tmp_path):
    """The security boundary (Tahap 32 design decision 4): whatever
    workspace_id the caller/model argues, the server's own configured one
    always wins."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    database_url, (workspace_id, folder_id) = await _setup_workspace_sqlite_file(tmp_path, content_dir)

    client = _workspace_client(workspace_id, "editor", database_url)
    result = await client.call_tool(
        "workspace_write_file",
        {
            "folder_id": folder_id, "relative_path": "catatan.txt", "content": "isi",
            "workspace_id": "fake-hallucinated-id",
        },
    )
    assert result["success"] is True
    assert (content_dir / "catatan.txt").exists()
