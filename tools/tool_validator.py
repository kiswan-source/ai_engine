"""Root Restriction primitive (MASTER_INSTRUCTION.md Bab 69.6).

Agent access to a Workspace Folder must never escape the folder's registered
root — no ``../`` traversal, no symlink pointing outside. This is the single
gate every filesystem read in `tools/adapters/filesystem.py` routes through;
it does not depend on `security/permissions.py` (that's role-based RBAC, a
separate concern from "which paths on disk are even reachable").
"""
from __future__ import annotations

from pathlib import Path


class PathEscapesRootError(PermissionError):
    """Raised when a resolved path would land outside its Workspace root."""


def resolve_within_root(root: str | Path, relative: str) -> Path:
    """Resolve ``relative`` against ``root`` and return the real path.

    Raises :class:`PathEscapesRootError` if the resolved (symlink-following)
    path is not ``root`` itself or a descendant of it — this is what makes
    ``../../etc/passwd`` or a symlink pointing outside the root fail closed
    rather than silently succeeding.
    """
    root_resolved = Path(root).resolve()
    candidate = (root_resolved / relative).resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise PathEscapesRootError(
            f"path {relative!r} resolves outside workspace root {root_resolved}"
        )
    return candidate
