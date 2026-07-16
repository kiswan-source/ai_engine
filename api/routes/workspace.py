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

import asyncio
import os
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.knowledge import _retriever as _knowledge_retriever
from api.routes.projects import _role_for
from db.connection import get_session
from db.models import Project, ProjectMember, Workspace, WorkspaceFolder
from security import audit_log
from security.auth import Principal, get_current_principal
from security.permissions import require_workspace_permission
from tools.adapters.filesystem import FilesystemAdapter
from tools.tool_validator import PathEscapesRootError
from workspace.indexer import index_folder
from workspace.scanner import scan_folders
from workspace.versioning import get_version, list_versions, save_version

router = APIRouter()

VALID_SOURCE_TYPES = ("Local", "Network", "Server", "Upload")
IMPLEMENTED_SOURCE_TYPES = ("Local",)

# Fase 9 (DCF v5 mandate "Workspace Manager UI — Native Windows Folder
# Connection") — Owner decision (Gate 1): a browser can never hand JS a real
# OS path (no showDirectoryPicker()/webkitdirectory API exposes one — a
# deliberate browser security boundary, not a gap here), so "native folder
# picker -> registerWorkspace(path)" is impossible as literally specified.
# The chosen substitute is an in-app folder browser: browse-fs lists real
# server-side directories so the frontend can render a click-to-navigate tree
# instead of a text input. Owner also decided this endpoint may browse
# anywhere the process can reach (no allow-list) — permission is the act of
# picking a folder, same posture Workspace registration already has.
_WSL_DRIVE_RE = re.compile(r"^/mnt/([a-zA-Z])(/.*)?$")


def _friendly_path(path: str) -> str:
    """Display-only conversion so a WSL-mounted Windows drive shows as
    ``D:\\Archive`` instead of ``/mnt/d/Archive`` — the mandate's "user never
    sees the WSL path" requirement. Anything else (native Linux/macOS paths)
    passes through unchanged."""
    m = _WSL_DRIVE_RE.match(path)
    if not m:
        return path
    letter, rest = m.group(1).upper(), (m.group(2) or "")
    return f"{letter}:{rest.replace('/', chr(92))}" if rest else f"{letter}:\\"


def _browse_roots() -> list[dict]:
    """Starting points for the folder browser when no ``path`` is given —
    surfaces WSL-mounted Windows drives (``/mnt/c``, ``/mnt/d``, ...)
    prominently since that's how ``D:\\`` reaches this process, plus the
    home directory and ``/`` as a full-filesystem fallback."""
    roots = []
    home = os.path.expanduser("~")
    if os.path.isdir(home):
        roots.append({"name": "Home", "path": home, "friendly_path": _friendly_path(home)})
    mnt = "/mnt"
    if os.path.isdir(mnt):
        try:
            for entry in sorted(os.listdir(mnt)):
                p = os.path.join(mnt, entry)
                if len(entry) == 1 and os.path.isdir(p):
                    roots.append({"name": f"{entry.upper()}:\\", "path": p, "friendly_path": _friendly_path(p)})
        except OSError:
            pass
    roots.append({"name": "/ (root filesystem)", "path": "/", "friendly_path": "/"})
    return roots


class WorkspaceCreateRequest(BaseModel):
    project_id: str = Field(..., min_length=1)


class WorkspaceUpdateRequest(BaseModel):
    root_path: str | None = None


class MountRequest(BaseModel):
    path: str = Field(..., min_length=1)
    source_type: str = Field("Local")
    alias: str | None = None


class RestoreVersionRequest(BaseModel):
    relative_path: str = Field(..., min_length=1)
    version_id: int


class QuickConnectRequest(BaseModel):
    path: str = Field(..., min_length=1)
    alias: str | None = Field(None, max_length=256)  # parity with ProjectCreateRequest.name/Project.name column


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


async def _get_folder_or_404(session: AsyncSession, workspace_id: str, folder_id: str) -> WorkspaceFolder:
    folder = await session.get(WorkspaceFolder, folder_id)
    if folder is None or folder.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Folder not found in this workspace")
    return folder


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


