"""Integration tests for /api/v1/projects/* — first backend implementation
of the Phase 3 Project entity (PROJECT_SPECIFICATION.md).

Same in-memory SQLite pattern as tests/integration/test_knowledge_api.py
(creating only the projects/project_members tables — VectorEmbedding's
pgvector column type would fail create_all() on SQLite).

Distinct callers are simulated via API_KEYS + X-API-Key headers (matching
test_orchestrator_api.py's test_decide_approval_denies_insufficient_role) —
identity here is just the key string, there's no User table (see
api/routes/projects.py module docstring).
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.connection import get_session
from db.models import Project, ProjectMember


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr(
        "api.config.settings.API_KEYS", "ownerkey:user,memberkey:user,strangerkey:user"
    )


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Project.metadata.create_all, tables=[Project.__table__, ProjectMember.__table__])
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


async def test_list_projects_empty(client):
    res = await client.get("/api/v1/projects", headers=_as("ownerkey"))
    assert res.status_code == 200
    assert res.json() == {"projects": []}


async def test_create_and_list_project(client):
    create_res = await client.post(
        "/api/v1/projects",
        json={"name": "Studi Kelayakan Tambang X", "description": "..."},
        headers=_as("ownerkey"),
    )
    assert create_res.status_code == 200
    project_id = create_res.json()["id"]

    list_res = await client.get("/api/v1/projects", headers=_as("ownerkey"))
    projects = list_res.json()["projects"]
    assert len(projects) == 1
    assert projects[0]["id"] == project_id
    assert projects[0]["status"] == "active"


async def test_project_invisible_to_stranger(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Rahasia"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]

    list_res = await client.get("/api/v1/projects", headers=_as("strangerkey"))
    assert list_res.json()["projects"] == []

    detail_res = await client.get(f"/api/v1/projects/{project_id}", headers=_as("strangerkey"))
    assert detail_res.status_code == 403


async def test_get_project_detail_as_owner(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Proyek A"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]

    res = await client.get(f"/api/v1/projects/{project_id}", headers=_as("ownerkey"))
    assert res.status_code == 200
    body = res.json()
    assert body["your_role"] == "owner"
    assert body["members"] == []


async def test_update_project_name(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Nama Lama"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]

    update_res = await client.patch(
        f"/api/v1/projects/{project_id}", json={"name": "Nama Baru"}, headers=_as("ownerkey")
    )
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Nama Baru"


async def test_archive_project_is_soft_delete(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Akan Diarsipkan"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]

    archive_res = await client.delete(f"/api/v1/projects/{project_id}", headers=_as("ownerkey"))
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "archived"

    # Row still exists and is still readable — not a hard delete.
    detail_res = await client.get(f"/api/v1/projects/{project_id}", headers=_as("ownerkey"))
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == "archived"


async def test_add_member_grants_access(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Kolaborasi"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]

    add_res = await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "memberkey", "role": "viewer"},
        headers=_as("ownerkey"),
    )
    assert add_res.status_code == 200
    assert add_res.json() == {"principal_key": "memberkey", "role": "viewer"}

    member_view = await client.get(f"/api/v1/projects/{project_id}", headers=_as("memberkey"))
    assert member_view.status_code == 200
    assert member_view.json()["your_role"] == "viewer"


async def test_viewer_cannot_update_project(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Proyek B"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "memberkey", "role": "viewer"},
        headers=_as("ownerkey"),
    )

    res = await client.patch(
        f"/api/v1/projects/{project_id}", json={"name": "Rebut"}, headers=_as("memberkey")
    )
    assert res.status_code == 403


async def test_remove_member(client):
    create_res = await client.post("/api/v1/projects", json={"name": "Proyek C"}, headers=_as("ownerkey"))
    project_id = create_res.json()["id"]
    await client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"principal_key": "memberkey", "role": "editor"},
        headers=_as("ownerkey"),
    )

    remove_res = await client.delete(
        f"/api/v1/projects/{project_id}/members/memberkey", headers=_as("ownerkey")
    )
    assert remove_res.status_code == 200

    member_view = await client.get(f"/api/v1/projects/{project_id}", headers=_as("memberkey"))
    assert member_view.status_code == 403


async def test_get_unknown_project_404(client):
    res = await client.get("/api/v1/projects/does-not-exist", headers=_as("ownerkey"))
    assert res.status_code == 404
