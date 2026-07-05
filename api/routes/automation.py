"""Automation API — CRUD + manual trigger for `db.models.ScheduledJob`
(Bab 68 Prioritas 5). Not a protected folder (Bab 45.1).

Reuses the same `Orchestrator` singleton as `api/routes/orchestrator.py`
(not a fresh one) so scheduled runs share telemetry/circuit-breaker state
with manual runs — same reasoning as `monitoring.py`. The module-level
`_scheduler` here is what `api/main.py`'s lifespan starts/stops.

RBAC scoping mirrors `api/routes/projects.py`: jobs are visible/editable
only to their `owner_key` (the caller's API key) — same identity
primitive, same reasoning (no `User` table exists).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.orchestrator import _orchestrator
from db.connection import get_session
from db.models import ScheduledJob
from scheduler import Scheduler
from security.auth import Principal, get_current_principal

router = APIRouter()

_scheduler = Scheduler(_orchestrator)


class JobCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    prompt: str = Field(..., min_length=1)
    roles: list[str] = Field(..., min_length=1)
    mode: str = "sequential"
    interval_seconds: int = Field(..., ge=30)


class JobUpdateRequest(BaseModel):
    name: str | None = None
    prompt: str | None = None
    roles: list[str] | None = None
    mode: str | None = None
    interval_seconds: int | None = Field(None, ge=30)
    enabled: bool | None = None


def _serialize(job: ScheduledJob) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "prompt": job.prompt,
        "roles": job.roles,
        "mode": job.mode,
        "interval_seconds": job.interval_seconds,
        "enabled": job.enabled,
        "last_run_at": job.last_run_at,
        "last_status": job.last_status,
        "last_result_summary": job.last_result_summary,
        "next_run_at": job.next_run_at,
        "created_at": job.created_at,
    }


async def _get_owned_job_or_404(session: AsyncSession, job_id: str, principal: Principal) -> ScheduledJob:
    job = await session.get(ScheduledJob, job_id)
    if job is None or job.owner_key != principal.api_key:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return job


@router.get("/jobs")
async def list_jobs(
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    result = await session.execute(
        select(ScheduledJob).where(ScheduledJob.owner_key == principal.api_key).order_by(ScheduledJob.created_at.desc())
    )
    return {"jobs": [_serialize(j) for j in result.scalars().all()]}


@router.post("/jobs")
async def create_job(
    req: JobCreateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    job = ScheduledJob(
        name=req.name,
        prompt=req.prompt,
        roles=req.roles,
        mode=req.mode,
        interval_seconds=req.interval_seconds,
        owner_key=principal.api_key,
    )
    session.add(job)
    await session.commit()
    return _serialize(job)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    job = await _get_owned_job_or_404(session, job_id, principal)
    return _serialize(job)


@router.patch("/jobs/{job_id}")
async def update_job(
    job_id: str,
    req: JobUpdateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    job = await _get_owned_job_or_404(session, job_id, principal)
    for field in ("name", "prompt", "roles", "mode", "interval_seconds", "enabled"):
        value = getattr(req, field)
        if value is not None:
            setattr(job, field, value)
    await session.commit()
    return _serialize(job)


@router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    """Hard delete (db.models.ScheduledJob docstring) — unlike Project's soft-delete."""
    job = await _get_owned_job_or_404(session, job_id, principal)
    await session.delete(job)
    await session.commit()
    return {"deleted": True}


@router.post("/jobs/{job_id}/run-now")
async def run_job_now(
    job_id: str, session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    """Manual trigger, regardless of next_run_at — same execution path a real tick uses."""
    await _get_owned_job_or_404(session, job_id, principal)  # ownership check before touching the scheduler's own session
    job = await _scheduler.run_now(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scheduled job not found")
    return _serialize(job)
