"""Integration tests for the Workspace Slice 2 (Fase 12) delete-request /
delete-confirm endpoints — same in-memory SQLite pattern as
test_workspace_versioning_api.py, whose _make_workspace_with_folder helper
this file reuses the shape of."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.connection import get_session
from db.models import Project, ProjectMember, Workspace, WorkspaceFileVersion, WorkspaceFolder
from workspace.delete_gate import WorkspaceDeleteGate


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


async def _add_member(client, project_id, principal_key, role, owner="ownerkey"):
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": principal_key, "role": role},
        headers=_as(owner),
    )


# ─── happy path ─────────────────────────────────────────────────────────

async def test_request_then_confirm_deletes_the_file(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi lama")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    req_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )
    assert req_res.status_code == 200, req_res.text
    body = req_res.json()
    assert body["relative_path"] == "a.txt"
    assert body["size_bytes"] == len(b"isi lama")
    token = body["token"]
    assert (tmp_path / "a.txt").exists()  # step 1 touches nothing on disk

    confirm_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": token, "reason": "tidak dipakai lagi"}, headers=_as("ownerkey"),
    )
    assert confirm_res.status_code == 200, confirm_res.text
    assert confirm_res.json()["deleted"] is True
    assert not (tmp_path / "a.txt").exists()


async def test_confirmed_delete_is_recoverable_via_existing_restore_endpoint(client, tmp_path):
    """Owner's explicit design choice: snapshot-before-delete, so a
    confirmed delete is closer to a soft delete than a true unrecoverable
    one — reusing the exact restore mechanism Fase 4 already built."""
    (tmp_path / "a.txt").write_text("isi yang mau dihapus")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    req_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )
    token = req_res.json()["token"]
    await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": token}, headers=_as("ownerkey"),
    )
    assert not (tmp_path / "a.txt").exists()

    versions_res = await client.get(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/versions", params={"path": "a.txt"},
        headers=_as("ownerkey"),
    )
    versions = versions_res.json()["versions"]
    assert len(versions) == 1

    restore_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/restore",
        json={"relative_path": "a.txt", "version_id": versions[0]["id"]},
        headers=_as("ownerkey"),
    )
    assert restore_res.status_code == 200, restore_res.text
    assert (tmp_path / "a.txt").read_text() == "isi yang mau dihapus"


# ─── permission (delete_output is owner-only) ──────────────────────────

async def test_editor_cannot_request_delete(client, tmp_path):
    """Editor has write_output but not delete_output — the one Workspace
    mutation classified HUMAN-ONLY gets the narrowest permission tier."""
    (tmp_path / "a.txt").write_text("isi")
    project_id, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)
    await _add_member(client, project_id, "editorkey", "editor")

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("editorkey"),
    )
    assert res.status_code == 403
    assert (tmp_path / "a.txt").exists()


async def test_viewer_cannot_request_delete(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    project_id, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)
    await _add_member(client, project_id, "viewerkey", "viewer")

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("viewerkey"),
    )
    assert res.status_code == 403


async def test_stranger_cannot_request_or_confirm_delete(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("strangerkey"),
    )
    assert res.status_code == 403

    confirm_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": "whatever"}, headers=_as("strangerkey"),
    )
    assert confirm_res.status_code == 403


async def test_confirm_also_re_checks_permission_not_just_the_token(client, tmp_path):
    """A token alone is never sufficient authorization — even a genuine
    token, if somehow presented by a non-owner caller, must still be
    rejected (defense in depth, same posture every other mutating route
    in this file already has)."""
    (tmp_path / "a.txt").write_text("isi")
    project_id, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)
    await _add_member(client, project_id, "editorkey", "editor")

    req_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )
    token = req_res.json()["token"]

    confirm_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": token}, headers=_as("editorkey"),
    )
    assert confirm_res.status_code == 403
    assert (tmp_path / "a.txt").exists()


# ─── validation / edge cases ────────────────────────────────────────────

async def test_request_delete_of_missing_file_404s(client, tmp_path):
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "does-not-exist.txt"}, headers=_as("ownerkey"),
    )
    assert res.status_code == 404


async def test_request_delete_of_directory_rejected(client, tmp_path):
    (tmp_path / "subdir").mkdir()
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "subdir"}, headers=_as("ownerkey"),
    )
    assert res.status_code == 400
    assert (tmp_path / "subdir").exists()


async def test_confirm_unknown_token_404s(client, tmp_path):
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": "does-not-exist"}, headers=_as("ownerkey"),
    )
    assert res.status_code == 404


async def test_confirm_twice_second_call_conflicts(client, tmp_path):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    req_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )
    token = req_res.json()["token"]
    first = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": token}, headers=_as("ownerkey"),
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": token}, headers=_as("ownerkey"),
    )
    assert second.status_code == 409


async def test_confirm_token_scoped_to_its_own_workspace_and_folder(client, tmp_path, tmp_path_factory):
    """A token issued for one (workspace_id, folder_id, relative_path) must
    not be usable against a different Workspace/folder, even one the same
    caller legitimately owns — prevents a leaked/misdirected token being
    replayed somewhere it wasn't meant for."""
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    other_root = tmp_path_factory.mktemp("other")
    _, other_workspace_id, other_folder_id = await _make_workspace_with_folder(client, other_root)

    req_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )
    token = req_res.json()["token"]

    res = await client.post(
        f"/api/v1/workspace/{other_workspace_id}/files/{other_folder_id}/delete-confirm",
        json={"token": token}, headers=_as("ownerkey"),
    )
    assert res.status_code == 400
    assert (tmp_path / "a.txt").exists()


