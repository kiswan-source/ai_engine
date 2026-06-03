"""
Integration Tests — FastAPI endpoints (no live Ollama/DB required — uses mocks)
Run: pytest tests/integration/test_api.py -v
"""
import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def app():
    """Create test app with mocked dependencies."""
    with (
        patch("db.connection.init_db", new_callable=AsyncMock),
        patch("db.connection.close_db", new_callable=AsyncMock),
    ):
        from api.main import app as _app
        yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
class TestHealthEndpoints:
    async def test_health_ok(self, client):
        resp = await client.get("/health/")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
class TestGISEndpoints:
    SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Placemark>
        <name>Gunung Leles</name>
        <Polygon>
          <outerBoundaryIs>
            <LinearRing>
              <coordinates>
                106.0000,-6.0000,0 106.0090,-6.0000,0
                106.0090,-6.0090,0 106.0000,-6.0090,0
                106.0000,-6.0000,0
              </coordinates>
            </LinearRing>
          </outerBoundaryIs>
        </Polygon>
      </Placemark>
    </kml>"""

    async def test_kml_parse(self, client):
        resp = await client.post(
            "/api/v1/gis/kml/parse",
            files={"file": ("test.kml", self.SAMPLE_KML.encode(), "application/vnd.google-earth.kml+xml")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["polygons"][0]["name"] == "Gunung Leles"
        assert data["polygons"][0]["area_ha"] > 0

    async def test_kml_to_geojson(self, client):
        resp = await client.post(
            "/api/v1/gis/kml/to-geojson",
            files={"file": ("test.kml", self.SAMPLE_KML.encode(), "application/vnd.google-earth.kml+xml")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 1

    async def test_area_calculate(self, client):
        coords = [
            [106.0, -6.0], [106.009, -6.0],
            [106.009, -6.009], [106.0, -6.009],
        ]
        resp = await client.post("/api/v1/gis/area/calculate", json=coords)
        assert resp.status_code == 200
        data = resp.json()
        assert "area_ha" in data
        assert data["area_ha"] > 0

    async def test_area_too_few_points(self, client):
        resp = await client.post("/api/v1/gis/area/calculate", json=[[106.0, -6.0]])
        assert resp.status_code == 400


@pytest.mark.asyncio
class TestAIEndpoints:
    async def test_ai_health(self, client):
        with patch(
            "core.ai.gemma_client.gemma.health_check",
            new_callable=AsyncMock,
            return_value={"ollama": "ok", "model": "gemma4:26b", "model_loaded": True},
        ):
            resp = await client.get("/api/v1/ai/health")
            assert resp.status_code == 200
            assert resp.json()["ollama"] == "ok"

    async def test_chat_endpoint(self, client):
        with patch(
            "core.ai.gemma_client.gemma.generate",
            new_callable=AsyncMock,
            return_value="Ini adalah respons AI dari Gemma.",
        ):
            resp = await client.post(
                "/api/v1/ai/chat",
                json={"message": "Apa itu batu andesit?", "use_cache": False},
            )
            assert resp.status_code == 200
            assert "response" in resp.json()
