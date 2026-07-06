"""Integration test for Agent Workspace Context over HTTP (Bab 69.5, Tahap 23)
— the real route (`api/routes/chat.py`) -> real `ToolRegistry` (NOT the
fake-registry trick other chat tests use — the whole point here is
exercising the real `workspace_list_files`/`workspace_read_file` tools) ->
real DB-backed `agent/tools/workspace_reader.py` -> real
`tools/adapters/filesystem.py` reading a real file on disk.

A file-backed sqlite DB (not `:memory:`), not the in-memory pattern most
other integration tests use: the real `workspace_list_files`/
`workspace_read_file` are sync wrappers that call `asyncio.run(...)`
internally, invoked via `ChatEngine._run_tool`'s `asyncio.to_thread(...)` —
a genuinely different OS thread with its own fresh event loop. An
in-memory sqlite DB's connection is tied to the loop that opened it and
can't be reused from that new loop; a real file has no such attachment
(same reasoning as `tests/unit/test_workspace_reader.py`'s sync-wrapper
tests).

Two separate things must point at this same test database —
`db.connection.get_session` (FastAPI dependency, for the Project/Workspace
CRUD routes used to set up fixtures, and reused by
`api/routes/chat.py::_check_workspace_access`'s deferred import of
`db.connection.AsyncSessionFactory` — both run on the main test loop, so
sharing the global factory is fine there) and `api.config.settings.DATABASE_URL`
(read by `workspace_list_files`/`workspace_read_file`'s sync wrappers to
build a *fresh* engine inside their own `asyncio.run()` — a different loop
that can't reuse the global factory's engine at all, caught live against
real Postgres; see `agent/tools/workspace_reader.py`'s module docstring).
"""
import json

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.connection import get_session
from db.models import Project, ProjectMember, Workspace, WorkspaceFolder


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "ownerkey:user,strangerkey:user")


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def sqlite_session_factory(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(
            Project.metadata.create_all,
            tables=[Project.__table__, ProjectMember.__table__, Workspace.__table__, WorkspaceFolder.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # _check_workspace_access (api/routes/chat.py) runs on the main test
    # loop, so reusing the global factory is fine there. The real
    # workspace_list_files/workspace_read_file sync wrappers build a
    # *fresh* engine from settings.DATABASE_URL inside their own
    # asyncio.run() (a different loop) — patching DATABASE_URL to this same
    # file lets that fresh engine see the same data (see
    # workspace_reader.py's module docstring for why the global factory
    # itself can't cross into that loop).
    monkeypatch.setattr("db.connection.AsyncSessionFactory", factory)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    yield factory
    await engine.dispose()


@pytest.fixture
async def client(app, sqlite_session_factory):
    async def _override_get_session():
        async with sqlite_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _as(key: str) -> dict:
    return {"X-API-Key": key}


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCM:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return _FakeStreamResponse(self._lines)

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    rounds: list[list[str]] = []

    def __init__(self, *args, **kwargs):
        self._round_index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None):
        idx = min(self._round_index, len(self.rounds) - 1)
        self._round_index += 1
        return _FakeStreamCM(self.rounds[idx])


def _tool_call_round(tool_name: str, arguments: dict) -> str:
    return json.dumps(
        {"message": {"content": "", "tool_calls": [{"function": {"name": tool_name, "arguments": arguments}}]}, "done": True}
    )


def _final_round(text: str = "Selesai.") -> str:
    return json.dumps({"message": {"content": text}, "done": True})


def _sse_events(response_text: str) -> list[dict]:
    return [json.loads(line[len("data: "):]) for line in response_text.splitlines() if line.startswith("data: ")]


async def _create_project_and_workspace(client, content_dir) -> tuple[str, str, str]:
    """Returns (project_id, workspace_id, folder_id) — real rows via real routes."""
    project_res = await client.post("/api/v1/projects", json={"name": "Studi Lapangan"}, headers=_as("ownerkey"))
    project_id = project_res.json()["id"]

    ws_res = await client.post("/api/v1/workspace", json={"project_id": project_id}, headers=_as("ownerkey"))
    workspace_id = ws_res.json()["id"]

    mount_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(content_dir), "source_type": "Local", "alias": "Lapangan"},
        headers=_as("ownerkey"),
    )
    folder_id = mount_res.json()["id"]
    return project_id, workspace_id, folder_id


async def test_chat_reads_real_workspace_file_and_ignores_model_supplied_workspace_id(
    client, tmp_path, monkeypatch
):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "assay.txt").write_text("kadar emas anomali distrik alpha ditemukan di titik bor 12")

    _, workspace_id, folder_id = await _create_project_and_workspace(client, content_dir)

    rounds = [
        [_tool_call_round("workspace_list_files", {})],
        # Deliberately wrong workspace_id — must be overridden, not trusted.
        [_tool_call_round("workspace_read_file", {"folder_id": folder_id, "relative_path": "assay.txt", "workspace_id": "bogus-id"})],
        [_final_round("Sudah saya baca isinya.")],
    ]

    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    res = await client.post(
        "/api/v1/chat/stream",
        json={"message": "lihat isi workspace lalu baca assay.txt", "workspace_id": workspace_id},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 200
    events = _sse_events(res.text)

    tool_results = [e for e in events if e.get("type") == "tool_result"]
    assert len(tool_results) == 2
    assert tool_results[0]["ok"] is True  # workspace_list_files
    assert tool_results[1]["ok"] is True  # workspace_read_file, despite the bogus workspace_id in args
    assert "kadar emas anomali distrik alpha" in tool_results[1]["summary"]


async def test_non_member_denied_before_streaming_starts(client, tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()

    _, workspace_id, _ = await _create_project_and_workspace(client, content_dir)

    res = await client.post(
        "/api/v1/chat/stream",
        json={"message": "halo", "workspace_id": workspace_id},
        headers=_as("strangerkey"),
    )
    assert res.status_code == 403
