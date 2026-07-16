"""Integration tests for the Fase 4 (DCF v5 mandate "Workspace Autonomous
Capability") version-history/restore endpoints — same in-memory SQLite
pattern as test_workspace_api.py."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.tools.workspace_reader import _write_file
from db.connection import get_session
from db.models import Project, ProjectMember, Workspace, WorkspaceFileVersion, WorkspaceFolder


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr(
        "api.config.settings.API_KEYS", "ownerkey:user,editorkey:user,viewerkey:user,strangerkey:user"
    )


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Project.metadata.create_all,
            tables=[
                Project.__table__, ProjectMember.__table__, Workspace.__table__,
                WorkspaceFolder.__table__, WorkspaceFileVersion.__table__,
            ],
        )
    yield async_sessionmaker(engine, expire_on_commit=False)
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


async def _make_workspace_with_folder(client, tmp_path, owner="ownerkey") -> tuple[str, str, str]:
    """Returns (project_id, workspace_id, folder_id)."""
    proj = await client.post("/api/v1/projects", json={"name": "Studi"}, headers=_as(owner))
    project_id = proj.json()["id"]
    ws = await client.post("/api/v1/workspace", json={"project_id": project_id}, headers=_as(owner))
    workspace_id = ws.json()["id"]
    mount = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local", "alias": "Docs"},
        headers=_as(owner),
    )
    folder_id = mount.json()["id"]
    return project_id, workspace_id, folder_id


async def test_versions_empty_for_file_never_overwritten(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 200
    assert res.json()["versions"] == []


async def test_restore_brings_back_overwritten_content(client, sqlite_session_factory, tmp_path):
    (tmp_path / "a.txt").write_text("versi 1")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    # Simulates the chat tool overwriting the file — same underlying
    # function agent/tools/workspace_reader.py::workspace_write_file wraps,
    # called directly against this test's own DB instead of driving a full
    # chat turn just to exercise the versioning/restore endpoints.
    result = await _write_file(
        workspace_id, folder_id, "a.txt", "versi 2", mode="overwrite", actor="ownerkey",
        session_factory=sqlite_session_factory,
    )
    assert result["success"] is True
    assert result["action"] == "overwritten"
    assert (tmp_path / "a.txt").read_text() == "versi 2"

    versions_res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("ownerkey"),
    )
    versions = versions_res.json()["versions"]
    assert len(versions) == 1
    version_id = versions[0]["id"]

    restore_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "a.txt", "version_id": version_id},
        headers=_as("ownerkey"),
    )
    assert restore_res.status_code == 200, restore_res.text
    assert (tmp_path / "a.txt").read_text() == "versi 1"


async def test_restoring_also_snapshots_the_current_content_first(client, sqlite_session_factory, tmp_path):
    """A restore is itself an overwrite — it must be undoable too, not just
    the original write that prompted it."""
    (tmp_path / "a.txt").write_text("versi 1")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    await _write_file(
        workspace_id, folder_id, "a.txt", "versi 2", mode="overwrite", actor="ownerkey",
        session_factory=sqlite_session_factory,
    )
    versions_res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("ownerkey"),
    )
    version_id = versions_res.json()["versions"][0]["id"]

    restore_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "a.txt", "version_id": version_id},
        headers=_as("ownerkey"),
    )
    assert restore_res.status_code == 200

    versions_after = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("ownerkey"),
    )
    assert len(versions_after.json()["versions"]) == 2


async def test_viewer_can_list_versions_but_not_restore(client, tmp_path):
    (tmp_path / "a.txt").write_text("versi 1")
    project_id, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "viewerkey", "role": "viewer"},
        headers=_as("ownerkey"),
    )

    list_res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("viewerkey"),
    )
    assert list_res.status_code == 200  # read access, same as any other Workspace content

    restore_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "a.txt", "version_id": 1},
        headers=_as("viewerkey"),
    )
    assert restore_res.status_code == 403  # viewer lacks write_output


async def test_stranger_cannot_list_or_restore_versions(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    list_res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("strangerkey"),
    )
    assert list_res.status_code == 403

    restore_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "a.txt", "version_id": 1},
        headers=_as("strangerkey"),
    )
    assert restore_res.status_code == 403


async def test_restore_unknown_version_id_404s(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "a.txt", "version_id": 9999},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 404