async def _require_write(session: AsyncSession, workspace: Workspace, principal: Principal) -> str | None:
    """Workspace Permission "write_output" (Fase 4) — the same action
    `agent/tools/workspace_reader.py::workspace_write_file` already gates on
    for the chat-tool write path; restoring a version is equally a content
    mutation, not Workspace-registration management, so it uses this
    finer-grained action rather than "admin" like the routes above."""
    role = await _project_role_for_workspace(session, workspace, principal)
    try:
        require_workspace_permission(role, "write_output")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return role


@router.get("/browse-fs")
async def browse_filesystem(
    path: str | None = None,
    principal: Principal = Depends(get_current_principal),
):
    """In-app folder browser (Fase 9) — the practical substitute for a
    literal native OS picker (see module-level comment above
    ``_browse_roots``). Lists only immediate subdirectories of ``path`` (not
    files — this endpoint exists to let the user navigate to and pick a
    FOLDER for Add Folder, not to browse file contents); omit ``path`` to get
    the curated starting points instead. Authenticated callers only — no
    further scoping, per Owner decision (Gate 1) that browsing anywhere the
    process can reach is the intended permission model, same posture
    Workspace registration itself already has."""
    if not path:
        return {"path": None, "parent": None, "entries": _browse_roots()}

    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    entries = []
    try:
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full) and not name.startswith("."):
                entries.append({"name": name, "path": full, "friendly_path": _friendly_path(full)})
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Cannot list directory: {e}")

    parent = os.path.dirname(path.rstrip("/")) or None
    if parent == path:
        parent = None
    return {"path": path, "friendly_path": _friendly_path(path), "parent": parent, "entries": entries}


