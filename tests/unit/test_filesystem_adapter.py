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
