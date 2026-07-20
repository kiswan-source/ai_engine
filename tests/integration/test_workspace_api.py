"""Integration tests for /api/v1/workspace/* (Bab 69.13, ADR-0005, Tahap 19).

Same in-memory SQLite pattern as tests/integration/test_projects_api.py
(Project/ProjectMember/Workspace/WorkspaceFolder tables only — VectorEmbedding's
pgvector column would fail create_all() on SQLite).

``/index`` reuses `api.routes.knowledge`'s `_retriever` singleton directly
(`api/routes/workspace.py` module docstring) rather than building a fresh
one — this makes indexed content actually show up in
`GET /api/v1/knowledge/search`, matching production behavior with any
backend. But it also means `api.routes.workspace._knowledge_retriever` is a
*name binding* captured at import time (`from api.routes.knowledge import
_retriever as _knowledge_retriever`) — monkeypatching
`api.routes.knowledge._retriever` alone does NOT change what
`api.routes.workspace` already imported, same pitfall
`test_knowledge_api.py`'s docstring describes for the module-level-singleton-
built-at-import problem, one level further removed. Both bindings must be
patched to the *same* isolated `Retriever` instance for a test that indexes
via one route and searches via the other.
"""
import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.connection import get_session
from db.models import Project, ProjectMember, Workspace, WorkspaceFolder
from rag.embeddings import hashed_bow_embedder
from rag.knowledge_store import InMemoryKnowledgeStore
from rag.retriever import Retriever


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr(
        "api.config.settings.API_KEYS", "ownerkey:user,editorkey:user,viewerkey:user,strangerkey:user"
    )


@pytest.fixture(autouse=True)
def _hermetic_rag(monkeypatch):
    import api.routes.knowledge as knowledge_route
    import api.routes.workspace as workspace_route

    isolated = Retriever(namespace=knowledge_route.RAG_NAMESPACE, store=InMemoryKnowledgeStore(), embedder=hashed_bow_embedder)
    monkeypatch.setattr(knowledge_route, "_retriever", isolated)
    monkeypatch.setattr(workspace_route, "_knowledge_retriever", isolated)


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
            tables=[Project.__table__, ProjectMember.__table__, Workspace.__table__, WorkspaceFolder.__table__],
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


async def _make_project(client, owner="ownerkey") -> str:
    res = await client.post("/api/v1/projects", json={"name": "Studi Kelayakan"}, headers=_as(owner))
    return res.json()["id"]


async def _make_workspace(client, project_id: str, owner="ownerkey") -> str:
    res = await client.post("/api/v1/workspace", json={"project_id": project_id}, headers=_as(owner))
    assert res.status_code == 200, res.text
    return res.json()["id"]


# ─── create / get ───────────────────────────────────────────────────────

async def test_create_and_get_workspace(client):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.get(f"/api/v1/workspace?project_id={project_id}", headers=_as("ownerkey"))
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == workspace_id
    assert body["status"] == "Active"
    assert body["folders"] == []


async def test_create_workspace_twice_for_same_project_conflicts(client):
    project_id = await _make_project(client)
    await _make_workspace(client, project_id)

    res = await client.post("/api/v1/workspace", json={"project_id": project_id}, headers=_as("ownerkey"))
    assert res.status_code == 409


async def test_create_workspace_requires_project_membership(client):
    project_id = await _make_project(client)

    res = await client.post("/api/v1/workspace", json={"project_id": project_id}, headers=_as("strangerkey"))
    assert res.status_code == 403


async def test_viewer_can_read_but_not_create_workspace(client):
    project_id = await _make_project(client)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "viewerkey", "role": "viewer"},
        headers=_as("ownerkey"),
    )
    workspace_id = await _make_workspace(client, project_id)

    get_res = await client.get(f"/api/v1/workspace?project_id={project_id}", headers=_as("viewerkey"))
    assert get_res.status_code == 200

    patch_res = await client.patch(
        f"/api/v1/workspace/{workspace_id}", json={"root_path": "/tmp/whatever"}, headers=_as("viewerkey")
    )
    assert patch_res.status_code == 403


async def test_get_workspace_unknown_project_404(client):
    res = await client.get("/api/v1/workspace?project_id=does-not-exist", headers=_as("ownerkey"))
    assert res.status_code == 404


