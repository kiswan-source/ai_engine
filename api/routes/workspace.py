"""Workspace API (MASTER_INSTRUCTION.md Bab 69.13, ADR-0005, Tahap 19) — formalizes
the hand-off doc's "rancangan awal, wajib diverifikasi tim backend sebelum
implementasi" endpoint sketch into a real contract. Not a protected folder
(Bab 45.1).

**RESTful shape, not the flat sketch.** Bab 69.13 lists `POST /workspace/mount`,
`/scan`, `/index` etc. with no resource id — workable only while exactly one
Workspace exists system-wide. Formalized here as
`/workspace/{workspace_id}/mount|scan|index|files|tree|status`, mirroring the
`/projects/{id}/members` sub-resource pattern already established in
`api/routes/projects.py`.

**RBAC is resource-scoped, not global.** A Workspace always belongs to one
Project (Bab 69.11: "Workspace adalah bagian dari Project"), so every route
resolves the caller's Project role via `api/routes/projects.py::_role_for`
(reused, not duplicated) and then calls
`security/permissions.py::require_workspace_permission` — see that module's
Tahap 19 docstring for the full rationale.

**Every mutating route (create/patch/delete/mount/scan/index) requires the
"admin" Workspace Permission** — Bab 69.7's Admin row is literally "Kelola
pendaftaran/mount/hapus Workspace Folder", and scan/index are the same kind
of Workspace-management action, not passive content access. The finer-grained
actions (`read`/`read_only`/`write_output`/`generated`/`knowledge`/`vector`/
`temporary`) are reserved for a later, more granular layer — per-file Agent
content access during a running Workflow (Bab 69.5's Agent Workspace
Context) — not for gating these registration/management HTTP endpoints.
This is a deliberate scope decision (Bab 69.7 doesn't specify which action
maps to which endpoint), documented here rather than left implicit.

**Root Restriction (Bab 69.6) is enforced per registered `WorkspaceFolder`,
not per shared "Workspace Root".** `Workspace.root_path` is informational
only — set to the first mounted folder's path for display (Bab 69.14's
"Workspace Path" field) — because `PROJECT_SPECIFICATION.md` §7.1 leaves the
relationship between it and individual `WorkspaceFolder.path` entries
undecided. Each folder is independently sandboxed via
`tools/adapters/filesystem.py` (a caller can never read outside ANY
registered folder — a stronger guarantee than one shared umbrella root).

**`POST .../index` reuses `api/routes/knowledge.py`'s `_retriever` singleton
directly**, not just its namespace string — with `VECTOR_BACKEND=memory`
(the Bab 12 dev/CI default), two independently-built `Retriever`s each wrap
their own `InMemoryKnowledgeStore`, so indexed content would never show up
in `GET /api/v1/knowledge/search` even though both used the name
`"rag:documents"`. Only sharing the same store instance (matching
`PgVectorKnowledgeStore`'s behavior, where any two instances already hit the
same Postgres table) makes "Workspace Folder is a RAG Source" (Bab 69.10)
actually true end-to-end, not just true when Postgres happens to be
configured. `workspace/indexer.py::index_folder` still defaults to building
its own `Retriever` when called without one, for standalone/unit-test use.

**Local only this pass** (Bab 69.3): `POST .../mount` 400s on any
`source_type` other than `"Local"`, with an explicit "roadmap" message
(Bab 69.16), rather than silently accepting inert metadata for adapters that
don't exist yet.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.knowledge import _retriever as _knowledge_retriever
from api.routes.projects import _role_for
from db.connection import get_session
from db.models import Project, Workspace, WorkspaceFolder
from security.auth import Principal, get_current_principal
from security.permissions import require_workspace_permission
from tools.adapters.filesystem import FilesystemAdapter
from workspace.indexer import index_folder
from workspace.scanner import scan_folders

router = APIRouter()

VALID_SOURCE_TYPES = ("Local", "Network", "Server", "Upload")
IMPLEMENTED_SOURCE_TYPES = ("Local",)


class WorkspaceCreateRequest(BaseModel):
    project_id: str = Field(..., min_length=1)


class WorkspaceUpdateRequest(BaseModel):
    root_path: str | None = None


class MountRequest(BaseModel):
    path: str = Field(..., min_length=1)
    source_type: str = Field("Local")
    alias: str | None = None


def _folder_dict(folder: WorkspaceFolder) -> dict:
    return {
        "id": folder.id,
        "path": folder.path,
        "source_type": folder.source_type,
        "alias": folder.alias,
        "registered_at": folder.registered_at,
    }


def _workspace_dict(workspace: Workspace, folders: list[WorkspaceFolder]) -> dict:
    return {
        "id": workspace.id,
        "project_id": workspace.project_id,
        "root_path": workspace.root_path,
        "status": workspace.status,
        "last_scan_at": workspace.last_scan_at,
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
        "folders": [_folder_dict(f) for f in folders],
    }


async def _get_workspace_or_404(session: AsyncSession, workspace_id: str) -> Workspace:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None or workspace.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


async def _folders_for(session: AsyncSession, workspace_id: str) -> list[WorkspaceFolder]:
    result = await session.execute(select(WorkspaceFolder).where(WorkspaceFolder.workspace_id == workspace_id))
    return list(result.scalars().all())


async def _project_role_for_workspace(
    session: AsyncSession, workspace: Workspace, principal: Principal
) -> str | None:
    project = await session.get(Project, workspace.project_id)
    if project is None:
        return None
    return await _role_for(session, project, principal)


async def _require_member(session: AsyncSession, workspace: Workspace, principal: Principal) -> str | None:
    """Any Project role (owner/editor/viewer) may read a Workspace."""
    role = await _project_role_for_workspace(session, workspace, principal)
    if role not in ("owner", "editor", "viewer"):
        raise HTTPException(status_code=403, detail="Insufficient project role")
    return role


async def _require_admin(session: AsyncSession, workspace: Workspace, principal: Principal) -> str | None:
    """Workspace Permission "admin" — see module docstring for why every
    mutating route in this file uses this single action."""
    role = await _project_role_for_workspace(session, workspace, principal)
    try:
        require_workspace_permission(role, "admin")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return role


@router.get("")
async def get_workspace(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    result = await session.execute(
        select(Workspace).where(Workspace.project_id == project_id, Workspace.deleted_at.is_(None))
    )
    workspace = result.scalar_one_or_none()
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found for this project")
    await _require_member(session, workspace, principal)
    folders = await _folders_for(session, workspace.id)
    return _workspace_dict(workspace, folders)


@router.post("")
async def create_workspace(
    req: WorkspaceCreateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    project = await session.get(Project, req.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    role = await _role_for(session, project, principal)
    if role not in ("owner", "editor"):
        raise HTTPException(status_code=403, detail="Insufficient project role")

    existing = await session.execute(
        select(Workspace).where(Workspace.project_id == req.project_id, Workspace.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Workspace already exists for this project")

    workspace = Workspace(project_id=req.project_id)
    session.add(workspace)
    await session.commit()
    return _workspace_dict(workspace, [])


@router.patch("/{workspace_id}")
async def update_workspace(
    workspace_id: str,
    req: WorkspaceUpdateRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_admin(session, workspace, principal)

    if req.root_path is not None:
        workspace.root_path = req.root_path
    await session.commit()
    folders = await _folders_for(session, workspace.id)
    return _workspace_dict(workspace, folders)


@router.delete("/{workspace_id}")
async def delete_workspace(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Soft-delete (deleted_at, Bab 69.3) — never removes the row, never touches source files."""
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_admin(session, workspace, principal)

    workspace.deleted_at = datetime.utcnow()
    await session.commit()
    return {"id": workspace.id, "deleted": True}


