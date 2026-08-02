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
`workspace/indexer.py` already indexes) are dispatched directly to their
`agent/tools/readers.py` parser (Fase 15 — not through that module's
`extract_text()`, which collapses the result to a plain string for its own
RAG-indexing use and would throw away the pagination metadata a Workspace
read needs).

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
from contextlib import asynccontextmanager
from typing import Any, Dict

from sqlalchemy import select

import db.connection as db_connection
from agent.tools.gis_io import _load_any_fc, _summarize_fc
from agent.tools.readers import (
    DEFAULT_PAGE_CHARS,
    MAX_BATCH_FILES,
    MAX_LENGTH_PER_FILE,
    _EXTENSION_READERS,
    _PAGINATED_READERS,
    _paginate,
)
from db.models import Workspace, WorkspaceFolder
from security import audit_log
from tools.adapters.filesystem import FilesystemAdapter, classify
from tools.tool_validator import PathEscapesRootError
from workspace.versioning import save_version

# Fase 8 (DCF v5 mandate "Workspace Native File Access & Chat UX Repair",
# Slice 1) note on scope: this Slice adds the safe, reversible parts of the
# mandate — search/move/rename/copy/create-folder. Delete is deliberately
# NOT here (Owner decision, Gate 1: gated behind a two-step confirmation
# token — built as Slice 2, workspace/delete_gate.py) and xlsx/pptx (Slice
# 3, built Fase 12) + format-preserving DOCX+PDF in-place edit (Slice 4,
# still not built) were separate Slices too, for the same reason: new
# dependencies + higher design risk than Slice 1's file-move-shaped
# operations. Drive access (D:\, E:\, F:\) is unaffected by this file —
# every function below already works with whatever root path a
# WorkspaceFolder is registered with; making a Windows drive reachable from
# wherever this process runs is a deployment/mount decision the Owner
# deferred, not something fixed in code.

# Plain-text formats write raw content directly.
WRITABLE_EXTENSIONS = {"txt", "md", "log", "csv", "json", "html"}
# pdf/docx (Tahap 33) and xlsx/pptx (Slice 3, Fase 12) reuse
# agent/tools/writers.py's real generators instead of a raw text write —
# see _write_file. Full-replace only for all four, same as pdf/docx already
# were — in-place edit is Slice 4, not built yet.
WRITABLE_DOCUMENT_EXTENSIONS = {"pdf", "docx", "xlsx", "pptx"}


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
    workspace_id: str, folder_id: str, relative_path: str, session_factory=None,
    offset: int = 0, length: int = DEFAULT_PAGE_CHARS,
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
            # Fase 15: same offset/length pagination as the standalone
            # readers (agent/tools/readers.py) — this had the identical
            # hard-truncate-at-10000-chars bug, found by Gate 1 adversarial
            # review of that Fase's own blueprint, not a separate design.
            # Dispatches directly to the reader (not via workspace/indexer.py
            # ::extract_text, which collapses the result down to a plain
            # `str | None` for its own RAG-indexing use and would silently
            # throw away the has_more/offset/returned_chars metadata this
            # needs — caught by this Fase's own test failing, not designed
            # in from the start).
            ext = os.path.splitext(relative_path)[1].lstrip(".").lower()
            reader = _EXTENSION_READERS.get(ext)
            if reader is None:
                return {"success": False, "error": "File dokumen ini gagal dibaca sebagai teks."}
            if reader in _PAGINATED_READERS:
                item = reader(str(abs_path), offset=offset, length=length)
            else:
                item = reader(str(abs_path))
            if "error" in item:
                return {"success": False, "error": "File dokumen ini gagal dibaca sebagai teks."}
            # Drop the reader's own "source" key (the real absolute host
            # path) — Workspace deliberately never surfaces that to the
            # model/user (same principle as Fase 9's WSL-path-hiding
            # _friendly_path()); "path": relative_path already covers it.
            item.pop("source", None)
            return {"success": True, "path": relative_path, "type": "document", **item}

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
# protect across multiple uvicorn workers/processes. Entries are refcounted
# and evicted once no caller still needs them (Gate 3, 2026-07-23 — this used
# to grow unbounded for the process lifetime; low severity since each entry
# is one tiny asyncio.Lock, but free to fix).
_move_copy_locks: dict[tuple[str, str, str], "asyncio.Lock"] = {}
_move_copy_lock_refcounts: dict[tuple[str, str, str], int] = {}
_move_copy_locks_guard = asyncio.Lock()


