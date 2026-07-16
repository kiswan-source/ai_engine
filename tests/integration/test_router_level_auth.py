"""Integration tests for Fase 1 Slice 1 — router-level auth on the 5 routers
that previously had no auth dependency at all (`ai`, `gis`, `pipeline`,
`docs`, `dokumen` — see `api/main.py`'s `_AUTH` list). Same isolated-client
pattern as `test_knowledge_auth.py`. One assertion pair per router is enough
to prove the router-level `dependencies=[Depends(get_current_principal)]`
wiring actually fires for every route under it, not a full behavioral suite.
"""
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "anykey:user")


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _as(key: str) -> dict:
    return {"X-API-Key": key}


async def test_ai_health_requires_auth(client):
    res = await client.get("/api/v1/ai/health")
    assert res.status_code == 401


async def test_ai_health_with_valid_key(client, monkeypatch):
    async def _fake_health_check(self):
        return {"status": "ok"}

    from core.ai.gemma_client import GemmaClient

    monkeypatch.setattr(GemmaClient, "health_check", _fake_health_check)
    res = await client.get("/api/v1/ai/health", headers=_as("anykey"))
    assert res.status_code == 200


async def test_gis_area_calculate_requires_auth(client):
    res = await client.post(
        "/api/v1/gis/area/calculate",
        json=[[106.0, -6.0], [106.01, -6.0], [106.01, -6.01]],
    )
    assert res.status_code == 401


async def test_gis_area_calculate_with_valid_key(client):
    res = await client.post(
        "/api/v1/gis/area/calculate",
        json=[[106.0, -6.0], [106.01, -6.0], [106.01, -6.01]],
        headers=_as("anykey"),
    )
    assert res.status_code == 200
    assert "area_ha" in res.json()


async def test_dokumen_komoditas_requires_auth(client):
    res = await client.get("/api/dokumen/komoditas")
    assert res.status_code == 401


async def test_dokumen_komoditas_with_valid_key(client):
    res = await client.get("/api/dokumen/komoditas", headers=_as("anykey"))
    assert res.status_code == 200


async def test_pipeline_enqueue_requires_auth(client):
    res = await client.post("/api/v1/pipeline/async/enqueue", json={})
    assert res.status_code == 401


async def test_docs_upload_requires_auth(client):
    res = await client.post("/api/v1/docs/upload-and-analyze")
    assert res.status_code == 401


async def test_no_api_keys_configured_behaves_as_before(client, monkeypatch):
    """Fase 0 chose loopback-only isolation over API-key auth — API_KEYS
    stays blank on the live system, so this must keep working as admin."""
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    res = await client.get("/api/dokumen/komoditas")
    assert res.status_code == 200
