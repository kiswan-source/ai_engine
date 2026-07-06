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

Document files (pdf/txt/md/log/docx/doc/csv/json — the same categories
`workspace/indexer.py` already indexes) go through `extract_text()`.

Image and GIS files (Bab 69.5's "Vision" row, Tahap 29) are handled here
too, reusing existing machinery rather than inventing new parsing:
- **image**: read raw bytes + base64-encode, same shape uploaded images
  already use (`core/chat/engine.py::_build_user_message`'s `images_b64`).
  `core/chat/engine.py::stream_run` is what turns this into a real vision
  turn — this module only produces the data, it doesn't know about
  Ollama's message format.
- **gis** (kml/geojson/shp/zip): reuses `agent/tools/gis_io.py`'s
  `_load_any_fc()`/`_summarize_fc()` — the exact same compact
  area/centroid/bbox summary `read_kml`/`read_geojson`/`read_shp` already
  produce, not a raw coordinate dump (see the `gis-tool-output-consistency`
  lesson: dumping full geometry buried the numbers the model needed).

Workspace Write Access (Bab 69.7 `write_output`, Tahap 30): `workspace_write_file`
creates/overwrites/appends a **plain-text** file (txt/md/log/csv/json/html
— the same categories `TEXT_READERS` reads, minus pdf/docx/doc, which are
binary formats `agent/tools/writers.py` generates through ReportLab/
python-docx, not a raw text write) back into the Workspace folder itself,
via `FilesystemAdapter.write_text()` — the actual "edit files in your
project folder" capability the Bab 69.7 permission table anticipated but
nothing implemented until now. RBAC for this one is NOT re-derived here
(same "agent/tools/ must not import from api/" rule as `_read_file`) —
`core/chat/engine.py._run_tool` checks the caller's Project role against
`write_output` *before* calling this, using the role `api/routes/chat.py`
already resolved once at bind time (cached on `Session.workspace_role`,
same shape as `Session.workspace_id`).
"""
from __future__ import annotations

import asyncio
import base64
import mimetypes
from typing import Any, Dict

from sqlalchemy import select

from agent.tools.gis_io import _load_any_fc, _summarize_fc
from db.connection import AsyncSessionFactory
from db.models import Workspace, WorkspaceFolder
from tools.adapters.filesystem import FilesystemAdapter, classify
from tools.tool_validator import PathEscapesRootError
from workspace.indexer import extract_text

# Bab 69.7 Workspace Write Access is scoped to plain-text formats this pass
# — pdf/docx/doc need their own generators (agent/tools/writers.py), not a
# raw text write; documented as a follow-up, not attempted here.
WRITABLE_EXTENSIONS = {"txt", "md", "log", "csv", "json", "html"}


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
        category = classify(relative_path)
        abs_path = adapter.absolute_path(relative_path)

        if category == "document":
            text = extract_text(adapter, relative_path)
            if text is None:
                return {"success": False, "error": "File dokumen ini gagal dibaca sebagai teks."}
            return {"success": True, "path": relative_path, "type": "document",
                    "text": text[:10000], "truncated": len(text) > 10000}

        if category == "image":
            with open(abs_path, "rb") as fh:
                data = fh.read()
            mime_type, _ = mimetypes.guess_type(relative_path)
            return {
                "success": True, "path": relative_path, "type": "image",
                "image_base64": base64.b64encode(data).decode(),
                "mime_type": mime_type or "application/octet-stream",
                "text": f"Gambar dari Workspace: {relative_path}",
            }

        if category == "gis":
            fc = _load_any_fc(str(abs_path))
            summary = _summarize_fc(fc)
            return {"success": True, "path": relative_path, "type": "gis", **summary}

        return {
            "success": False,
            "error": "Tipe file tidak didukung (bukan dokumen, gambar, atau GIS yang dikenali).",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _write_file(
    workspace_id: str, folder_id: str, relative_path: str, content: str,
    mode: str = "overwrite", session_factory=None,
) -> Dict[str, Any]:
    session_factory = session_factory or AsyncSessionFactory
    async with session_factory() as session:
        folder = await session.get(WorkspaceFolder, folder_id)
        if folder is None or folder.workspace_id != workspace_id:
            return {"success": False, "error": "Folder tidak ditemukan di Workspace ini."}
        folder_path, source_type = folder.path, folder.source_type

    if source_type != "Local":
        return {"success": False, "error": f"source_type={source_type!r} belum didukung."}

    ext = relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""
    if ext not in WRITABLE_EXTENSIONS:
        return {
            "success": False,
            "error": f"Hanya bisa menulis file teks ({'/'.join(sorted(WRITABLE_EXTENSIONS))}).",
        }
    if mode not in ("overwrite", "append"):
        return {"success": False, "error": f"mode={mode!r} tidak dikenal (pakai 'overwrite' atau 'append')."}

    try:
        adapter = FilesystemAdapter(folder_path)
        path = adapter.write_text(relative_path, content, mode="a" if mode == "append" else "w")
        return {"success": True, "path": relative_path, "action": mode, "size": path.stat().st_size}
    except PathEscapesRootError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


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


def workspace_write_file(
    workspace_id: str, folder_id: str, relative_path: str, content: str, mode: str = "overwrite"
) -> Dict[str, Any]:
    """Tulis (buat/timpa/tambah) satu file teks di Project Workspace.
    ``workspace_id`` selalu disuntik oleh `ChatEngine._run_tool`; izin
    ``write_output`` dicek DI SANA sebelum fungsi ini pernah dipanggil —
    lihat modul docstring."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _write_file(workspace_id, folder_id, relative_path, content, mode, session_factory=factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())
