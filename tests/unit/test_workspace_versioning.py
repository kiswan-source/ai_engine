"""Unit tests for workspace/versioning.py (Fase 4, DCF v5 mandate
"Workspace Autonomous Capability" — CONTROL: version tracking)."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.models import WorkspaceFileVersion
from workspace.versioning import get_version, list_versions, save_version


@pytest.fixture
async def sqlite_session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(WorkspaceFileVersion.metadata.create_all, tables=[WorkspaceFileVersion.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def test_save_then_list_versions_newest_first(sqlite_session_factory):
    async with sqlite_session_factory() as session:
        await save_version(session, "ws-1", "folder-1", "a.txt", b"v1", actor="alice")
        await save_version(session, "ws-1", "folder-1", "a.txt", b"v2 longer", actor="bob")

        versions = await list_versions(session, "ws-1", "folder-1", "a.txt")

    assert len(versions) == 2
    assert versions[0]["actor"] == "bob"  # newest first
    assert versions[1]["actor"] == "alice"
    assert versions[0]["size_bytes"] == len(b"v2 longer")


async def test_list_versions_scoped_to_workspace_folder_and_path():
    """Different workspace_id/folder_id/relative_path must never leak into
    each other's version history."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(WorkspaceFileVersion.metadata.create_all, tables=[WorkspaceFileVersion.__table__])
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        await save_version(session, "ws-1", "folder-1", "a.txt", b"content-a", actor="x")
        await save_version(session, "ws-2", "folder-1", "a.txt", b"content-other-ws", actor="x")
        await save_version(session, "ws-1", "folder-2", "a.txt", b"content-other-folder", actor="x")
        await save_version(session, "ws-1", "folder-1", "b.txt", b"content-other-path", actor="x")

        versions = await list_versions(session, "ws-1", "folder-1", "a.txt")

    assert len(versions) == 1
    await engine.dispose()


async def test_get_version_returns_none_for_wrong_workspace_or_folder(sqlite_session_factory):
    async with sqlite_session_factory() as session:
        saved = await save_version(session, "ws-1", "folder-1", "a.txt", b"content", actor="alice")

        assert await get_version(session, saved.id, "ws-1", "folder-1") is not None
        assert await get_version(session, saved.id, "wrong-ws", "folder-1") is None
        assert await get_version(session, saved.id, "ws-1", "wrong-folder") is None


async def test_get_version_returns_full_content(sqlite_session_factory):
    async with sqlite_session_factory() as session:
        saved = await save_version(session, "ws-1", "folder-1", "a.txt", b"the actual bytes", actor="alice")

        version = await get_version(session, saved.id, "ws-1", "folder-1")

    assert version.content == b"the actual bytes"
    assert version.actor == "alice"
