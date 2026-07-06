"""Integration tests for Monitoring API authentication (Tahap 26).

No prior integration test existed for these routes at all (only unit tests
for the individual dashboard functions `telemetry/monitoring.py` exposes) —
this is the first HTTP-level coverage, and the first real caller of
`require_role("view_dashboard")` (defined since Tahap 7/ADR-0010, never
wired to a route before now).

`/dashboard` pulls in two real, slow dependencies, found by actually timing
this test rather than assumed hermetic — neither caused by this Tahap's
auth change, but both must be neutralized for this test to stay fast and
CI-safe (Bab 12.3, no live services):

1. `monitoring.workspace_dashboard(session)` — a real `Depends(get_session)`.
   With real Postgres and leftover `Workspace` rows from earlier manual
   verification (this dev box had several), it took 6+ seconds — it
   re-scans every registered folder's filesystem per request (a known,
   already-documented limitation, Tahap 19/21), worse with orphaned rows
   pointing at folders that no longer exist. Overridden to an empty
   in-memory sqlite here.
2. `monitoring.health_dashboard()`/`provider_dashboard()` both call
   `telemetry.monitoring.check_readiness()`, which makes *real* network
   calls to Ollama/OpenAI/Claude/Gemini (same work `/health/ready` does) —
   measured at 9+ seconds alone in this environment. Monkeypatched to a
   fast stub; these tests only care about the auth gate, not real
   provider connectivity.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.connection import get_session
from db.models import Workspace, WorkspaceFolder


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "anykey:user")


@pytest.fixture(autouse=True)
def _fast_health_check(monkeypatch):
    async def _fake_check_readiness():
        return {"ready": True, "checks": {}}

    monkeypatch.setattr("telemetry.monitoring.check_readiness", _fake_check_readiness)


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Workspace.metadata.create_all, tables=[Workspace.__table__, WorkspaceFolder.__table__])
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


async def test_dashboard_requires_auth(client):
    res = await client.get("/api/v1/monitoring/dashboard")
    assert res.status_code == 401


async def test_dashboard_accessible_with_any_authenticated_role(client):
    # Every role already includes view_dashboard (Bab 30) — this is "must
    # be authenticated", not a finer-grained per-role gate yet.
    res = await client.get("/api/v1/monitoring/dashboard", headers={"X-API-Key": "anykey"})
    assert res.status_code == 200
    assert "agent" in res.json()


async def test_alerts_requires_auth(client):
    res = await client.get("/api/v1/monitoring/alerts")
    assert res.status_code == 401


async def test_alerts_accessible_with_valid_key(client):
    res = await client.get("/api/v1/monitoring/alerts", headers={"X-API-Key": "anykey"})
    assert res.status_code == 200


async def test_no_api_keys_configured_behaves_as_before(client, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "")
    res = await client.get("/api/v1/monitoring/dashboard")
    assert res.status_code == 200
