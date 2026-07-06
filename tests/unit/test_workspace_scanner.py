"""Unit tests for workspace/scanner.py (Bab 69.2/69.8 aggregation)."""
from tools.adapters.filesystem import FilesystemAdapter
from workspace.scanner import scan_folders


def test_scan_folders_aggregates_counts_across_multiple_folders(tmp_path):
    folder_a = tmp_path / "a"
    folder_b = tmp_path / "b"
    folder_a.mkdir()
    folder_b.mkdir()
    (folder_a / "report.txt").write_text("hello")
    (folder_a / "site.png").write_bytes(b"\x89PNG")
    (folder_b / "boundary.kml").write_text("<kml/>")

    summary = scan_folders(
        {
            "folder-a": FilesystemAdapter(folder_a),
            "folder-b": FilesystemAdapter(folder_b),
        }
    )

    assert summary.document_count == 1
    assert summary.image_count == 1
    assert summary.gis_count == 1
    assert summary.other_count == 0
    assert summary.total_size_bytes > 0
    assert set(summary.per_folder.keys()) == {"folder-a", "folder-b"}


def test_scan_folders_empty_dict_returns_zeroed_summary():
    summary = scan_folders({})
    assert summary.document_count == 0
    assert summary.per_folder == {}