@router.post("/{workspace_id}/mount")
async def mount_folder(
    workspace_id: str,
    req: MountRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_admin(session, workspace, principal)

    if req.source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown source_type {req.source_type!r}")
    if req.source_type not in IMPLEMENTED_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type={req.source_type!r} is a Bab 69.16 roadmap item — only 'Local' is implemented",
        )

    try:
        FilesystemAdapter(req.path)  # validates the directory exists, doesn't read it
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))

    folder = WorkspaceFolder(workspace_id=workspace.id, source_type=req.source_type, path=req.path, alias=req.alias)
    session.add(folder)
    if workspace.root_path is None:
        workspace.root_path = req.path
    await session.commit()
    return _folder_dict(folder)


@router.post("/{workspace_id}/scan")
async def scan_workspace(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_admin(session, workspace, principal)
    folders = [f for f in await _folders_for(session, workspace.id) if f.source_type == "Local"]

    workspace.status = "Scanning"
    await session.commit()

    try:
        adapters = {f.id: FilesystemAdapter(f.path) for f in folders}
        summary = scan_folders(adapters)
    except (NotADirectoryError, OSError) as e:
        workspace.status = "Error"
        await session.commit()
        raise HTTPException(status_code=400, detail=f"Scan failed: {e}")

    workspace.status = "Active"
    workspace.last_scan_at = datetime.utcnow()
    await session.commit()

    return {
        "status": workspace.status,
        "last_scan_at": workspace.last_scan_at,
        "document_count": summary.document_count,
        "image_count": summary.image_count,
        "gis_count": summary.gis_count,
        "other_count": summary.other_count,
        "total_size_bytes": summary.total_size_bytes,
    }


@router.post("/{workspace_id}/index")
async def index_workspace(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_admin(session, workspace, principal)
    folders = [f for f in await _folders_for(session, workspace.id) if f.source_type == "Local"]

    workspace.status = "Indexing"
    await session.commit()

    try:
        total_chunks = 0
        for folder in folders:
            adapter = FilesystemAdapter(folder.path)
            total_chunks += await index_folder(
                adapter, workspace_id=workspace.id, folder_id=folder.id, retriever=_knowledge_retriever
            )
    except (NotADirectoryError, OSError) as e:
        workspace.status = "Error"
        await session.commit()
        raise HTTPException(status_code=400, detail=f"Index failed: {e}")

    workspace.status = "Active"
    await session.commit()
    return {"status": workspace.status, "chunks_indexed": total_chunks}


@router.get("/{workspace_id}/files")
async def list_workspace_files(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Workspace Files (Bab 69.9) — from registered WorkspaceFolder, distinct
    from (and not merged with) Uploaded Files (F-003 resolution, unchanged)."""
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_member(session, workspace, principal)
    folders = [f for f in await _folders_for(session, workspace.id) if f.source_type == "Local"]

    files = []
    for folder in folders:
        adapter = FilesystemAdapter(folder.path)
        for f in adapter.list_tree():
            files.append(
                {
                    "folder_id": folder.id,
                    "folder_alias": folder.alias,
                    "relative_path": f.relative_path,
                    "category": f.category,
                    "size_bytes": f.size_bytes,
                    "source": "workspace",
                }
            )
    return {"files": files}


@router.get("/{workspace_id}/tree")
async def workspace_tree(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_member(session, workspace, principal)
    folders = await _folders_for(session, workspace.id)

    tree = []
    for folder in folders:
        entry = {"id": folder.id, "alias": folder.alias, "path": folder.path, "source_type": folder.source_type, "files": []}
        if folder.source_type == "Local":
            adapter = FilesystemAdapter(folder.path)
            entry["files"] = [f.relative_path for f in adapter.list_tree()]
        tree.append(entry)
    return {"folders": tree}


@router.get("/{workspace_id}/status")
async def workspace_status(
    workspace_id: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Lightweight polling endpoint (Bab 69.14) — Workspace Path/Status/Last Scan only."""
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_member(session, workspace, principal)
    return {
        "id": workspace.id,
        "status": workspace.status,
        "root_path": workspace.root_path,
        "last_scan_at": workspace.last_scan_at,
    }
