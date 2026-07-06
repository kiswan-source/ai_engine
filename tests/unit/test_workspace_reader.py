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
    _list_files,
    _read_file,
    _write_file,
    workspace_list_files,
    workspace_read_file,
    workspace_write_file,
)
from db.models import Workspace, WorkspaceFolder


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Workspace.metadata.create_all, tables=[Workspace.__table__, WorkspaceFolder.__table__])
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
    assert result["action"] == "overwrite"
    assert (tmp_path / "catatan.txt").read_text() == "isi baru"


async def test_write_file_overwrite_replaces_content(sqlite_session_factory, tmp_path):
    (tmp_path / "catatan.txt").write_text("lama")
    workspace_id, folder_id = await _seed(sqlite_session_factory, tmp_path)

    result = await _write_file(
        workspace_id, folder_id, "catatan.txt", "baru", mode="overwrite", session_factory=sqlite_session_factory
    )

    assert result["success"] is True
    assert (tmp_path / "catatan.txt").read_text() == "baru"


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
