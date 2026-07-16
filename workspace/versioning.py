"""File version history for Controlled AI Workspace writes (Fase 4, DCF v5
mandate "Workspace Autonomous Capability").

Every `agent/tools/workspace_reader.py::_write_file` overwrite of a file
that already existed snapshots the previous content here BEFORE writing —
so every change is recoverable without needing a live approval pause in
the middle of a chat turn (a known, deliberate limitation of this design,
not silently skipped — see that module's docstring). Restoring a version
is deliberately NOT exposed as a chat tool: it's a human action via
`api/routes/workspace.py`'s versions/restore endpoints, reviewed through
the Workspace UI, not something the model decides mid-conversation.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import WorkspaceFileVersion


async def save_version(
    session: AsyncSession, workspace_id: str, folder_id: str, relative_path: str,
    content: bytes, actor: str,
) -> WorkspaceFileVersion:
    """Snapshot ``content`` (the file's state right before being overwritten)."""
    version = WorkspaceFileVersion(
        workspace_id=workspace_id, folder_id=folder_id, relative_path=relative_path,
        content=content, size_bytes=len(content), actor=actor,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


async def list_versions(
    session: AsyncSession, workspace_id: str, folder_id: str, relative_path: str,
) -> list[dict[str, Any]]:
    """Newest-first metadata for every saved version of one file — ``content``
    is deliberately excluded here (could be large/binary); fetch one version
    explicitly via :func:`get_version` to read its bytes."""
    stmt = (
        select(WorkspaceFileVersion)
        .where(
            WorkspaceFileVersion.workspace_id == workspace_id,
            WorkspaceFileVersion.folder_id == folder_id,
            WorkspaceFileVersion.relative_path == relative_path,
        )
        # Autoincrement id, not created_at — two versions saved within the
        # same second (SQLite's CURRENT_TIMESTAMP resolution, hit live by
        # this module's own tests) would otherwise tie and sort ambiguously.
        .order_by(WorkspaceFileVersion.id.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {"id": r.id, "size_bytes": r.size_bytes, "actor": r.actor, "created_at": r.created_at}
        for r in rows
    ]


async def get_version(
    session: AsyncSession, version_id: int, workspace_id: str, folder_id: str,
) -> WorkspaceFileVersion | None:
    """One specific version's full row (including ``content``) — ``None`` if
    it doesn't exist or doesn't belong to ``workspace_id``/``folder_id``
    (never trust a caller-supplied ``version_id`` alone, same principle as
    ``workspace_id`` injection elsewhere in this codebase)."""
    version = await session.get(WorkspaceFileVersion, version_id)
    if version is None or version.workspace_id != workspace_id or version.folder_id != folder_id:
        return None
    return version
