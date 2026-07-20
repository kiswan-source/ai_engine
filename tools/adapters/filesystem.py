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
import shutil
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

    def exists(self, relative_path: str) -> bool:
        """Whether ``relative_path`` exists under this root — resolved
        through the same Root Restriction gate as every other method here,
        so a traversal attempt raises rather than silently returning False."""
        return resolve_within_root(self.root, relative_path).exists()

    def make_dir(self, relative_path: str) -> Path:
        """Create a folder (and any missing parents) under this root.
        A no-op if it already exists, matching ``os.makedirs(exist_ok=True)``
        — creating a folder that's already there isn't an error condition
        for the "buat folder" mandate requirement."""
        path = resolve_within_root(self.root, relative_path)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def move(self, src_relative: str, dst_relative: str) -> Path:
        """Move/rename a file or folder within this root — both the source
        and destination are validated through Root Restriction (a caller
        could otherwise ``../``-escape via either argument, not just one)."""
        src = resolve_within_root(self.root, src_relative)
        if not src.exists():
            raise FileNotFoundError(f"{src_relative!r} tidak ditemukan di Workspace ini.")
        dst = resolve_within_root(self.root, dst_relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        return Path(shutil.move(str(src), str(dst)))

    def copy(self, src_relative: str, dst_relative: str) -> Path:
        """Copy a file or folder within this root — same dual Root
        Restriction check as :meth:`move`."""
        src = resolve_within_root(self.root, src_relative)
        if not src.exists():
            raise FileNotFoundError(f"{src_relative!r} tidak ditemukan di Workspace ini.")
        dst = resolve_within_root(self.root, dst_relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dst))
        return dst

    def delete(self, relative_path: str) -> None:
        """Permanently remove one file under this root — Workspace Slice 2
        (delete). File-only for this slice (deliberately narrower scope than
        move/copy, which already handle directories) — a caller must refuse
        or handle directories one level up, since recursive folder delete is
        a separate, higher-blast-radius slice not built yet. Callers are
        responsible for snapshotting the content first if recoverability is
        wanted (this method is the irreversible primitive, not the policy
        that wraps it)."""
        path = resolve_within_root(self.root, relative_path)
        if not path.exists():
            raise FileNotFoundError(f"{relative_path!r} tidak ditemukan di Workspace ini.")
        if path.is_dir():
            raise IsADirectoryError(f"{relative_path!r} adalah folder — delete folder belum didukung slice ini.")
        path.unlink()

    def search(self, query: str) -> list[WorkspaceFile]:
        """Case-insensitive filename search across the whole tree under this
        root (Smart Search) — matches on substring, not just exact name, so
        "Kesimpulan_Tiga_Framework" finds "Kesimpulan_Tiga_Framework.pdf"."""
        needle = query.lower()
        return [
            WorkspaceFile(relative_path=rel_path, category=classify(rel_path), size_bytes=abs_path.stat().st_size)
            for rel_path, abs_path in self._walk()
            if needle in os.path.basename(rel_path).lower()
        ]
