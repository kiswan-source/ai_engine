"""Unit tests for agent/tools/workspace_reader.py (Bab 69.5, Tahap 23) —
the Agent Workspace Context tools exposed to Chat.

Image/GIS category dispatch (Tahap 29) is tested here too — same fixtures,
just new file categories under the same `_read_file` entry point.
"""
import asyncio
import base64
import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.tools.workspace_reader import (
    _copy_generated_file_into_workspace,
    _create_folder,
    _find_file,
    _list_files,
    _move_or_copy,
    _read_file,
    _write_file,
    workspace_copy_file,
    workspace_create_folder,
    workspace_find_file,
    workspace_list_files,
    workspace_move_file,
    workspace_read_file,
    workspace_write_file,
)
from db.models import Workspace, WorkspaceFileVersion, WorkspaceFolder


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Workspace.metadata.create_all,
            tables=[Workspace.__table__, WorkspaceFolder.__table__, WorkspaceFileVersion.__table__],
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def _seed(factory, tmp_path, source_type="Local", project_id=None):
    import uuid

    async with factory() as session:
        ws = Workspace(project_id=project_id or f"p-{uuid.uuid4().hex}", status="Active")
        session.add(ws)
        await session.flush()
        folder = WorkspaceFolder(workspace_id=ws.id, source_type=source_type, path=str(tmp_path), alias="Docs")
        session.add(folder)
        await session.commit()
        return ws.id, folder.id


async def test_list_files_returns_files_from_real_folder(sqlite_session_factory, tmp_path):
    (tmp_path / "report.txt").write_text("laporan lapangan")
    (tmp_path / "site.png").write_bytes(b"\x89PNG")
    workspace_id, _ = await _seed(sqlite_session_factory, tmp_path)

    result = await _list_files(workspace_id, session_factory=sqlite_session_factory)

    assert result["success"] is True
    categories = {f["category"] for f in result["files"]}
    assert categories == {"document", "image"}


async def test_list_files_unknown_workspace(sqlite_session_factory):
    result = await _list_files("does-not-exist", session_factory=sqlite_session_factory)
    assert result["success"] is False
    assert "tidak ditemukan" in result["error"].lower()


async def test_read_file_returns_real_content(sqlite_session_factory, tmp_path):
    (tmp_path / "assay.txt").write_text("kadar emas anomali distrik alpha")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _read_file(workspace_id, folder_id, "assay.txt", session_factory=sqlite_session_factory)

    assert result["success"] is True
    assert result["text"] == "kadar emas anomali distrik alpha"


async def test_read_file_image_returns_base64_and_mime_type(sqlite_session_factory, tmp_path):
    from PIL import Image

    img_path = tmp_path / "site.png"
    Image.new("RGBA", (20, 10), (255, 0, 0, 255)).save(str(img_path))
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _read_file(workspace_id, folder_id, "site.png", session_factory=sqlite_session_factory)

    assert result["success"] is True
    assert result["type"] == "image"
    assert result["mime_type"] == "image/png"
    assert base64.b64decode(result["image_base64"]) == img_path.read_bytes()


async def test_read_file_gis_returns_area_summary_not_raw_coordinates(sqlite_session_factory, tmp_path):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "Blok A"},
         "geometry": {"type": "Polygon", "coordinates": [
             [[110, -7], [110.1, -7], [110.1, -7.1], [110, -7], [110, -7]]]}}]}
    (tmp_path / "blok.geojson").write_text(json.dumps(fc))
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _read_file(workspace_id, folder_id, "blok.geojson", session_factory=sqlite_session_factory)

    assert result["success"] is True
    assert result["type"] == "gis"
    assert result["total_area_ha"] > 0
    assert result["polygon_count"] == 1
    # The compact summary, not a coordinate dump (gis-tool-output-consistency).
    assert "coordinates" not in result


async def test_write_file_creates_new_file(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "catatan.txt", "isi baru", session_factory=sqlite_session_factory
    )

    assert result["success"] is True
    # Fase 4: distinct from "overwritten" — a brand-new file has nothing to
    # snapshot, and the model/user should be able to tell the difference
    # (the "tidak boleh ada silent modification" mandate requirement).
    assert result["action"] == "created"
    assert (tmp_path / "catatan.txt").read_text() == "isi baru"


async def test_write_file_overwrite_replaces_content(sqlite_session_factory, tmp_path):
    (tmp_path / "catatan.txt").write_text("lama")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "catatan.txt", "baru", mode="overwrite", session_factory=sqlite_session_factory
    )

    assert result["success"] is True
    assert result["action"] == "overwritten"
    assert (tmp_path / "catatan.txt").read_text() == "baru"