# ─── mount ──────────────────────────────────────────────────────────────

async def test_mount_local_folder_succeeds(client, tmp_path):
    (tmp_path / "report.txt").write_text("mining feasibility study")
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local", "alias": "Docs"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["path"] == str(tmp_path)
    assert body["alias"] == "Docs"

    ws_res = await client.get(f"/api/v1/workspace?project_id={project_id}", headers=_as("ownerkey"))
    assert ws_res.json()["root_path"] == str(tmp_path)


async def test_mount_nonexistent_path_rejected(client):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": "/no/such/directory/anywhere", "source_type": "Local"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 400


async def test_mount_non_local_source_type_rejected_as_roadmap(client, tmp_path):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Network"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 400
    assert "roadmap" in res.json()["detail"].lower()


async def test_mount_unknown_source_type_rejected(client, tmp_path):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Teleport"},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 400


async def test_viewer_cannot_mount(client, tmp_path):
    project_id = await _make_project(client)
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "viewerkey", "role": "viewer"},
        headers=_as("ownerkey"),
    )
    workspace_id = await _make_workspace(client, project_id)

    res = await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local"},
        headers=_as("viewerkey"),
    )
    assert res.status_code == 403


# ─── scan ───────────────────────────────────────────────────────────────

async def test_scan_reports_correct_counts(client, tmp_path):
    (tmp_path / "report.txt").write_text("mining feasibility study")
    (tmp_path / "site.png").write_bytes(b"\x89PNG-fake")
    (tmp_path / "boundary.geojson").write_text("{}")
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)
    await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local"},
        headers=_as("ownerkey"),
    )

    res = await client.post(f"/api/v1/workspace/{workspace_id}/scan", headers=_as("ownerkey"))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "Active"
    assert body["document_count"] == 1
    assert body["image_count"] == 1
    assert body["gis_count"] == 1
    assert body["last_scan_at"] is not None


async def test_scan_does_not_block_the_event_loop(client, tmp_path, monkeypatch):
    """Gate 3 (AEGIS audit) fix: scan_workspace used to call scan_folders
    synchronously — a real recursive os.walk here would freeze every other
    API caller for the duration. quick_connect was already fixed with
    asyncio.to_thread; this proves scan_workspace now has the same
    protection by making scan_folders itself block for a while and
    asserting a concurrent, unrelated request still completes well before
    the scan does (if scan_folders ran on the event loop, it would starve
    the concurrent request instead)."""
    import api.routes.workspace as workspace_route
    from workspace.scanner import WorkspaceScanSummary

    def _slow_scan_folders(*args, **kwargs):
        time.sleep(0.3)
        return WorkspaceScanSummary()

    monkeypatch.setattr(workspace_route, "scan_folders", _slow_scan_folders)

    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)
    await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local"},
        headers=_as("ownerkey"),
    )

    concurrent_done_at = None

    async def _concurrent_request():
        nonlocal concurrent_done_at
        await asyncio.sleep(0.05)  # let the scan start first
        await client.get("/health/")
        concurrent_done_at = time.monotonic()

    scan_started_at = time.monotonic()
    _, scan_res = await asyncio.gather(
        _concurrent_request(),
        client.post(f"/api/v1/workspace/{workspace_id}/scan", headers=_as("ownerkey")),
    )

    assert scan_res.status_code == 200
    assert concurrent_done_at is not None
    # The concurrent /health call must finish well before the 0.3s blocking
    # scan does — if scan_folders ran on the event loop instead of a
    # thread, /health would be stuck behind it for the full 0.3s too.
    assert concurrent_done_at - scan_started_at < 0.25


# ─── index + files + tree + status ─────────────────────────────────────

async def test_index_makes_content_searchable_via_knowledge_api(client, tmp_path):
    unique_phrase = "kadar emas anomali distrik alpha"
    (tmp_path / "assay.txt").write_text(f"Laporan lapangan: {unique_phrase} ditemukan di titik bor 12.")
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)
    await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local"},
        headers=_as("ownerkey"),
    )

    index_res = await client.post(f"/api/v1/workspace/{workspace_id}/index", headers=_as("ownerkey"))
    assert index_res.status_code == 200
    assert index_res.json()["chunks_indexed"] >= 1
    assert index_res.json()["status"] == "Active"

    search_res = await client.get(
        "/api/v1/knowledge/search", params={"q": unique_phrase}, headers=_as("ownerkey")
    )
    assert search_res.status_code == 200
    hits = search_res.json()["hits"]
    assert any(unique_phrase in h["text"] for h in hits)
    assert any(h["metadata"].get("source") == "workspace" for h in hits)
    assert any(h["metadata"].get("workspace_id") == workspace_id for h in hits)


