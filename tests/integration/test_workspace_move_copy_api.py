"""Integration tests for the Fase 13 (Workspace Manager UI — sidebar tree,
context menu, drag & drop) move/copy HTTP endpoints — same in-memory SQLite
pattern as test_workspace_versioning_api.py.

Gate 1 decision (Owner): these routes mirror the existing chat-tool security
model exactly (same `_move_or_copy`, same `write_output` permission, same
TOCTOU lock, same version-snapshot-before-overwrite) rather than a new tier —
these tests assert that mirroring actually holds, not just that the routes
respond.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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


async def test_move_renames_file_in_place(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"success": True, "src": "a.txt", "dst": "b.txt"}
    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_text() == "isi"


async def test_copy_leaves_source_in_place(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/copy",
        json={"src_relative_path": "a.txt", "dst_relative_path": "sub/b.txt"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 200, res.text
    assert (tmp_path / "a.txt").read_text() == "isi"
    assert (tmp_path / "sub" / "b.txt").read_text() == "isi"


async def test_copy_folder_into_own_subdirectory_is_rejected(client, tmp_path):
    """Gate 3 finding (2026-08-01) at the HTTP layer — this is the exact
    request shape the new context-menu Copy prompt makes trivially
    reachable: copying a folder into one of its own subdirectories used to
    make shutil.copytree recurse into the destination it was still
    creating, with no cleanup on the resulting failure."""
    (tmp_path / "projectA" / "archive").mkdir(parents=True)
    (tmp_path / "projectA" / "file.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/copy",
        json={"src_relative_path": "projectA", "dst_relative_path": "projectA/archive/backup"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 400
    assert not (tmp_path / "projectA" / "archive" / "backup").exists()


async def test_move_onto_existing_destination_requires_overwrite(client, tmp_path):
    (tmp_path / "a.txt").write_text("source")
    (tmp_path / "b.txt").write_text("target")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    denied = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt"},
        headers=_as("ownerkey"),
    )
    assert denied.status_code == 400
    assert (tmp_path / "a.txt").exists()  # untouched

    allowed = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt", "overwrite": True},
        headers=_as("ownerkey"),
    )
    assert allowed.status_code == 200, allowed.text
    assert (tmp_path / "b.txt").read_text() == "source"


async def test_overwriting_move_snapshots_previous_content_first(client, tmp_path):
    """Same guarantee as `workspace_move_file` (chat tool) — an overwritten
    destination is recoverable via the existing restore endpoint, not a
    silent clobber."""
    (tmp_path / "a.txt").write_text("source")
    (tmp_path / "b.txt").write_text("target-to-be-lost")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt", "overwrite": True},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 200, res.text

    versions_res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "b.txt"},
        headers=_as("ownerkey"),
    )
    versions = versions_res.json()["versions"]
    assert len(versions) == 1

    restore_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "b.txt", "version_id": versions[0]["id"]},
        headers=_as("ownerkey"),
    )
    assert restore_res.status_code == 200, restore_res.text
    assert (tmp_path / "b.txt").read_text() == "target-to-be-lost"


async def test_move_missing_source_400s(client, tmp_path):
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "nope.txt", "dst_relative_path": "b.txt"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 400


async def test_move_path_escaping_root_400s(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "../../etc/evil.txt"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 400
    assert (tmp_path / "a.txt").exists()  # untouched, never escaped the root


async def test_editor_can_move_viewer_cannot(client, tmp_path):
    """Mirrors write_output's existing owner+editor tier — the same
    permission the chat-tool move/copy path already gates on."""
    (tmp_path / "a.txt").write_text("isi")
    project_id, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "editorkey", "role": "editor"},
        headers=_as("ownerkey"),
    )
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "viewerkey", "role": "viewer"},
        headers=_as("ownerkey"),
    )

    viewer_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt"},
        headers=_as("viewerkey"),
    )
    assert viewer_res.status_code == 403
    assert (tmp_path / "a.txt").exists()

    editor_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt"},
        headers=_as("editorkey"),
    )
    assert editor_res.status_code == 200, editor_res.text


async def test_stranger_cannot_move_or_copy(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    move_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/move",
        json={"src_relative_path": "a.txt", "dst_relative_path": "b.txt"},
        headers=_as("strangerkey"),
    )
    assert move_res.status_code == 403

    copy_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/copy",
        json={"src_relative_path": "a.txt", "dst_relative_path": "c.txt"},
        headers=_as("strangerkey"),
    )
    assert copy_res.status_code == 403
    assert (tmp_path / "a.txt").exists()
