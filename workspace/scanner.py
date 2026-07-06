"""Workspace Scan (Bab 69.2, 69.8) — aggregates a Workspace's registered
folders into one set of counts (`api/routes/workspace.py`'s ``POST
.../scan`` persists the result into ``Workspace``/``last_scan_at``).

Pure function over already-constructed adapters — no DB/HTTP here, so it's
trivially unit-testable without a database (Bab 12.3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from tools.adapters.filesystem import FilesystemAdapter, ScanResult


@dataclass(frozen=True)
class WorkspaceScanSummary:
    per_folder: dict[str, ScanResult] = field(default_factory=dict)
    document_count: int = 0
    image_count: int = 0
    gis_count: int = 0
    other_count: int = 0
    total_size_bytes: int = 0


def scan_folders(adapters_by_folder_id: dict[str, FilesystemAdapter]) -> WorkspaceScanSummary:
    """Scan every ``FilesystemAdapter`` (one per registered ``WorkspaceFolder``)
    and roll the counts up to Workspace level."""
    per_folder = {folder_id: adapter.scan() for folder_id, adapter in adapters_by_folder_id.items()}
    return WorkspaceScanSummary(
        per_folder=per_folder,
        document_count=sum(r.document_count for r in per_folder.values()),
        image_count=sum(r.image_count for r in per_folder.values()),
        gis_count=sum(r.gis_count for r in per_folder.values()),
        other_count=sum(r.other_count for r in per_folder.values()),
        total_size_bytes=sum(r.total_size_bytes for r in per_folder.values()),
    )
