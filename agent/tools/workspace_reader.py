"""Agent Workspace Context (MASTER_INSTRUCTION.md Bab 69.5, Tahap 23) exposed
as Chat tools — lets the model read from a Project Workspace (Tahap 19)
instead of only Uploaded Files.

Root Restriction (Bab 69.6) is enforced by `tools/adapters/filesystem.py`,
the same primitive `api/routes/workspace.py`'s HTTP endpoints already use —
this module never touches the filesystem any other way. Access here trusts
that the *session* was already authorized to use this Workspace (checked
once at `api/routes/chat.py`'s bind time) — these functions don't re-derive
Project membership themselves, since doing so would mean `agent/tools/`
importing from `api/routes/`, the wrong dependency direction (see
`workspace/indexer.py`'s docstring on the same rule for `workspace/`).

`workspace_list_files`/`workspace_read_file` (the sync functions actually
registered in `agent/tools/registry.py`) are thin `asyncio.run(...)`
wrappers around the async helpers below — the same pattern
`agent/tools/registry.py`'s `mcp_list_tools`/`mcp_call_tool` (Tahap 17)
already use for one-off async work triggered from `ChatEngine._run_tool`'s
`asyncio.to_thread` (a worker thread with no event loop of its own).

**Caught live (Tahap 23 verification), not assumed away**: unlike MCP's
tools, this one touches a *pre-existing* global async resource —
`db.connection.AsyncSessionFactory`'s engine is built once, on the main
event loop (uvicorn's). `asyncio.run()` inside the worker thread spins up
a brand-new loop; asyncpg connections/Futures are bound to the loop that
created them, so reusing the global factory from here raised "Future
attached to a different loop" against the real Postgres backend the first
time this was tried against a live server. Fix: the sync wrappers build a
**fresh, short-lived engine** from `settings.DATABASE_URL` per call
(disposed after) instead of reusing the global factory — `_list_files`/
`_read_file` still default to the global `AsyncSessionFactory` when called
directly (same-loop callers, e.g. a future async call site, or tests that
inject their own factory already on the right loop).

Scoped to document files only (pdf/txt/md/log/docx/doc/csv/json — the same
categories `workspace/indexer.py` already indexes). Images/GIS Workspace
files are Bab 69.5's "Vision" row, a separate integration (tool results are
JSON text fed back to the model today, not vision input) — explicitly left
as a follow-up gap, not attempted here.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from sqlalchemy import select

from db.connection import AsyncSessionFactory
from db.models import Workspace, WorkspaceFolder
from tools.adapters.filesystem import FilesystemAdapter
from workspace.indexer import extract_text


async def _list_files(workspace_id: str, session_factory=None) -> Dict[str, Any]:
    session_factory = session_factory or AsyncSessionFactory
    async with session_factory() as session:
        ws = await session.get(Workspace, workspace_id)
        if ws is None or ws.deleted_at is not None:
            return {"success": False, "error": "Workspace tidak ditemukan."}
        result = await session.execute(select(WorkspaceFolder).where(WorkspaceFolder.workspace_id == workspace_id))
        folders = result.scalars().all()

    files = []
    for folder in folders:
        if folder.source_type != "Local":
            continue
        try:
            adapter = FilesystemAdapter(folder.path)
        except NotADirectoryError:
            continue
        for f in adapter.list_tree():
            files.append(
                {
                    "folder_id": folder.id,
                    "folder_alias": folder.alias,
                    "relative_path": f.relative_path,
                    "category": f.category,
                    "size_bytes": f.size_bytes,
                }
            )
    return {"success": True, "files": files, "text": f"{len(files)} file ditemukan di Workspace."}


async def _read_file(
    workspace_id: str, folder_id: str, relative_path: str, session_factory=None
) -> Dict[str, Any]:
    session_factory = session_factory or AsyncSessionFactory
    async with session_factory() as session:
        folder = await session.get(WorkspaceFolder, folder_id)
        if folder is None or folder.workspace_id != workspace_id:
            return {"success": False, "error": "Folder tidak ditemukan di Workspace ini."}
        folder_path, source_type = folder.path, folder.source_type

    if source_type != "Local":
        return {"success": False, "error": f"source_type={source_type!r} belum didukung."}
    try:
        adapter = FilesystemAdapter(folder_path)
        text = extract_text(adapter, relative_path)
    except Exception as e:
        return {"success": False, "error": str(e)}
    if text is None:
        return {
            "success": False,
            "error": (
                "Tipe file tidak didukung atau gagal dibaca sebagai teks "
                "(gambar/GIS di Workspace belum bisa dibaca lewat tool ini)."
            ),
        }
    return {"success": True, "path": relative_path, "text": text[:10000], "truncated": len(text) > 10000}


def _build_fresh_engine():
    """A new engine/session-factory pair bound to whatever loop calls it —
    see module docstring on why the global AsyncSessionFactory can't be
    reused from inside asyncio.run(). Caller must dispose the engine."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from api.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def workspace_list_files(workspace_id: str) -> Dict[str, Any]:
    """Daftar semua file di Project Workspace. ``workspace_id`` selalu
    disuntik oleh `ChatEngine._run_tool` dari sesi yang sudah diotorisasi —
    lihat modul docstring."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _list_files(workspace_id, session_factory=factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_read_file(workspace_id: str, folder_id: str, relative_path: str) -> Dict[str, Any]:
    """Baca isi satu file dari Project Workspace. ``workspace_id`` selalu
    disuntik oleh `ChatEngine._run_tool` — lihat modul docstring."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _read_file(workspace_id, folder_id, relative_path, session_factory=factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())
