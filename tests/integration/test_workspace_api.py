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

    search_res = await client.get("/api/v1/knowledge/search", params={"q": unique_phrase})
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