async def test_write_file_overwrite_saves_a_version_of_the_old_content(sqlite_session_factory, tmp_path):
    """Fase 4 — the whole point: an overwrite must never be silent/
    unrecoverable. The OLD content, not the new one, is what gets snapshotted."""
    from workspace.versioning import list_versions

    (tmp_path / "catatan.txt").write_text("isi lama yang akan hilang")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "catatan.txt", "isi baru", mode="overwrite",
        actor="alice", session_factory=sqlite_session_factory,
    )
    assert result["success"] is True

    async with sqlite_session_factory() as session:
        versions = await list_versions(session, workspace_id, folder_id, "catatan.txt")
    assert len(versions) == 1
    assert versions[0]["actor"] == "alice"
    assert versions[0]["size_bytes"] == len(b"isi lama yang akan hilang")


async def test_write_file_creating_new_file_saves_no_version(sqlite_session_factory, tmp_path):
    """Nothing to snapshot for a file that didn't exist before."""
    from workspace.versioning import list_versions

    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    await _write_file(
        workspace_id, folder_id, "baru.txt", "isi", session_factory=sqlite_session_factory
    )

    async with sqlite_session_factory() as session:
        versions = await list_versions(session, workspace_id, folder_id, "baru.txt")
    assert versions == []


async def test_write_file_append_saves_no_version(sqlite_session_factory, tmp_path):
    """Append never destroys prior content, so no pre-write snapshot is needed."""
    from workspace.versioning import list_versions

    (tmp_path / "catatan.txt").write_text("baris 1\n")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "catatan.txt", "baris 2\n", mode="append", session_factory=sqlite_session_factory
    )
    assert result["action"] == "appended"

    async with sqlite_session_factory() as session:
        versions = await list_versions(session, workspace_id, folder_id, "catatan.txt")
    assert versions == []


async def test_write_file_append_adds_to_existing_content(sqlite_session_factory, tmp_path):
    (tmp_path / "catatan.txt").write_text("baris 1\n")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "catatan.txt", "baris 2\n", mode="append", session_factory=sqlite_session_factory
    )

    assert result["success"] is True
    assert (tmp_path / "catatan.txt").read_text() == "baris 1\nbaris 2\n"


async def test_write_file_rejects_unsupported_extension(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "script.py", "print('x')", session_factory=sqlite_session_factory
    )

    assert result["success"] is False
    assert not (tmp_path / "script.py").exists()


async def test_write_file_rejects_path_traversal(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "../outside.txt", "isi", session_factory=sqlite_session_factory
    )

    assert result["success"] is False
    assert not (tmp_path.parent / "outside.txt").exists()


# ─── PDF/DOCX Workspace writes (Tahap 33) ───────────────────────────────

async def test_write_file_creates_real_pdf_in_workspace_folder(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "laporan.pdf", "# Ringkasan\n\nKadar tembaga 1.85%.",
        title="Laporan Survei", session_factory=sqlite_session_factory,
    )

    assert result["success"] is True
    assert result["type"] == "pdf"
    pdf_path = tmp_path / "laporan.pdf"
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")  # real PDF, not a text stub
    assert result["size"] > 500  # non-trivial ReportLab output, not an empty shell


async def test_write_file_creates_real_docx_in_workspace_folder(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "laporan.docx", "Isi laporan lapangan.",
        session_factory=sqlite_session_factory,  # title omitted -> default from filename
    )

    assert result["success"] is True
    assert result["type"] == "docx"
    docx_path = tmp_path / "laporan.docx"
    assert docx_path.exists()
    assert docx_path.read_bytes().startswith(b"PK")  # docx is a real zip container


async def test_write_file_pdf_rejects_append_mode(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "laporan.pdf", "isi", mode="append", session_factory=sqlite_session_factory
    )

    assert result["success"] is False
    assert not (tmp_path / "laporan.pdf").exists()


async def test_read_file_folder_not_in_workspace(sqlite_session_factory, tmp_path):
    workspace_a, _ = await _seed(sqlite_session_factory, tmp_path)
    _, folder_b = await _seed(sqlite_session_factory, tmp_path)  # second workspace/folder pair

    # folder_b belongs to a *different* workspace than workspace_a.
    result = await _read_file(workspace_a, folder_b, "assay.txt", session_factory=sqlite_session_factory)

    assert result["success"] is False
    assert "tidak ditemukan" in result["error"].lower()