async def test_files_and_tree_list_mounted_content(client, tmp_path):
    (tmp_path / "report.txt").write_text("isi laporan")
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)
    await client.post(
        f"/api/v1/workspace/{workspace_id}/mount",
        json={"path": str(tmp_path), "source_type": "Local", "alias": "Laporan"},
        headers=_as("ownerkey"),
    )

    files_res = await client.get(f"/api/v1/workspace/{workspace_id}/files", headers=_as("ownerkey"))
    assert files_res.status_code == 200
    files = files_res.json()["files"]
    assert len(files) == 1
    assert files[0]["relative_path"] == "report.txt"
    assert files[0]["source"] == "workspace"

    tree_res = await client.get(f"/api/v1/workspace/{workspace_id}/tree", headers=_as("ownerkey"))
    assert tree_res.status_code == 200
    tree = tree_res.json()["folders"]
    assert len(tree) == 1
    assert tree[0]["alias"] == "Laporan"
    assert "report.txt" in tree[0]["files"]


async def test_status_endpoint(client, tmp_path):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.get(f"/api/v1/workspace/{workspace_id}/status", headers=_as("ownerkey"))
    assert res.status_code == 200
    assert res.json()["status"] == "Active"


# ─── delete (soft) ──────────────────────────────────────────────────────

async def test_delete_workspace_is_soft_delete(client):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    del_res = await client.delete(f"/api/v1/workspace/{workspace_id}", headers=_as("ownerkey"))
    assert del_res.status_code == 200
    assert del_res.json()["deleted"] is True

    get_res = await client.get(f"/api/v1/workspace?project_id={project_id}", headers=_as("ownerkey"))
    assert get_res.status_code == 404


async def test_stranger_cannot_delete_workspace(client):
    project_id = await _make_project(client)
    workspace_id = await _make_workspace(client, project_id)

    res = await client.delete(f"/api/v1/workspace/{workspace_id}", headers=_as("strangerkey"))
    assert res.status_code == 403


# ─── Fase 9 (DCF v5 mandate "Workspace Manager UI") ────────────────────────
# browse-fs / mine / quick-connect — the in-app folder browser + one-call
# auto-provisioning that replaces manual Project/Workspace/mount management
# for the "Add Folder" flow. See api/routes/workspace.py module comment
# above _browse_roots for why this isn't a literal native OS picker.

async def test_browse_fs_no_path_returns_roots(client):
    res = await client.get("/api/v1/workspace/browse-fs", headers=_as("ownerkey"))
    assert res.status_code == 200
    body = res.json()
    assert body["path"] is None
    assert isinstance(body["entries"], list)
    assert len(body["entries"]) > 0


async def test_browse_fs_lists_subdirectories(client, tmp_path):
    (tmp_path / "Document").mkdir()
    (tmp_path / "Legal").mkdir()
    (tmp_path / "report.txt").write_text("not a directory")

    res = await client.get(f"/api/v1/workspace/browse-fs?path={tmp_path}", headers=_as("ownerkey"))
    assert res.status_code == 200
    body = res.json()
    names = {e["name"] for e in body["entries"]}
    assert names == {"Document", "Legal"}  # the file is excluded, only dirs


async def test_browse_fs_hides_dotfolders(client, tmp_path):
    (tmp_path / "Document").mkdir()
    (tmp_path / ".git").mkdir()

    res = await client.get(f"/api/v1/workspace/browse-fs?path={tmp_path}", headers=_as("ownerkey"))
    names = {e["name"] for e in res.json()["entries"]}
    assert names == {"Document"}


async def test_browse_fs_rejects_nonexistent_path(client):
    res = await client.get("/api/v1/workspace/browse-fs?path=/no/such/directory/anywhere", headers=_as("ownerkey"))
    assert res.status_code == 400


