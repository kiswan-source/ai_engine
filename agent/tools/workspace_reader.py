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
creates/overwrites/appends a plain-text file (txt/md/log/csv/json/html —
the same categories `TEXT_READERS` reads) back into the Workspace folder
itself, via `FilesystemAdapter.write_text()` — the actual "edit files in
your project folder" capability the Bab 69.7 permission table anticipated
but nothing implemented until now. RBAC for this one is NOT re-derived
here (same "agent/tools/ must not import from api/" rule as `_read_file`)
— `core/chat/engine.py._run_tool` checks the caller's Project role against
`write_output` *before* calling this, using the role `api/routes/chat.py`
already resolved once at bind time (cached on `Session.workspace_role`,
same shape as `Session.workspace_id`).

PDF/DOCX Workspace writes (Tahap 33): reuses `agent/tools/writers.py`'s
`write_pdf`/`write_docx` UNCHANGED rather than re-implementing document
generation — those functions' `_path(filename)` helper already writes to
`filename` as-is whenever it has a directory component (every `write_*`
function in that module shares this), so calling them with the
Workspace-resolved absolute path (instead of a bare filename) makes them
land inside the Workspace folder instead of `~/ai_engine/reports/`, no
changes to that module needed. `mode="append"` is rejected for these two
extensions — ReportLab/python-docx have no sane way to append to an
existing binary document.