async def test_read_file_unsupported_extension(sqlite_session_factory, tmp_path):
    (tmp_path / "notes.xyz").write_text("unsupported")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _read_file(workspace_id, folder_id, "notes.xyz", session_factory=sqlite_session_factory)

    assert result["success"] is False


async def test_read_file_rejects_non_local_source_type(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path, source_type="Network")

    result = await _read_file(workspace_id, folder_id, "assay.txt", session_factory=sqlite_session_factory)

    assert result["success"] is False
    assert "belum didukung" in result["error"]


# ─── Regression: default session_factory must honor a patched AsyncSessionFactory ─
# Real CI failure, not hypothetical: `from db.connection import AsyncSessionFactory`
# copies the reference at import time, so tests/integration/test_chat_workspace_context_api.py
# monkeypatching db.connection.AsyncSessionFactory never reached any function here
# that defaulted to the bare (stale) name — those functions silently tried the
# REAL configured database instead of the test's sqlite one. Passed locally
# (real Postgres happened to be reachable) but failed in CI (no Postgres at
# all) the first time this code was ever actually pushed. Fixed by importing
# `db.connection` as a module and referencing `db_connection.AsyncSessionFactory`
# at call time instead — this test locks in that the fix actually works.

async def test_default_session_factory_honors_a_later_patched_async_session_factory(
    sqlite_session_factory, tmp_path, monkeypatch
):
    import db.connection as db_connection

    (tmp_path / "notes.txt").write_text("isi asli")
    workspace_id, _ = await _seed(sqlite_session_factory, tmp_path)
    monkeypatch.setattr(db_connection, "AsyncSessionFactory", sqlite_session_factory)

    result = await _find_file(workspace_id, "notes.txt")  # no session_factory passed — must use the default

    assert result["success"] is True
    assert len(result["matches"]) == 1


# ─── Fase 8 (DCF v5 mandate "Workspace Native File Access"), Slice 1 ────────
# Smart Search + create-folder/move/copy — reversible ops only; delete is a
# separate, later Slice (Owner decision: two-step confirmation token).

async def test_find_file_matches_across_multiple_folders(sqlite_session_factory, tmp_path):
    import uuid

    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    (root_a / "Kesimpulan_Tiga_Framework.pdf").write_bytes(b"%PDF-fake")
    (root_b / "other.txt").write_text("x")
    project_id = f"p-{uuid.uuid4().hex}"
    workspace_id, _ = await _seed(sqlite_session_factory, root_a, project_id=project_id)
    async with sqlite_session_factory() as session:
        folder_b = WorkspaceFolder(workspace_id=workspace_id, source_type="Local", path=str(root_b), alias="B")
        session.add(folder_b)
        await session.commit()

    result = await _find_file(workspace_id, "Kesimpulan_Tiga_Framework", session_factory=sqlite_session_factory)

    assert result["success"] is True
    assert len(result["matches"]) == 1
    assert result["matches"][0]["relative_path"] == "Kesimpulan_Tiga_Framework.pdf"
    assert len(result["searched_folders"]) == 2


async def test_find_file_no_match_still_succeeds_with_empty_matches(sqlite_session_factory, tmp_path):
    workspace_id, _ = await _seed(sqlite_session_factory, tmp_path)

    result = await _find_file(workspace_id, "does-not-exist", session_factory=sqlite_session_factory)

    assert result["success"] is True
    assert result["matches"] == []


