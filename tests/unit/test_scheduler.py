"""Unit tests for scheduler.Scheduler (Bab 68 Prioritas 5) — fake clock (no
real sleeping), stub agents (no live provider calls, Bab 12.3), in-memory
SQLite instead of the real Postgres `AsyncSessionFactory` (Bab 12.3 — CI has
no live services).
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agents.base_agent import AgentResult, BaseAgent, Task
from db.models import ScheduledJob
from orchestrator import Orchestrator
from registry.agent_registry import AgentRegistry
from scheduler.scheduler import Scheduler


class StubAgent(BaseAgent):
    def __init__(self, role, output="ok", should_fail=False):
        self.role = role
        self.agent_id = f"{role}-stub"
        self.default_provider = "stub"
        self._output = output
        self._should_fail = should_fail

    async def execute(self, task: Task) -> AgentResult:
        if self._should_fail:
            raise RuntimeError("provider unreachable")
        return AgentResult(
            output=self._output, confidence=0.8, trace_id=task.trace_id,
            provider_used="stub", model_used="stub-m", role=self.role, agent_id=self.agent_id,
        )

    async def health_check(self) -> bool:
        return True


class _CapturingAgent(StubAgent):
    """Records the Task it was dispatched with, for asserting on
    task.metadata (Fase 14 — caller_role threading)."""

    def __init__(self, role, output="ok"):
        super().__init__(role, output=output)
        self.last_task: Task | None = None

    async def execute(self, task: Task) -> AgentResult:
        self.last_task = task
        return await super().execute(task)


def registry_with(*agents) -> AgentRegistry:
    reg = AgentRegistry()
    for a in agents:
        reg.register(a)
    return reg


@pytest.fixture
async def sqlite_session_factory(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(ScheduledJob.metadata.create_all, tables=[ScheduledJob.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("scheduler.scheduler.AsyncSessionFactory", factory)
    yield factory
    await engine.dispose()


def make_job(**overrides) -> ScheduledJob:
    defaults = dict(
        name="Laporan Harian",
        prompt="ringkas status hari ini",
        roles=["writer"],
        mode="sequential",
        interval_seconds=3600,
        enabled=True,
        owner_key="ownerkey",
    )
    defaults.update(overrides)
    return ScheduledJob(**defaults)


async def _insert(session_factory, job: ScheduledJob) -> str:
    async with session_factory() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job.id


class FakeClock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def test_tick_runs_due_job_and_records_success(sqlite_session_factory):
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer", output="hasil laporan")))
    scheduler = Scheduler(orch, clock=clock)
    job_id = await _insert(sqlite_session_factory, make_job())

    ran = await scheduler.tick()

    assert ran == 1
    async with sqlite_session_factory() as session:
        job = await session.get(ScheduledJob, job_id)
        assert job.last_status == "success"
        assert job.last_result_summary == "hasil laporan"
        assert job.last_run_at == clock.now
        assert job.next_run_at == clock.now + timedelta(seconds=3600)


async def test_tick_skips_job_not_yet_due(sqlite_session_factory):
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer")))
    scheduler = Scheduler(orch, clock=clock)
    job_id = await _insert(
        sqlite_session_factory, make_job(next_run_at=clock.now + timedelta(minutes=5))
    )

    ran = await scheduler.tick()

    assert ran == 0
    async with sqlite_session_factory() as session:
        job = await session.get(ScheduledJob, job_id)
        assert job.last_run_at is None


async def test_tick_skips_disabled_job(sqlite_session_factory):
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer")))
    scheduler = Scheduler(orch, clock=clock)
    await _insert(sqlite_session_factory, make_job(enabled=False))

    ran = await scheduler.tick()

    assert ran == 0


async def test_tick_records_failure_without_stopping_other_jobs(sqlite_session_factory):
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer", should_fail=True)))
    scheduler = Scheduler(orch, clock=clock)
    job_id = await _insert(sqlite_session_factory, make_job())

    ran = await scheduler.tick()

    assert ran == 1
    async with sqlite_session_factory() as session:
        job = await session.get(ScheduledJob, job_id)
        assert job.last_status == "failed"
        assert "provider unreachable" in job.last_result_summary
        assert job.next_run_at == clock.now + timedelta(seconds=3600)  # still reschedules


async def test_run_now_ignores_next_run_at(sqlite_session_factory):
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer", output="segera")))
    scheduler = Scheduler(orch, clock=clock)
    job_id = await _insert(
        sqlite_session_factory, make_job(next_run_at=clock.now + timedelta(days=1))
    )

    job = await scheduler.run_now(job_id)

    assert job.last_status == "success"
    assert job.last_result_summary == "segera"


async def test_run_now_unknown_job_returns_none(sqlite_session_factory):
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer")))
    scheduler = Scheduler(orch)
    assert await scheduler.run_now("does-not-exist") is None


async def test_start_stop_lifecycle_is_idempotent(sqlite_session_factory):
    orch = Orchestrator(agent_registry=registry_with(StubAgent("writer")))
    scheduler = Scheduler(orch, tick_seconds=3600)

    await scheduler.start()
    task_after_first_start = scheduler._task
    await scheduler.start()  # no-op, must not spawn a second loop
    assert scheduler._task is task_after_first_start

    await scheduler.stop()
    assert scheduler._task is None


# ── Fase 14 Gate 2 finding — caller_role must flow into scheduled runs too,
# not just the two HTTP-facing call sites (api/routes/orchestrator.py's /run
# and the chat bridge). Otherwise a scheduled job's EXECUTOR-capability steps
# would call tools completely unchecked by RBAC. ─────────────────────────


async def test_scheduled_job_resolves_caller_role_from_its_owner_key(sqlite_session_factory, monkeypatch):
    monkeypatch.setattr("api.config.settings.API_KEYS", "ownerkey:operator")
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    agent = _CapturingAgent("writer")
    orch = Orchestrator(agent_registry=registry_with(agent))
    scheduler = Scheduler(orch, clock=clock)
    await _insert(sqlite_session_factory, make_job(owner_key="ownerkey"))

    await scheduler.tick()

    assert agent.last_task.metadata.get("caller_role") == "operator"


async def test_scheduled_job_with_unresolvable_owner_key_runs_unchecked_not_crashed(sqlite_session_factory, monkeypatch):
    """A key that's no longer in API_KEYS (revoked/rotated) must degrade to
    the existing "no role, no check" default — same posture as any other
    caller that doesn't pass a role — never crash the job."""
    monkeypatch.setattr("api.config.settings.API_KEYS", "someotherkey:admin")
    clock = FakeClock(datetime(2026, 7, 5, 12, 0, 0))
    agent = _CapturingAgent("writer")
    orch = Orchestrator(agent_registry=registry_with(agent))
    scheduler = Scheduler(orch, clock=clock)
    await _insert(sqlite_session_factory, make_job(owner_key="revoked-key"))

    ran = await scheduler.tick()

    assert ran == 1
    assert agent.last_task.metadata.get("caller_role") is None
    await scheduler.stop()  # no-op, must not raise