Automatic versioning (Fase 4, DCF v5 mandate "Workspace Autonomous
Capability"): before this Tahap, an overwrite of an existing file was
silent and unrecoverable — `FilesystemAdapter.write_text(mode="w")` just
replaced the content with no trace of what was there before. `_write_file`
now snapshots the file's current bytes to `workspace/versioning.py` (a new
`WorkspaceFileVersion` row) BEFORE overwriting it — but only when the
target already exists; a brand-new file has nothing to snapshot. The
result's `action` field is `"created"` or `"overwritten"` (not a generic
`mode` echo) so the model/user can tell which actually happened — the
"tidak boleh ada silent modification" mandate requirement. Every write
(create or overwrite) is also recorded to `security.audit_log`. Restoring
a saved version is deliberately NOT a chat tool — see
`api/routes/workspace.py`'s versions/restore endpoints and
`workspace/versioning.py`'s module docstring for why. Known, accepted
limitation: this is automatic-snapshot-then-write, not a live
pause-and-confirm approval before the overwrite happens — Owner chose this
over a full in-chat approval flow (Fase 4 design decision) to avoid a much
larger SSE-protocol + frontend change for this pass.
"""
from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
from typing import Any, Dict

from sqlalchemy import select

import db.connection as db_connection
from agent.tools.gis_io import _load_any_fc, _summarize_fc
from db.models import Workspace, WorkspaceFolder
from security import audit_log
from tools.adapters.filesystem import FilesystemAdapter, classify
from tools.tool_validator import PathEscapesRootError
from workspace.indexer import extract_text
from workspace.versioning import save_version

# Fase 8 (DCF v5 mandate "Workspace Native File Access & Chat UX Repair",
# Slice 1) note on scope: this Slice adds the safe, reversible parts of the
# mandate — search/move/rename/copy/create-folder. Delete is deliberately
# NOT here (Owner decision, Gate 1: gated behind a two-step confirmation
# token, a separate Slice) and xlsx/pptx/format-preserving DOCX+PDF edit are
# separate Slices too (new dependencies + higher design risk). Drive access
# (D:\, E:\, F:\) is unaffected by this file — every function below already
# works with whatever root path a WorkspaceFolder is registered with; making
# a Windows drive reachable from wherever this process runs is a deployment/
# mount decision the Owner deferred, not something fixed in code.

# Plain-text formats write raw content directly.
WRITABLE_EXTENSIONS = {"txt", "md", "log", "csv", "json", "html"}
# pdf/docx (Tahap 33) reuse agent/tools/writers.py's real generators
# (ReportLab/python-docx) instead of a raw text write — see _write_file.
WRITABLE_DOCUMENT_EXTENSIONS = {"pdf", "docx"}


def _default_title(relative_path: str) -> str:
    base = relative_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return base.replace("_", " ").replace("-", " ").title()


async def _list_files(workspace_id: str, session_factory=None) -> Dict[str, Any]:
    session_factory = session_factory or db_connection.AsyncSessionFactory
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
    session_factory = session_factory or db_connection.AsyncSessionFactory
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


async def _find_file(workspace_id: str, filename: str, session_factory=None) -> Dict[str, Any]:
    """Smart Search (mandate §Smart Search) — case-insensitive substring
    match on filename across every Local folder registered to this
    Workspace, not just one. Always ``success: True`` (the search itself
    ran) — an empty ``matches`` list is a valid outcome the caller/model
    decides how to act on (STEP 3/4 of the mandate's Chat Decision Flow),
    not a tool failure."""
    session_factory = session_factory or db_connection.AsyncSessionFactory
    async with session_factory() as session:
        ws = await session.get(Workspace, workspace_id)
        if ws is None or ws.deleted_at is not None:
            return {"success": False, "error": "Workspace tidak ditemukan."}
        result = await session.execute(select(WorkspaceFolder).where(WorkspaceFolder.workspace_id == workspace_id))
        folders = result.scalars().all()

    matches = []
    searched = []
    for folder in folders:
        if folder.source_type != "Local":
            continue
        searched.append(folder.alias or folder.path)
        try:
            adapter = FilesystemAdapter(folder.path)
        except NotADirectoryError:
            continue
        for f in adapter.search(filename):
            matches.append({
                "folder_id": folder.id, "folder_alias": folder.alias,
                "relative_path": f.relative_path, "category": f.category, "size_bytes": f.size_bytes,
            })
    return {
        "success": True, "matches": matches, "searched_folders": searched,
        "text": f"{len(matches)} file cocok dengan {filename!r} di {len(searched)} folder Workspace.",
    }


async def _create_folder(
    workspace_id: str, folder_id: str, relative_path: str, actor: str = "anonymous", session_factory=None,
) -> Dict[str, Any]:
    session_factory = session_factory or db_connection.AsyncSessionFactory
    async with session_factory() as session:
        folder = await session.get(WorkspaceFolder, folder_id)
        if folder is None or folder.workspace_id != workspace_id:
            return {"success": False, "error": "Folder tidak ditemukan di Workspace ini."}
        if folder.source_type != "Local":
            return {"success": False, "error": f"source_type={folder.source_type!r} belum didukung."}
        try:
            adapter = FilesystemAdapter(folder.path)
            path = adapter.make_dir(relative_path)
        except PathEscapesRootError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}
    await audit_log.record(
        "workspace.folder_created", actor=actor,
        detail={"workspace_id": workspace_id, "folder_id": folder_id, "path": relative_path},
    )
    return {"success": True, "path": relative_path, "text": f"Folder {relative_path!r} dibuat."}


# Serializes the check-then-act (exists? -> snapshot -> move/copy) sequence
# in _move_or_copy per (workspace_id, folder_id, dst_relative_path) — without
# this, two concurrent calls targeting the same not-yet-existing destination
# both observe exists()==False, both skip the version snapshot, and whichever
# move/copy runs second silently clobbers the first with no recovery, exactly
# the "silent unrecoverable overwrite" Fase 4 was built to prevent (caught in
# adversarial review, not the original design — see git history). In-process
# only, matching this codebase's existing single-process assumption
# (`ChatEngine.sessions` is an in-memory dict, same posture) — does not
# protect across multiple uvicorn workers/processes. Entries are never
# evicted (unbounded growth over process lifetime), but each is one tiny
# asyncio.Lock keyed by strings; revisit only if this ever matters in practice.
_move_copy_locks: dict[tuple[str, str, str], "asyncio.Lock"] = {}


def _lock_for(workspace_id: str, folder_id: str, dst_relative_path: str):
    import asyncio as _asyncio

    key = (workspace_id, folder_id, dst_relative_path)
    lock = _move_copy_locks.get(key)
    if lock is None:
        lock = _asyncio.Lock()
        _move_copy_locks[key] = lock
    return lock


async def _move_or_copy(
    workspace_id: str, folder_id: str, src_relative_path: str, dst_relative_path: str,
    op: str, overwrite: bool, actor: str, session_factory=None,
) -> Dict[str, Any]:
    """Shared implementation for move/rename and copy — same shape (one
    WorkspaceFolder root, both paths validated through Root Restriction),
    differing only in which `FilesystemAdapter` method actually runs."""
    session_factory = session_factory or db_connection.AsyncSessionFactory
    async with session_factory() as session:
        folder = await session.get(WorkspaceFolder, folder_id)
        if folder is None or folder.workspace_id != workspace_id:
            return {"success": False, "error": "Folder tidak ditemukan di Workspace ini."}
        if folder.source_type != "Local":
            return {"success": False, "error": f"source_type={folder.source_type!r} belum didukung."}
        async with _lock_for(workspace_id, folder_id, dst_relative_path):
            try:
                adapter = FilesystemAdapter(folder.path)
                if adapter.exists(dst_relative_path):
                    if not overwrite:
                        return {
                            "success": False,
                            "error": f"{dst_relative_path!r} sudah ada. Set overwrite=true untuk menimpanya.",
                        }
                    # Only a file can be safely version-snapshotted (Fase 4's
                    # WorkspaceFileVersion stores one file's bytes) — a folder
                    # destination is refused rather than silently merged.
                    if adapter.absolute_path(dst_relative_path).is_dir():
                        return {"success": False, "error": f"{dst_relative_path!r} adalah folder yang sudah ada."}
                    await _snapshot_if_exists(session, workspace_id, folder_id, dst_relative_path, adapter, actor)
                fn = adapter.move if op == "move" else adapter.copy
                fn(src_relative_path, dst_relative_path)
            except (PathEscapesRootError, FileNotFoundError) as e:
                return {"success": False, "error": str(e)}
            except Exception as e:
                return {"success": False, "error": str(e)}
    await audit_log.record(
        f"workspace.file_{op}d" if op == "move" else "workspace.file_copied", actor=actor,
        detail={"workspace_id": workspace_id, "folder_id": folder_id,
                "src": src_relative_path, "dst": dst_relative_path},
    )
    return {"success": True, "src": src_relative_path, "dst": dst_relative_path}


async def _copy_generated_file_into_workspace(
    workspace_id: str, source_abs_path: str, actor: str = "anonymous", session_factory=None,
) -> Dict[str, Any]:
    """Fase 11 fix — after a general write_* tool (write_docx/write_pdf/
    write_txt/write_html/write_json/write_geojson/write_shp) generates a
    file in `~/ai_engine/reports/`, `ChatEngine._run_tool` calls this to
    also copy it into the connected Workspace's first Local folder, same
    basename — so the user never has to download a report and re-upload it
    into their project folder by hand just because the model happened to
    call a non-Workspace-aware writer instead of `workspace_write_file`
    (the same tool-selection unreliability already worked around for reads
    in `core/chat/engine.py::_auto_resolve_workspace_file`). If a file with
    that name already exists in the Workspace, its previous content is
    version-snapshotted first (same `WorkspaceFileVersion` mechanism
    `_write_file` uses) — never a silent clobber."""
    session_factory = session_factory or db_connection.AsyncSessionFactory
    filename = os.path.basename(source_abs_path)
    async with session_factory() as session:
        ws = await session.get(Workspace, workspace_id)
        if ws is None or ws.deleted_at is not None:
            return {"success": False, "error": "Workspace tidak ditemukan."}
        result = await session.execute(
            select(WorkspaceFolder).where(
                WorkspaceFolder.workspace_id == workspace_id, WorkspaceFolder.source_type == "Local"
            )
        )
        folder = result.scalars().first()
        if folder is None:
            return {"success": False, "error": "Tidak ada folder Local di Workspace ini."}
        # Gate 2 fix: same TOCTOU class as _write_file/_move_or_copy — lock
        # around the same check-then-act sequence before it can silently
        # clobber a concurrent write to the same destination.
        async with _lock_for(workspace_id, folder.id, filename):
            try:
                adapter = FilesystemAdapter(folder.path)
                with open(source_abs_path, "rb") as fh:
                    data = fh.read()
                versioned = await _snapshot_if_exists(session, workspace_id, folder.id, filename, adapter, actor)
                adapter.write_bytes(filename, data)
            except (PathEscapesRootError, OSError) as e:
                return {"success": False, "error": str(e)}
        folder_id = folder.id
    await audit_log.record(
        "workspace.file_written", actor=actor,
        detail={"workspace_id": workspace_id, "folder_id": folder_id, "path": filename,
                "action": "overwritten" if versioned else "created", "source": "auto_copy_from_report"},
    )
    return {"success": True, "relative_path": filename, "folder_id": folder_id}


async def _snapshot_if_exists(
    session, workspace_id: str, folder_id: str, relative_path: str, adapter: FilesystemAdapter, actor: str,
) -> bool:
    """Save the file's current bytes as a version BEFORE it's overwritten —
    no-op (returns False) if the file doesn't exist yet, since a brand-new
    file has nothing to snapshot. Returns whether a version was saved."""
    abs_path = adapter.absolute_path(relative_path)
    if not abs_path.exists():
        return False
    current_bytes = adapter.read_bytes(relative_path)
    await save_version(session, workspace_id, folder_id, relative_path, current_bytes, actor=actor)
    return True


async def _write_file(
    workspace_id: str, folder_id: str, relative_path: str, content: str,
    mode: str = "overwrite", title: str | None = None, actor: str = "anonymous", session_factory=None,
) -> Dict[str, Any]:
    session_factory = session_factory or db_connection.AsyncSessionFactory
    async with session_factory() as session:
        folder = await session.get(WorkspaceFolder, folder_id)
        if folder is None or folder.workspace_id != workspace_id:
            return {"success": False, "error": "Folder tidak ditemukan di Workspace ini."}
        folder_path, source_type = folder.path, folder.source_type

        if source_type != "Local":
            return {"success": False, "error": f"source_type={source_type!r} belum didukung."}

        ext = relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""
        if ext not in WRITABLE_EXTENSIONS and ext not in WRITABLE_DOCUMENT_EXTENSIONS:
            supported = sorted(WRITABLE_EXTENSIONS | WRITABLE_DOCUMENT_EXTENSIONS)
            return {"success": False, "error": f"Tipe file tidak didukung untuk menulis ({'/'.join(supported)})."}
        if mode not in ("overwrite", "append"):
            return {"success": False, "error": f"mode={mode!r} tidak dikenal (pakai 'overwrite' atau 'append')."}
        if ext in WRITABLE_DOCUMENT_EXTENSIONS and mode == "append":
            return {"success": False, "error": f"Mode 'append' tidak didukung untuk .{ext} (cuma 'overwrite')."}

        # Gate 2 fix: same TOCTOU class _move_or_copy was already locked
        # against — two concurrent overwrite-mode writes to the same new
        # relative_path could both observe "doesn't exist yet" and both skip
        # the version snapshot. Scope the lock to the same check-then-act
        # sequence (snapshot-if-exists through the actual write).
        async with _lock_for(workspace_id, folder_id, relative_path):
            try:
                adapter = FilesystemAdapter(folder_path)
                # Fase 4: overwriting an append is a no-op for versioning purposes
                # too (append never destroys prior content) — only a genuine
                # overwrite of an existing file needs a pre-write snapshot.
                versioned = False
                if mode == "overwrite":
                    versioned = await _snapshot_if_exists(session, workspace_id, folder_id, relative_path, adapter, actor)
                action = "overwritten" if versioned else "created"

                if ext in WRITABLE_DOCUMENT_EXTENSIONS:
                    from agent.tools.writers import write_docx, write_pdf

                    abs_path = str(adapter.absolute_path(relative_path))
                    generator = write_pdf if ext == "pdf" else write_docx
                    result = generator(abs_path, title or _default_title(relative_path), content)
                    if not result.get("success"):
                        return {"success": False, "error": result.get("error", "Gagal membuat dokumen.")}
                    await audit_log.record(
                        "workspace.file_written", actor=actor,
                        detail={"workspace_id": workspace_id, "folder_id": folder_id,
                                "path": relative_path, "action": action},
                    )
                    return {"success": True, "path": relative_path, "action": action,
                             "type": ext, "size": result["size"]}
                path = adapter.write_text(relative_path, content, mode="a" if mode == "append" else "w")
                await audit_log.record(
                    "workspace.file_written", actor=actor,
                    detail={"workspace_id": workspace_id, "folder_id": folder_id,
                            "path": relative_path, "action": "appended" if mode == "append" else action},
                )
                return {"success": True, "path": relative_path,
                         "action": "appended" if mode == "append" else action, "size": path.stat().st_size}
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
    workspace_id: str, folder_id: str, relative_path: str, content: str,
    mode: str = "overwrite", title: str | None = None, actor: str | None = None,
) -> Dict[str, Any]:
    """Tulis (buat/timpa/tambah) satu file di Project Workspace — teks
    apa adanya, atau PDF/DOCX sungguhan (Tahap 33) kalau ekstensinya
    begitu (``title`` cuma dipakai untuk PDF/DOCX). ``workspace_id`` selalu
    disuntik oleh `ChatEngine._run_tool`; izin ``write_output`` dicek DI
    SANA sebelum fungsi ini pernah dipanggil — lihat modul docstring.
    ``actor`` (Fase 4, same injection rule) identifies who triggered an
    overwrite, for the version snapshot and audit log entry."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _write_file(
                workspace_id, folder_id, relative_path, content, mode, title,
                actor=actor or "anonymous", session_factory=factory,
            )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_find_file(workspace_id: str, filename: str) -> Dict[str, Any]:
    """Cari file berdasarkan nama (atau sebagian nama) di seluruh folder
    Project Workspace ini — Smart Search. ``workspace_id`` selalu disuntik
    oleh `ChatEngine._run_tool` — lihat modul docstring."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _find_file(workspace_id, filename, session_factory=factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_create_folder(
    workspace_id: str, folder_id: str, relative_path: str, actor: str | None = None,
) -> Dict[str, Any]:
    """Buat folder baru di dalam Project Workspace (dan parent-nya kalau
    belum ada). ``workspace_id``/``actor`` selalu disuntik oleh
    `ChatEngine._run_tool` — lihat modul docstring."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _create_folder(workspace_id, folder_id, relative_path, actor or "anonymous", session_factory=factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_move_file(
    workspace_id: str, folder_id: str, src_relative_path: str, dst_relative_path: str,
    overwrite: bool = False, actor: str | None = None,
) -> Dict[str, Any]:
    """Pindahkan ATAU ganti nama satu file/folder di dalam Project Workspace
    (memindahkan ke path lain = 'move'; mengganti nama di folder yang sama =
    'rename' — keduanya operasi filesystem yang sama). ``workspace_id``/
    ``actor`` selalu disuntik oleh `ChatEngine._run_tool`."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _move_or_copy(
                workspace_id, folder_id, src_relative_path, dst_relative_path,
                op="move", overwrite=overwrite, actor=actor or "anonymous", session_factory=factory,
            )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_copy_file(
    workspace_id: str, folder_id: str, src_relative_path: str, dst_relative_path: str,
    overwrite: bool = False, actor: str | None = None,
) -> Dict[str, Any]:
    """Salin satu file/folder di dalam Project Workspace ke path lain,
    sumber tetap ada. ``workspace_id``/``actor`` selalu disuntik oleh
    `ChatEngine._run_tool`."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _move_or_copy(
                workspace_id, folder_id, src_relative_path, dst_relative_path,
                op="copy", overwrite=overwrite, actor=actor or "anonymous", session_factory=factory,
            )
        finally:
            await engine.dispose()

    return asyncio.run(_run())
