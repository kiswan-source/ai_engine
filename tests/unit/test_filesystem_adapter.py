"""Unit tests for the Workspace filesystem adapter (Bab 69.6 Root Restriction)."""
import os

import pytest

from tools.adapters.filesystem import FilesystemAdapter, classify
from tools.tool_validator import PathEscapesRootError, resolve_within_root


@pytest.fixture()
def workspace_root(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "images").mkdir()
    (tmp_path / "docs" / "report.txt").write_text("mining feasibility study")
    (tmp_path / "docs" / "notes.pdf").write_bytes(b"%PDF-fake")
    (tmp_path / "images" / "site.png").write_bytes(b"\x89PNG-fake")
    (tmp_path / "area.geojson").write_text("{}")
    return tmp_path


# ─── tool_validator.resolve_within_root ────────────────────────────────────

def test_resolve_within_root_allows_nested_path(workspace_root):
    resolved = resolve_within_root(workspace_root, "docs/report.txt")
    assert resolved == (workspace_root / "docs" / "report.txt").resolve()


def test_resolve_within_root_rejects_parent_traversal(workspace_root):
    with pytest.raises(PathEscapesRootError):
        resolve_within_root(workspace_root, "../../etc/passwd")


def test_resolve_within_root_rejects_absolute_escape(workspace_root, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "secret.txt"
    with pytest.raises(PathEscapesRootError):
        resolve_within_root(workspace_root, f"../{outside.name}")


@pytest.mark.skipif(os.name == "nt", reason="symlinks need elevated perms on Windows")
def test_resolve_within_root_rejects_symlink_escape(workspace_root, tmp_path_factory):
    outside_dir = tmp_path_factory.mktemp("outside")
    (outside_dir / "secret.txt").write_text("nope")
    link = workspace_root / "escape_link"
    link.symlink_to(outside_dir)
    with pytest.raises(PathEscapesRootError):
        resolve_within_root(workspace_root, "escape_link/secret.txt")


# ─── classify() ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "filename,expected",
    [
        ("report.txt", "document"),
        ("notes.pdf", "document"),
        ("scan.docx", "document"),
        ("site.png", "image"),
        ("area.geojson", "gis"),
        ("boundary.kml", "gis"),
        ("archive.zip", "gis"),
        ("unknown.xyz", "other"),
    ],
)
def test_classify_matches_agent_tools_registry_groups(filename, expected):
    assert classify(filename) == expected


# ─── FilesystemAdapter ──────────────────────────────────────────────────

def test_adapter_rejects_missing_root(tmp_path):
    with pytest.raises(NotADirectoryError):
        FilesystemAdapter(tmp_path / "does-not-exist")


def test_adapter_scan_counts_by_category(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    result = adapter.scan()
    assert result.document_count == 2
    assert result.image_count == 1
    assert result.gis_count == 1
    assert result.other_count == 0
    assert len(result.files) == 4
    assert result.total_size_bytes > 0


def test_adapter_read_text_within_root(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    assert adapter.read_text("docs/report.txt") == "mining feasibility study"


def test_adapter_read_bytes_rejects_root_escape(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(PathEscapesRootError):
        adapter.read_bytes("../../etc/passwd")


def test_adapter_list_tree_returns_relative_posix_paths(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    paths = {f.relative_path for f in adapter.list_tree()}
    assert "docs/report.txt" in paths
    assert "images/site.png" in paths


# ─── CRUD additions (Fase 8, DCF v5 mandate "Workspace Native File Access") ──

def test_adapter_exists(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    assert adapter.exists("docs/report.txt") is True
    assert adapter.exists("docs/missing.txt") is False


def test_adapter_make_dir_creates_nested_folder(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    adapter.make_dir("new/nested/folder")
    assert (workspace_root / "new" / "nested" / "folder").is_dir()


def test_adapter_make_dir_is_idempotent(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    adapter.make_dir("docs")  # already exists — must not raise
    assert (workspace_root / "docs").is_dir()


def test_adapter_make_dir_rejects_root_escape(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(PathEscapesRootError):
        adapter.make_dir("../escape")


def test_adapter_move_renames_file(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    adapter.move("docs/report.txt", "docs/renamed.txt")
    assert not (workspace_root / "docs" / "report.txt").exists()
    assert (workspace_root / "docs" / "renamed.txt").read_text() == "mining feasibility study"


def test_adapter_move_to_different_folder(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    adapter.move("docs/report.txt", "images/report.txt")
    assert (workspace_root / "images" / "report.txt").exists()


def test_adapter_move_missing_source_raises(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(FileNotFoundError):
        adapter.move("docs/does-not-exist.txt", "docs/x.txt")


def test_adapter_move_rejects_root_escape_on_either_side(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(PathEscapesRootError):
        adapter.move("docs/report.txt", "../outside.txt")
    with pytest.raises(PathEscapesRootError):
        adapter.move("../outside.txt", "docs/x.txt")


def test_adapter_copy_leaves_source_in_place(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    adapter.copy("docs/report.txt", "docs/copy.txt")
    assert (workspace_root / "docs" / "report.txt").exists()
    assert (workspace_root / "docs" / "copy.txt").read_text() == "mining feasibility study"


def test_adapter_copy_missing_source_raises(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(FileNotFoundError):
        adapter.copy("docs/does-not-exist.txt", "docs/x.txt")


def test_adapter_search_matches_by_substring_case_insensitive(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    results = {f.relative_path for f in adapter.search("REPORT")}
    assert results == {"docs/report.txt"}


def test_adapter_search_no_match_returns_empty_list(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    assert adapter.search("nonexistent-name") == []


# ─── delete (Workspace Slice 2) ────────────────────────────────────────────

def test_adapter_delete_removes_file(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    adapter.delete("docs/report.txt")
    assert not (workspace_root / "docs" / "report.txt").exists()


def test_adapter_delete_missing_file_raises(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(FileNotFoundError):
        adapter.delete("docs/does-not-exist.txt")


def test_adapter_delete_rejects_directory(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(IsADirectoryError):
        adapter.delete("docs")
    assert (workspace_root / "docs").is_dir()  # untouched


def test_adapter_delete_rejects_root_escape(workspace_root):
    adapter = FilesystemAdapter(workspace_root)
    with pytest.raises(PathEscapesRootError):
        adapter.delete("../outside.txt")