async def test_create_folder_creates_nested_directory(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _create_folder(workspace_id, folder_id, "Legal/2026", session_factory=sqlite_session_factory)

    assert result["success"] is True
    assert (tmp_path / "Legal" / "2026").is_dir()


async def test_create_folder_rejects_path_traversal(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _create_folder(workspace_id, folder_id, "../escape", session_factory=sqlite_session_factory)

    assert result["success"] is False


async def test_move_renames_file(sqlite_session_factory, tmp_path):
    (tmp_path / "old.txt").write_text("isi")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _move_or_copy(
        workspace_id, folder_id, "old.txt", "new.txt", op="move", overwrite=False,
        actor="alice", session_factory=sqlite_session_factory,
    )

    assert result["success"] is True
    assert not (tmp_path / "old.txt").exists()
    assert (tmp_path / "new.txt").read_text() == "isi"


async def test_move_refuses_existing_destination_without_overwrite(sqlite_session_factory, tmp_path):
    (tmp_path / "src.txt").write_text("baru")
    (tmp_path / "dst.txt").write_text("lama")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _move_or_copy(
        workspace_id, folder_id, "src.txt", "dst.txt", op="move", overwrite=False,
        actor="alice", session_factory=sqlite_session_factory,
    )

    assert result["success"] is False
    assert (tmp_path / "src.txt").exists()  # untouched
    assert (tmp_path / "dst.txt").read_text() == "lama"  # untouched


async def test_move_with_overwrite_snapshots_previous_content(sqlite_session_factory, tmp_path):
    from workspace.versioning import list_versions

    (tmp_path / "src.txt").write_text("baru")
    (tmp_path / "dst.txt").write_text("lama yang akan hilang")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _move_or_copy(
        workspace_id, folder_id, "src.txt", "dst.txt", op="move", overwrite=True,
        actor="alice", session_factory=sqlite_session_factory,
    )

    assert result["success"] is True
    assert (tmp_path / "dst.txt").read_text() == "baru"
    async with sqlite_session_factory() as session:
        versions = await list_versions(session, workspace_id, folder_id, "dst.txt")
    assert len(versions) == 1
    assert versions[0]["actor"] == "alice"


async def test_move_missing_source_fails(sqlite_session_factory, tmp_path):
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _move_or_copy(
        workspace_id, folder_id, "does-not-exist.txt", "new.txt", op="move", overwrite=False,
        actor="alice", session_factory=sqlite_session_factory,
    )

    assert result["success"] is False


async def test_copy_leaves_source_file_intact(sqlite_session_factory, tmp_path):
    (tmp_path / "src.txt").write_text("isi")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _move_or_copy(
        workspace_id, folder_id, "src.txt", "copy.txt", op="copy", overwrite=False,
        actor="alice", session_factory=sqlite_session_factory,
    )

    assert result["success"] is True
    assert (tmp_path / "src.txt").exists()
    assert (tmp_path / "copy.txt").read_text() == "isi"


async def test_concurrent_moves_to_same_destination_do_not_silently_clobber(sqlite_session_factory, tmp_path):
    """Adversarial-review finding: two concurrent calls targeting the same
    not-yet-existing destination must not both observe exists()==False and
    both skip the version snapshot — exactly one must win, the other must
    be refused (not silently overwritten with no recovery)."""
    (tmp_path / "src1.txt").write_text("dari src1")
    (tmp_path / "src2.txt").write_text("dari src2")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    results = await asyncio.gather(
        _move_or_copy(workspace_id, folder_id, "src1.txt", "dst.txt", op="move", overwrite=False,
                       actor="a", session_factory=sqlite_session_factory),
        _move_or_copy(workspace_id, folder_id, "src2.txt", "dst.txt", op="move", overwrite=False,
                       actor="b", session_factory=sqlite_session_factory),
    )

    successes = [r for r in results if r["success"]]
    failures = [r for r in results if not r["success"]]
    assert len(successes) == 1
    assert len(failures) == 1
    assert "sudah ada" in failures[0]["error"]
    # The losing move's source file must still exist untouched — it was
    # refused, not silently discarded.
    losing_src = "src1.txt" if failures[0] is results[0] else "src2.txt"
    assert (tmp_path / losing_src).exists()


async def test_move_rejects_path_traversal_on_destination(sqlite_session_factory, tmp_path):
    (tmp_path / "src.txt").write_text("isi")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _move_or_copy(
        workspace_id, folder_id, "src.txt", "../outside.txt", op="move", overwrite=False,
        actor="alice", session_factory=sqlite_session_factory,
    )

    assert result["success"] is False
    assert (tmp_path / "src.txt").exists()


# ─── Fase 11 fix: auto-copy a generated report into the connected Workspace ─
# Real report: write_docx (a general, non-Workspace-aware writer) produced a
# real docx while a Workspace was connected, and it landed only in
# ~/ai_engine/reports/ — the user had to download it and re-upload it by hand.

async def test_copy_generated_file_into_workspace_creates_it(sqlite_session_factory, tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()
    source = reports_dir / "laporan.docx"
    source.write_bytes(b"fake docx bytes")
    workspace_id, folder_id = await _seed(sqlite_session_factory, workspace_dir)

    result = await _copy_generated_file_into_workspace(
        workspace_id, str(source), actor="alice", session_factory=sqlite_session_factory
    )

    assert result["success"] is True
    assert result["relative_path"] == "laporan.docx"
    assert result["folder_id"] == folder_id
    assert (workspace_dir / "laporan.docx").read_bytes() == b"fake docx bytes"
    # The source report copy is untouched (not moved).
    assert source.exists()


async def test_copy_generated_file_into_workspace_versions_existing_file(sqlite_session_factory, tmp_path):
    from workspace.versioning import list_versions

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()
    (workspace_dir / "laporan.docx").write_bytes(b"versi lama")
    source = reports_dir / "laporan.docx"
    source.write_bytes(b"versi baru")
    workspace_id, folder_id = await _seed(sqlite_session_factory, workspace_dir)

    result = await _copy_generated_file_into_workspace(
        workspace_id, str(source), actor="alice", session_factory=sqlite_session_factory
    )

    assert result["success"] is True
    assert (workspace_dir / "laporan.docx").read_bytes() == b"versi baru"
    async with sqlite_session_factory() as session:
        versions = await list_versions(session, workspace_id, folder_id, "laporan.docx")
    assert len(versions) == 1
    assert versions[0]["actor"] == "alice"


async def test_copy_generated_file_into_workspace_unknown_workspace_fails(sqlite_session_factory, tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    source = reports_dir / "laporan.docx"
    source.write_bytes(b"x")

    result = await _copy_generated_file_into_workspace(
        "does-not-exist", str(source), actor="alice", session_factory=sqlite_session_factory
    )

    assert result["success"] is False


# ─── sync wrappers for the new tools ────────────────────────────────────────

def test_sync_wrapper_find_file(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "Laporan_Akhir.pdf").write_bytes(b"%PDF-fake")
    db_path, (workspace_id, _) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_find_file(workspace_id, "Laporan_Akhir")

    assert result["success"] is True
    assert len(result["matches"]) == 1


def test_sync_wrapper_create_folder(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    db_path, (workspace_id, folder_id) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_create_folder(workspace_id, folder_id, "New")

    assert result["success"] is True
    assert (content_dir / "New").is_dir()


def test_sync_wrapper_move_file(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "old.txt").write_text("isi")
    db_path, (workspace_id, folder_id) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_move_file(workspace_id, folder_id, "old.txt", "new.txt")

    assert result["success"] is True
    assert (content_dir / "new.txt").exists()


def test_sync_wrapper_copy_file(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "src.txt").write_text("isi")
    db_path, (workspace_id, folder_id) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_copy_file(workspace_id, folder_id, "src.txt", "copy.txt")

    assert result["success"] is True
    assert (content_dir / "src.txt").exists()
    assert (content_dir / "copy.txt").exists()


# ─── sync wrappers (the asyncio.run plumbing actually registered as tools) ──
#
# Plain (non-async) test functions on purpose: workspace_list_files/
# workspace_read_file call asyncio.run() internally, which raises if called
# from inside an already-running loop (a pytest-asyncio async test has one).
# A file-backed sqlite DB (not :memory:): the sync wrappers build a *fresh*
# engine per call from settings.DATABASE_URL (see workspace_reader.py's
# module docstring — reusing the global AsyncSessionFactory here raised a
# real "attached to a different loop" error against Postgres, caught in
# live verification) — a real file lets that fresh engine see data seeded
# by a separate engine/loop; :memory: would not.

def _setup_sqlite_file(tmp_path, folder_path, source_type="Local"):
    # db file lives directly in tmp_path; folder_path (the Workspace Folder
    # being scanned) must be a *separate* subdirectory, or list_tree() would
    # also pick up the sqlite db file itself as a stray "other"-category file.
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Workspace.metadata.create_all, tables=[Workspace.__table__, WorkspaceFolder.__table__])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            ws = Workspace(project_id="p1", status="Active")
            session.add(ws)
            await session.flush()
            folder = WorkspaceFolder(workspace_id=ws.id, source_type=source_type, path=str(folder_path))
            session.add(folder)
            await session.commit()
            return ws.id, folder.id

    return db_path, asyncio.run(_init())


def test_sync_wrapper_list_files_via_asyncio_run(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "report.txt").write_text("isi laporan")
    db_path, (workspace_id, _) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_list_files(workspace_id)

    assert result["success"] is True
    assert len(result["files"]) == 1


def test_sync_wrapper_read_file_via_asyncio_run(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "report.txt").write_text("isi laporan sungguhan")
    db_path, (workspace_id, folder_id) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_read_file(workspace_id, folder_id, "report.txt")

    assert result["success"] is True
    assert result["text"] == "isi laporan sungguhan"


def test_sync_wrapper_write_file_via_asyncio_run(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    db_path, (workspace_id, folder_id) = _setup_sqlite_file(tmp_path, content_dir)
    monkeypatch.setattr("api.config.settings.DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")

    result = workspace_write_file(workspace_id, folder_id, "baru.txt", "ditulis lewat sync wrapper")

    assert result["success"] is True
    assert (content_dir / "baru.txt").read_text() == "ditulis lewat sync wrapper"