async def test_confirm_expired_token_410s(client, tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    import workspace.delete_gate as delete_gate_module

    monkeypatch.setattr(delete_gate_module, "_shared_gate", WorkspaceDeleteGate(ttl_seconds=0))

    req_res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )
    token = req_res.json()["token"]

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
        json={"token": token}, headers=_as("ownerkey"),
    )
    assert res.status_code == 410
    assert (tmp_path / "a.txt").exists()


async def test_delete_request_rejects_path_traversal(client, tmp_path):
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "../outside.txt"}, headers=_as("ownerkey"),
    )
    assert res.status_code == 400


async def test_delete_confirm_reuses_the_shared_toctou_lock(client, tmp_path, monkeypatch):
    """Gate 2/3 lesson applied proactively (§7 CLAUDE.md) — delete-confirm
    must serialize through the exact same per-destination lock write/move/
    copy already use. Two separate delete-request calls for the SAME file
    (two different tokens — e.g. two people/tabs both requesting deletion
    of the same file before either confirms) must not both execute their
    snapshot-then-delete critical section at once. Verified by forcing a
    yield point inside the critical section and asserting it's never
    entered twice at once for the same destination — same technique the
    Gate 3 workspace_reader concurrency tests already use."""
    import asyncio

    import workspace.versioning as versioning_module

    (tmp_path / "a.txt").write_text("isi")
    _, workspace_id, folder_id = await _make_workspace_with_folder(client, tmp_path)

    token_a = (await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )).json()["token"]
    token_b = (await client.post(
        f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-request",
        json={"relative_path": "a.txt"}, headers=_as("ownerkey"),
    )).json()["token"]
    assert token_a != token_b

    active = 0
    max_active = 0
    original_save_version = versioning_module.save_version

    async def _tracked_save_version(*args, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        result = await original_save_version(*args, **kwargs)
        active -= 1
        return result

    monkeypatch.setattr("api.routes.workspace.save_version", _tracked_save_version)

    # Whichever token's confirm wins the lock deletes the file; the other
    # then 404s cleanly on its own read_bytes once it gets the lock (the
    # file is already gone) — that's the correct, safe outcome. This test
    # only asserts the two attempts were never BOTH inside the critical
    # section at once.
    results = await asyncio.gather(
        client.post(
            f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
            json={"token": token_a}, headers=_as("ownerkey"),
        ),
        client.post(
            f"/api/v1/workspace/{workspace_id}/files/{folder_id}/delete-confirm",
            json={"token": token_b}, headers=_as("ownerkey"),
        ),
    )

    assert max_active == 1
    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 404]
    assert not (tmp_path / "a.txt").exists()