@asynccontextmanager
async def _lock_for(workspace_id: str, folder_id: str, dst_relative_path: str):
    key = (workspace_id, folder_id, dst_relative_path)
    async with _move_copy_locks_guard:
        lock = _move_copy_locks.setdefault(key, asyncio.Lock())
        _move_copy_lock_refcounts[key] = _move_copy_lock_refcounts.get(key, 0) + 1
    try:
        async with lock:
            yield
    finally:
        async with _move_copy_locks_guard:
            _move_copy_lock_refcounts[key] -= 1
            if _move_copy_lock_refcounts[key] <= 0:
                _move_copy_lock_refcounts.pop(key, None)
                _move_copy_locks.pop(key, None)


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
                # Gate 3 finding (2026-08-01): unlike shutil.move (which
                # already refuses "move a directory into itself"),
                # shutil.copytree has no such guard — copying a folder into
                # its own subdirectory (e.g. dst doesn't need to exist yet,
                # just needs to be nested under src) makes copytree recurse
                # into the destination it's still creating, burning CPU/disk
                # until Python's recursion limit or an OS path-length error,
                # and leaving an orphaned partial tree on disk with no
                # cleanup. Predates this Fase (shared by the chat tool since
                # Fase 8) but newly trivial to trigger via the REST route's
                # plain HTTP call and the chat-tool/context-menu's
                # free-text destination prompt — closing it here closes it
                # for every caller of this shared function.
                if op == "copy":
                    src_abs = adapter.absolute_path(src_relative_path)
                    if src_abs.is_dir():
                        dst_abs = adapter.absolute_path(dst_relative_path)
                        if dst_abs == src_abs or src_abs in dst_abs.parents:
                            return {
                                "success": False,
                                "error": f"Tidak bisa menyalin folder ke dalam dirinya sendiri atau subfoldernya ({dst_relative_path!r}).",
                            }
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
    mode: str = "overwrite", title: str | None = None, heading: str | None = None,
    actor: str = "anonymous", session_factory=None,
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
        if mode not in ("overwrite", "append", "edit"):
            return {"success": False, "error": f"mode={mode!r} tidak dikenal (pakai 'overwrite', 'append', atau 'edit')."}
        # Workspace Slice 4 (Fase 12, in-place edit): 'edit' (section
        # replace by heading) is docx-only; 'append' (add pages to the end)
        # now also works for pdf alongside the plain-text extensions it
        # already worked for. xlsx/pptx stay full-replace-only — no design
        # was approved for editing those this slice.
        if mode == "edit":
            if ext != "docx":
                return {"success": False, "error": "Mode 'edit' hanya didukung untuk .docx."}
            if not (heading and heading.strip()):
                return {"success": False, "error": "Mode 'edit' butuh argumen 'heading' (nama section yang diedit)."}
        if mode == "append" and ext in WRITABLE_DOCUMENT_EXTENSIONS and ext != "pdf":
            return {"success": False, "error": f"Mode 'append' tidak didukung untuk .{ext} (pakai 'overwrite')."}

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
                # Slice 4: 'edit' and pdf 'append' both rewrite the file's
                # existing bytes in place (unlike text append, which is
                # non-destructively additive via open(path, "a")), so they
                # need the same pre-write snapshot overwrite already gets.
                versioned = False
                if mode == "overwrite" or mode == "edit" or (mode == "append" and ext == "pdf"):
                    versioned = await _snapshot_if_exists(session, workspace_id, folder_id, relative_path, adapter, actor)
                action = "overwritten" if versioned else "created"

                if ext in WRITABLE_DOCUMENT_EXTENSIONS:
                    abs_path = str(adapter.absolute_path(relative_path))

                    if mode == "edit":
                        if not os.path.exists(abs_path):
                            return {"success": False, "error": "Mode 'edit' butuh file .docx yang sudah ada."}
                        from docx import Document

                        from core.document.markdown_render import edit_docx_section

                        doc = Document(abs_path)
                        action = edit_docx_section(doc, heading, content)
                        # Gate 2 fix: write-then-replace, same protection
                        # append_pdf_section already had — a crash/disk-full
                        # during Document.save()'s zip write must never leave
                        # a corrupted .docx in place (recoverable via the
                        # pre-write WorkspaceFileVersion snapshot either way,
                        # but no reason to accept the corruption window when
                        # avoiding it costs one extra os.replace).
                        tmp_abs_path = f"{abs_path}.tmp"
                        doc.save(tmp_abs_path)
                        os.replace(tmp_abs_path, abs_path)
                        result = {"success": True, "size": os.path.getsize(abs_path)}
                    elif mode == "append" and ext == "pdf":
                        from agent.tools.writers import append_pdf_section

                        result = append_pdf_section(abs_path, content, title=title)
                        if not result.get("success"):
                            return {"success": False, "error": result.get("error", "Gagal menambah halaman PDF.")}
                        action = "appended"
                    else:
                        from agent.tools.writers import write_docx, write_pdf, write_pptx, write_xlsx

                        generator = {"pdf": write_pdf, "docx": write_docx, "xlsx": write_xlsx, "pptx": write_pptx}[ext]
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