async def test_browse_fs_windows_drive_gets_friendly_path(client, tmp_path, monkeypatch):
    """/mnt/<letter>/... must display as D:\\... (mandate: user never sees
    the WSL path) — simulated here since the test sandbox isn't actually WSL."""
    from api.routes import workspace as workspace_route

    fake_drive = tmp_path / "mnt" / "d"
    fake_drive.mkdir(parents=True)
    (fake_drive / "04_Archive").mkdir()
    import re as _re

    monkeypatch.setattr(workspace_route, "_WSL_DRIVE_RE", _re.compile(rf"^{_re.escape(str(tmp_path))}/mnt/([a-zA-Z])(/.*)?$"))

    res = await client.get(f"/api/v1/workspace/browse-fs?path={fake_drive}", headers=_as("ownerkey"))
    body = res.json()
    assert body["friendly_path"] == "D:\\"
    assert body["entries"][0]["friendly_path"] == "D:\\04_Archive"


async def test_quick_connect_creates_project_workspace_folder_and_scans(client, tmp_path):
    (tmp_path / "laporan.pdf").write_bytes(b"%PDF-fake")
    (tmp_path / "site.png").write_bytes(b"\x89PNG-fake")

    res = await client.post(
        "/api/v1/workspace/quick-connect", json={"path": str(tmp_path)}, headers=_as("ownerkey")
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "Active"
    assert body["root_path"] == str(tmp_path)
    assert len(body["folders"]) == 1
    assert body["folders"][0]["path"] == str(tmp_path)
    assert body["scan"]["document_count"] == 1
    assert body["scan"]["image_count"] == 1


async def test_quick_connect_rejects_nonexistent_path(client):
    res = await client.post(
        "/api/v1/workspace/quick-connect", json={"path": "/no/such/directory/anywhere"}, headers=_as("ownerkey")
    )
    assert res.status_code == 400


async def test_quick_connect_uses_alias_as_folder_alias_and_project_name(client, tmp_path):
    res = await client.post(
        "/api/v1/workspace/quick-connect", json={"path": str(tmp_path), "alias": "Arsip Utama"},
        headers=_as("ownerkey"),
    )
    body = res.json()
    assert body["folders"][0]["alias"] == "Arsip Utama"


async def test_quick_connect_twice_creates_two_independent_workspaces(client, tmp_path):
    """Unlike POST /workspace (one Workspace per Project, 409 on a second),
    quick-connect always creates a fresh Project+Workspace pair — the sidebar
    is meant to hold multiple independently-connected top-level folders."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()

    res_a = await client.post("/api/v1/workspace/quick-connect", json={"path": str(dir_a)}, headers=_as("ownerkey"))
    res_b = await client.post("/api/v1/workspace/quick-connect", json={"path": str(dir_b)}, headers=_as("ownerkey"))
    assert res_a.status_code == 200
    assert res_b.status_code == 200
    assert res_a.json()["id"] != res_b.json()["id"]


async def test_mine_lists_all_connected_workspaces_for_owner(client, tmp_path):
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    await client.post("/api/v1/workspace/quick-connect", json={"path": str(dir_a)}, headers=_as("ownerkey"))
    await client.post("/api/v1/workspace/quick-connect", json={"path": str(dir_b)}, headers=_as("ownerkey"))

    res = await client.get("/api/v1/workspace/mine", headers=_as("ownerkey"))
    assert res.status_code == 200
    paths = {ws["root_path"] for ws in res.json()["workspaces"]}
    assert paths == {str(dir_a), str(dir_b)}


async def test_mine_excludes_other_users_workspaces(client, tmp_path):
    await client.post("/api/v1/workspace/quick-connect", json={"path": str(tmp_path)}, headers=_as("ownerkey"))

    res = await client.get("/api/v1/workspace/mine", headers=_as("strangerkey"))
    assert res.status_code == 200
    assert res.json()["workspaces"] == []


async def test_mine_excludes_soft_deleted_workspaces(client, tmp_path):
    connect_res = await client.post(
        "/api/v1/workspace/quick-connect", json={"path": str(tmp_path)}, headers=_as("ownerkey")
    )
    workspace_id = connect_res.json()["id"]
    await client.delete(f"/api/v1/workspace/{workspace_id}", headers=_as("ownerkey"))

    res = await client.get("/api/v1/workspace/mine", headers=_as("ownerkey"))
    assert res.json()["workspaces"] == []
