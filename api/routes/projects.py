"""Projects API — first backend implementation of the Phase 3 `Project`
entity (PROJECT_SPECIFICATION.md). Not a protected folder (Bab 45.1).

Scope deliberately narrow for this pass: Project CRUD + membership only.
PROJECT_SPECIFICATION.md §2 describes Conversation/Workflow/File
relationships to Project, but §6 explicitly leaves "can a Conversation move
between projects" etc. undecided — this route does not touch
`ConversationMessage`/`Document` schemas at all, so a Project is a
standalone grouping for now, not yet linked to actual chat/file data. That
wiring is a separate, later decision.

Identity: PROJECT_SPECIFICATION.md §3 specifies ``owner_id (FK -> User)``,
but no ``User`` table exists anywhere in this system — the real identity
primitive is the API key string from `security.auth.Principal`. Every
`owner_key`/`principal_key` here is that string. When `API_KEYS` is unset
(dev default), every caller is `Principal(api_key="", role="admin")`
(`security/auth.py`) — so in that mode every project's owner is the same
empty string and everyone can manage everyone's projects, consistent with
how every other route that opts into `get_current_principal` already
behaves when auth is disabled.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.connection import get_session
from db.models import Project, ProjectMember
from security.auth import Principal, get_current_principal

router = APIRouter()

MEMBER_ROLES = ("owner", "editor", "viewer")


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    status: str | None = None


class MemberRequest(BaseModel):
    principal_key: str = Field(..., min_length=1)
    role: str = Field("viewer", pattern="^(owner|editor|viewer)$")


async def _get_project_or_404(session: AsyncSession, project_id: str) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _role_for(session: AsyncSession, project: Project, principal: Principal) -> str | None:
    """Owner via `owner_key`, else looked up in `ProjectMember`, else None (no access)."""
    if project.owner_key == principal.api_key:
        return "owner"
    result = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.principal_key == principal.api_key
        )
    )
    member = result.scalar_one_or_none()
    return member.role if member else None


def _require(role: str | None, allowed: tuple[str, ...]) -> None:
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Insufficient project role")


@router.get("")
async def list_projects(
    session: AsyncSession = Depends(get_session), principal: Principal = Depends(get_current_principal)
):
    owned = await session.execute(select(Project).where(Project.owner_key == principal.api_key))
    member_rows = await session.execute(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.principal_key == principal.api_key)
    )
    seen: dict[str, Project] = {}
    for p in [*owned.scalars().all(), *member_rows.scalars().all()]:
        seen[p.id] = p
    projects = sorted(seen.values(), key=lambda p: p.created_at, reverse=True)
    return {
        "projects": [
            {"id": p.id, "name": p.name, "description": p.description, "status": p.status, "created_at": p.created_at}
            for p in projects
        ]
    }


@router.post("")
async def create_project(
    req: ProjectCreateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = Project(name=req.name, description=req.description, owner_key=principal.api_key)
    session.add(project)
    await session.commit()
    return {"id": project.id, "name": project.name, "status": project.status}


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = await _get_project_or_404(session, project_id)
    role = await _role_for(session, project, principal)
    _require(role, MEMBER_ROLES)

    members_res = await session.execute(select(ProjectMember).where(ProjectMember.project_id == project_id))
    members = members_res.scalars().all()
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "owner_key": project.owner_key,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "your_role": role,
        "members": [{"principal_key": m.principal_key, "role": m.role, "added_at": m.added_at} for m in members],
    }


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    req: ProjectUpdateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = await _get_project_or_404(session, project_id)
    role = await _role_for(session, project, principal)
    _require(role, ("owner", "editor"))

    if req.name is not None:
        project.name = req.name
    if req.description is not None:
        project.description = req.description
    if req.status is not None:
        _require(role, ("owner",))  # archiving is owner-only
        project.status = req.status
    await session.commit()
    return {"id": project.id, "name": project.name, "status": project.status}


@router.delete("/{project_id}")
async def archive_project(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Soft-delete (PROJECT_SPECIFICATION.md §6) — sets status="archived", never removes the row."""
    project = await _get_project_or_404(session, project_id)
    role = await _role_for(session, project, principal)
    _require(role, ("owner",))

    project.status = "archived"
    await session.commit()
    return {"id": project.id, "status": project.status}


@router.post("/{project_id}/members")
async def add_member(
    project_id: str,
    req: MemberRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = await _get_project_or_404(session, project_id)
    role = await _role_for(session, project, principal)
    _require(role, ("owner",))

    existing = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.principal_key == req.principal_key
        )
    )
    member = existing.scalar_one_or_none()
    if member is None:
        member = ProjectMember(project_id=project_id, principal_key=req.principal_key, role=req.role)
        session.add(member)
    else:
        member.role = req.role
    await session.commit()
    return {"principal_key": member.principal_key, "role": member.role}


@router.delete("/{project_id}/members/{principal_key}")
async def remove_member(
    project_id: str,
    principal_key: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = await _get_project_or_404(session, project_id)
    role = await _role_for(session, project, principal)
    _require(role, ("owner",))

    existing = await session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.principal_key == principal_key
        )
    )
    member = existing.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    await session.delete(member)
    await session.commit()
    return {"removed": True}