def workspace_read_file(
    workspace_id: str, folder_id: str, relative_path: str,
    offset: int = 0, length: int = DEFAULT_PAGE_CHARS,
) -> Dict[str, Any]:
    """Baca isi satu file dari Project Workspace. ``workspace_id`` selalu
    disuntik oleh `ChatEngine._run_tool` — lihat modul docstring.

    ``offset``/``length`` (Fase 15): pagination for large documents — call
    again with a bigger ``offset`` (see the response's ``has_more``) to
    continue reading past the first window. Defaults reproduce the old
    hard-truncate-at-10000-chars behavior exactly."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _read_file(
                workspace_id, folder_id, relative_path, session_factory=factory,
                offset=offset, length=length,
            )
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_read_many_files(
    workspace_id: str, folder_id: str, relative_paths, length_per_file: int = 2000,
) -> Dict[str, Any]:
    """Read several files from the same Workspace folder in one call (Fase
    15) — same batching motivation as ``agent.tools.readers.read_many_files``,
    Workspace-scoped. ``workspace_id`` always injected by
    ``ChatEngine._run_tool``, same rule as every other Workspace tool."""
    if isinstance(relative_paths, str):
        relative_paths = [relative_paths]
    if not relative_paths:
        return {"success": False, "error": "relative_paths kosong."}
    length_per_file = max(1, min(length_per_file, MAX_LENGTH_PER_FILE))
    if len(relative_paths) > MAX_BATCH_FILES:
        return {
            "success": False,
            "error": f"Terlalu banyak file sekaligus ({len(relative_paths)}), maksimum "
                     f"{MAX_BATCH_FILES} per panggilan. Bagi jadi beberapa panggilan.",
        }

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            results = []
            for relative_path in relative_paths:
                item = await _read_file(
                    workspace_id, folder_id, relative_path, session_factory=factory,
                    offset=0, length=length_per_file,
                )
                results.append({"relative_path": relative_path, **item})
            ok_count = sum(1 for r in results if r.get("success"))
            return {
                "success": True, "count": len(results), "ok_count": ok_count,
                "text": f"{ok_count}/{len(results)} file berhasil dibaca.",
                "results": results,
            }
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def workspace_write_file(
    workspace_id: str, folder_id: str, relative_path: str, content: str,
    mode: str = "overwrite", title: str | None = None, heading: str | None = None,
    actor: str | None = None,
) -> Dict[str, Any]:
    """Tulis (buat/timpa/tambah/edit) satu file di Project Workspace — teks
    apa adanya, atau PDF/DOCX/XLSX/PPTX sungguhan (Tahap 33, Fase 12) kalau
    ekstensinya begitu (``title`` cuma dipakai untuk dokumen). Mode
    ``"edit"`` (Workspace Slice 4, Fase 12, .docx only) mengganti isi satu
    section — cari paragraf heading yang cocok dengan ``heading``, ganti
    isinya (sampai heading setingkat berikutnya) dengan ``content``,
    heading itu sendiri tak disentuh; kalau ``heading`` belum ada, heading +
    content ditambahkan di akhir dokumen. Mode ``"append"`` untuk .pdf
    (Slice 4) menambah halaman baru di akhir PDF yang sudah ada tanpa
    menyentuh halaman lama sama sekali — beda dari mode ``"edit"``, PDF
    tidak mendukung ganti isi tengah dokumen (lihat
    core/document/markdown_render.py::edit_docx_section's docstring untuk
    alasan lisensi di balik keputusan ini). ``workspace_id`` selalu
    disuntik oleh `ChatEngine._run_tool`; izin ``write_output`` dicek DI
    SANA sebelum fungsi ini pernah dipanggil — lihat modul docstring.
    ``actor`` (Fase 4, same injection rule) identifies who triggered an
    overwrite, for the version snapshot and audit log entry."""

    async def _run():
        engine, factory = _build_fresh_engine()
        try:
            return await _write_file(
                workspace_id, folder_id, relative_path, content, mode, title, heading,
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
