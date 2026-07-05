"""Integration tests for /api/v1/automation/* (Bab 68 Prioritas 5).

Same in-memory SQLite pattern as test_projects_api.py/test_knowledge_api.py
for the request-scoped `get_session` dependency. `Scheduler.run_now()` talks
to `db.connection.AsyncSessionFactory` directly rather than the per-request
dependency (it isn't a request itself), so that module-level name is also
monkeypatched to the same SQLite factory, and `api.routes.automation._scheduler`
is swapped for one backed by a stub agent — same reasoning as
`test_orchestrator_api.py`'s `stub_orchestrator` fixture.
"""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agents.base_agent import AgentResult, BaseAgent, Task
from db.connection import get_session
from db.models import ScheduledJob
from orchestrator import Orchestrator
from registry.agent_registry import AgentRegistry
from scheduler.scheduler import Scheduler


class StubAgent(BaseAgent):
    def __init__(self, role, output="ok"):
        self.role = role
        self.agent_id = f"{role}-stub"
        self.default_provider = "stub"
        self._output = output

    async def execute(self, task: Task) -> AgentResult:
        return AgentResult(
            output=self._output, confidence=0.8, trace_id=task.trace_id,
            provider_used="stub", model_used="stub-m", role=self.role, agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


def registry_with(*agents) -> AgentRegistry:
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg


@pytest.fixture(autouse=True)
def _api_keys(monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "ownerkey:user,strangerkey:user")


@pytest.fixture
async def app():
    from api.main import app as _app

    yield _app


@pytest.fixture
async def sqlite_session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ScheduledJob.metadata.create_all, tables=[ScheduledJob.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("scheduler.scheduler.AsyncSessionFactory", factory)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(app, sqlite_session_factory, monkeypatch):
    import api.routes.automation as route

    monkeypatch.setattr(
        route, "_scheduler", Scheduler(Orchestrator(agent_registry=registry_with(StubAgent("writer", output="hasil"))))
    )

    async def _override_get_session():
        async with sqlite_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def _as(key: str) -> dict:
    return {"X-API-Key": key}


async def test_list_jobs_empty(client):
    res = await client.get("/api/v1/automation/jobs", headers=_as("ownerkey"))
    assert res.status_code == 200
    assert res.json() == {"jobs": []}


async def test_create_and_list_job(client):
    create_res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "Laporan Harian", "prompt": "ringkas status", "roles": ["writer"], "interval_seconds": 3600},
        headers=_as("ownerkey"),
    )
    assert create_res.status_code == 200
    body = create_res.json()
    assert body["enabled"] is True
    assert body["last_status"] is None

    list_res = await client.get("/api/v1/automation/jobs", headers=_as("ownerkey"))
    assert len(list_res.json()["jobs"]) == 1


async def test_job_invisible_to_stranger(client):
    create_res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "Rahasia", "prompt": "x", "roles": ["writer"], "interval_seconds": 3600},
        headers=_as("ownerkey"),
    )
    job_id = create_res.json()["id"]

    list_res = await client.get("/api/v1/automation/jobs", headers=_as("strangerkey"))
    assert list_res.json()["jobs"] == []

    get_res = await client.get(f"/api/v1/automation/jobs/{job_id}", headers=_as("strangerkey"))
    assert get_res.status_code == 404


async def test_update_job_disables_it(client):
    create_res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "J", "prompt": "x", "roles": ["writer"], "interval_seconds": 3600},
        headers=_as("ownerkey"),
    )
    job_id = create_res.json()["id"]

    update_res = await client.patch(
        f"/api/v1/automation/jobs/{job_id}", json={"enabled": False}, headers=_as("ownerkey")
    )
    assert update_res.status_code == 200
    assert update_res.json()["enabled"] is False


async def test_delete_job_is_hard_delete(client):
    create_res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "J", "prompt": "x", "roles": ["writer"], "interval_seconds": 3600},
        headers=_as("ownerkey"),
    )
    job_id = create_res.json()["id"]

    delete_res = await client.delete(f"/api/v1/automation/jobs/{job_id}", headers=_as("ownerkey"))
    assert delete_res.status_code == 200

    get_res = await client.get(f"/api/v1/automation/jobs/{job_id}", headers=_as("ownerkey"))
    assert get_res.status_code == 404


async def test_run_now_executes_immediately_and_records_result(client):
    create_res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "J", "prompt": "x", "roles": ["writer"], "interval_seconds": 3600},
        headers=_as("ownerkey"),
    )
    job_id = create_res.json()["id"]

    run_res = await client.post(f"/api/v1/automation/jobs/{job_id}/run-now", headers=_as("ownerkey"))
    assert run_res.status_code == 200
    body = run_res.json()
    assert body["last_status"] == "success"
    assert body["last_result_summary"] == "hasil"
    assert body["next_run_at"] is not None


async def test_run_now_denied_for_non_owner(client):
    create_res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "J", "prompt": "x", "roles": ["writer"], "interval_seconds": 3600},
        headers=_as("ownerkey"),
    )
    job_id = create_res.json()["id"]

    res = await client.post(f"/api/v1/automation/jobs/{job_id}/run-now", headers=_as("strangerkey"))
    assert res.status_code == 404


async def test_create_rejects_interval_below_minimum(client):
    res = await client.post(
        "/api/v1/automation/jobs",
        json={"name": "J", "prompt": "x", "roles": ["writer"], "interval_seconds": 5},
        headers=_as("ownerkey"),
    )
    assert res.status_code == 422