@router.get("/mine")
async def list_my_workspaces(
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Every Workspace the caller can reach (owns or is a member of the
    owning Project), across Projects — the "connected folders" list the
    Workspace Manager sidebar shows without the user ever picking a Project
    first (Fase 9). Reuses `api/routes/projects.py::list_projects`'s exact
    owned-or-member query shape rather than duplicating it under a new name."""
    owned = await session.execute(select(Project).where(Project.owner_key == principal.api_key))
    member_rows = await session.execute(
        select(Project)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(ProjectMember.principal_key == principal.api_key)
    )
    project_ids = {p.id for p in [*owned.scalars().all(), *member_rows.scalars().all()]}
    if not project_ids:
        return {"workspaces": []}

    result = await session.execute(
        select(Workspace).where(Workspace.project_id.in_(project_ids), Workspace.deleted_at.is_(None))
    )
    workspaces = result.scalars().all()
    out = []
    for ws in workspaces:
        folders = await _folders_for(session, ws.id)
        d = _workspace_dict(ws, folders)
        d["friendly_root_path"] = _friendly_path(ws.root_path) if ws.root_path else None
        out.append(d)
    out.sort(key=lambda d: d["updated_at"], reverse=True)
    return {"workspaces": out}


@router.post("/quick-connect")
async def quick_connect(
    req: QuickConnectRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """One call that does everything "Add Folder" needs (Fase 9) — auto
    Project + Workspace + WorkspaceFolder + scan, so the frontend never has
    to manage a Project, a Workspace id, or a mount step separately. Reuses
    the exact same primitives `create_project`/`create_workspace`/
    `mount_folder`/`scan_workspace` already use (Project/Workspace/
    WorkspaceFolder models, ``FilesystemAdapter``, ``scan_folders``) — this
    is a convenience composition over existing Workspace Engine internals,
    not a new system (Owner's explicit non-negotiable constraint)."""
    try:
        FilesystemAdapter(req.path)  # validates the directory exists, doesn't read it
    except NotADirectoryError as e:
        raise HTTPException(status_code=400, detail=str(e))

    friendly = _friendly_path(req.path)
    name = req.alias or os.path.basename(req.path.rstrip("/\\")) or friendly

    project = Project(name=name, owner_key=principal.api_key)
    session.add(project)
    await session.flush()

    workspace = Workspace(project_id=project.id, root_path=req.path)
    session.add(workspace)
    await session.flush()

    folder = WorkspaceFolder(workspace_id=workspace.id, source_type="Local", path=req.path, alias=req.alias or name)
    session.add(folder)

    try:
        adapter = FilesystemAdapter(req.path)
        # Found by adversarial Gate 2 review: a recursive os.walk (scan_folders
        # -> FilesystemAdapter._walk) run directly on the request coroutine
        # blocks the WHOLE asyncio event loop — every other API request,
        # everyone's — for as long as the walk takes. The "Add Folder" flow
        # makes triggering a full-drive-or-root scan a couple of clicks away
        # (the browse-fs roots deliberately include "/"), a materially easier
        # trigger than the pre-existing scan_workspace route (same root
        # cause, not fixed here — no UI shortcut made it a casual click
        # before this Fase). asyncio.to_thread keeps this request itself
        # just as slow, but stops it from stalling every OTHER caller.
        summary = await asyncio.to_thread(scan_folders, {folder.id: adapter})
    except (NotADirectoryError, OSError) as e:
        await session.rollback()
        raise HTTPException(status_code=400, detail=f"Scan failed: {e}")

    workspace.status = "Active"
    workspace.last_scan_at = datetime.utcnow()
    await session.commit()
    # workspace.updated_at has onupdate=func.now() — the UPDATE above expires
    # it (SQLite/aiosqlite doesn't eagerly re-fetch onupdate defaults via
    # RETURNING the way flush()-time INSERT defaults get fetched), so a bare
    # attribute access after commit tries an implicit lazy-load outside any
    # awaited context ("MissingGreenlet"). Explicit refresh avoids it.
    await session.refresh(workspace)
    await session.refresh(folder)

    await audit_log.record(
        "workspace.quick_connected", actor=principal.api_key,
        detail={"workspace_id": workspace.id, "project_id": project.id, "path": req.path},
    )

    d = _workspace_dict(workspace, [folder])
    d["friendly_root_path"] = friendly
    d["scan"] = {
        "document_count": summary.document_count,
        "image_count": summary.image_count,
        "gis_count": summary.gis_count,
        "other_count": summary.other_count,
        "total_size_bytes": summary.total_size_bytes,
    }
    return d


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


@router.get("/{workspace_id}/files/{folder_id}/versions")
async def get_file_versions(
    workspace_id: str,
    folder_id: str,
    path: str,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Version history for one file (Fase 4) — same read access as any other
    Workspace content (`_require_member`: owner/editor/viewer). `content`
    bytes are deliberately not included per-entry; restore reads them
    server-side instead of round-tripping potentially large/binary content
    through this listing."""
    workspace = await _get_workspace_or_404(session, workspace_id)
    await _require_member(session, workspace, principal)
    await _get_folder_or_404(session, workspace_id, folder_id)
    versions = await list_versions(session, workspace_id, folder_id, path)
    return {"relative_path": path, "versions": versions}


@router.post("/{workspace_id}/files/{folder_id}/restore")
async def restore_file_version(
    workspace_id: str,
    folder_id: str,
    req: RestoreVersionRequest,
    session: AsyncSession = Depends(get_session),
    principal: Principal = Depends(get_current_principal),
):
    """Restore a file to a previously saved version (Fase 4, CONTROL —
    rollback). Deliberately a human-facing HTTP endpoint, not a chat tool —
    see `workspace/versioning.py`'s module docstring for why. Gated on
    `write_output` (`_require_write`), same permission the chat write-path
    tool already uses — restoring is equally a content mutation.

    Restoring is itself an overwrite of whatever is live right now, so the
    current content is snapshotted first too — a restore can always be
    undone, not just the original write that prompted it."""
    workspace = await _get_workspace_or_404(session, workspace_id)
    role = await _require_write(session, workspace, principal)
    folder = await _get_folder_or_404(session, workspace_id, folder_id)
    if folder.source_type != "Local":
        raise HTTPException(status_code=400, detail=f"source_type={folder.source_type!r} belum didukung.")

    version = await get_version(session, req.version_id, workspace_id, folder_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found for this file")

    try:
        adapter = FilesystemAdapter(folder.path)
        abs_path = adapter.absolute_path(req.relative_path)
        if abs_path.exists():
            current_bytes = adapter.read_bytes(req.relative_path)
            await save_version(
                session, workspace_id, folder_id, req.relative_path, current_bytes,
                actor=principal.api_key,
            )
        adapter.write_bytes(req.relative_path, version.content)
    except PathEscapesRootError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await audit_log.record(
        "workspace.file_restored",
        actor=principal.api_key,
        detail={"workspace_id": workspace_id, "folder_id": folder_id,
                "path": req.relative_path, "restored_version_id": req.version_id},
    )
    return {"success": True, "path": req.relative_path, "restored_from_version_id": req.version_id}
