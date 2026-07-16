"""Local filesystem adapter for Project Workspace (Bab 69.3/69.11, ADR-0005).

Registers a folder as a Workspace source **without ever copying its
contents** (ADR-0005's binding principle) — every method here reads from the
original location, gated through `tools/tool_validator.resolve_within_root`
(Root Restriction, Bab 69.6). Only the ``Local`` source type has a working
adapter this pass; ``Network``/``Server``/``Cloud``/... are Bab 69.16 roadmap.

File classification mirrors the extension groups `agent/tools/registry.py`
already registers for Chat/Agent tools (document/image/gis), so a Workspace
Scan's counts mean the same thing a user would expect from uploading the
same files one by one.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from tools.tool_validator import resolve_within_root

DOCUMENT_EXTENSIONS = {"pdf", "txt", "md", "log", "docx", "doc", "csv", "json"}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp", "gif"}
GIS_EXTENSIONS = {"kml", "geojson", "shp", "zip"}


def classify(filename: str) -> str:
    """document | image | gis | other, by extension (same groups as agent/tools/registry.py)."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext in DOCUMENT_EXTENSIONS:
        return "document"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in GIS_EXTENSIONS:
        return "gis"
    return "other"


@dataclass(frozen=True)
class WorkspaceFile:
    """One file found under a Workspace Folder root, path relative to it."""

    relative_path: str
    category: str
    size_bytes: int


@dataclass(frozen=True)
class ScanResult:
    files: list[WorkspaceFile] = field(default_factory=list)
    document_count: int = 0
    image_count: int = 0
    gis_count: int = 0
    other_count: int = 0
    total_size_bytes: int = 0


class FilesystemAdapter:
    """Root-restricted read access to one Local Workspace Folder."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise NotADirectoryError(f"Workspace root does not exist or is not a directory: {self.root}")

    def _walk(self):
        for dirpath, _dirnames, filenames in os.walk(self.root, followlinks=False):
            for filename in filenames:
                abs_path = Path(dirpath) / filename
                rel_path = abs_path.relative_to(self.root).as_posix()
                # Re-validate every entry through the same gate a caller-supplied
                # path would use — catches a symlinked file/dir pointing outside root.
                resolve_within_root(self.root, rel_path)
                yield rel_path, abs_path

    def list_tree(self) -> list[WorkspaceFile]:
        files = []
        for rel_path, abs_path in self._walk():
            files.append(
                WorkspaceFile(
                    relative_path=rel_path,
                    category=classify(rel_path),
                    size_bytes=abs_path.stat().st_size,
                )
            )
        return files

    def scan(self) -> ScanResult:
        files = self.list_tree()
        counts = {"document": 0, "image": 0, "gis": 0, "other": 0}
        total_size = 0
        for f in files:
            counts[f.category] += 1
            total_size += f.size_bytes
        return ScanResult(
            files=files,
            document_count=counts["document"],
            image_count=counts["image"],
            gis_count=counts["gis"],
            other_count=counts["other"],
            total_size_bytes=total_size,
        )

    def read_bytes(self, relative_path: str) -> bytes:
        path = resolve_within_root(self.root, relative_path)
        return path.read_bytes()

    def read_text(self, relative_path: str, encoding: str = "utf-8") -> str:
        path = resolve_within_root(self.root, relative_path)
        return path.read_text(encoding=encoding)

    def absolute_path(self, relative_path: str) -> Path:
        """Resolved absolute path — used to hand off to `agent/tools/readers.py`
        parsers (PDF/DOCX/etc.) which expect a real file path, not bytes."""
        return resolve_within_root(self.root, relative_path)

    def write_text(self, relative_path: str, content: str, mode: str = "w", encoding: str = "utf-8") -> Path:
        """Create/overwrite (``mode="w"``) or append (``mode="a"``) a text
        file, gated through the same Root Restriction as every read here
        (Bab 69.7 Workspace Write Access, Tahap 30). ``resolve_within_root``
        works for a not-yet-existing target too (``Path.resolve()`` doesn't
        require the file to exist), so a brand-new file is validated exactly
        like an existing one — no separate "does it exist" branch needed."""
        path = resolve_within_root(self.root, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, mode, encoding=encoding) as f:
            f.write(content)
        return path

    def write_bytes(self, relative_path: str, data: bytes) -> Path:
        """Overwrite with raw bytes (Fase 4, Workspace file version restore
        — `workspace/versioning.py` stores every version as raw bytes
        regardless of format, so one write path covers text and PDF/DOCX
        alike instead of branching by extension)."""
        path = resolve_within_root(self.root, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path
