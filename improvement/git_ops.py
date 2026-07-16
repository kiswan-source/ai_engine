"""Git operations for the Continuous Improvement Engine's auto-apply path
(Fase 7, DCF v5 mandate). Every function takes an explicit ``repo_path`` —
never assumes "the current process's working directory" — so tests always
point this at a disposable temp repo, never the real application repo.

Safety-first: :func:`safe_to_commit` refuses to proceed if the working
tree has ANY uncommitted change other than the exact file about to be
touched — an autonomous process must never commit over a human's (or this
same Claude Code session's) in-progress work sitting uncommitted in the
same repo. This is checked immediately before every `apply_config_change`
call in ``improvement/apply.py``, not assumed safe.

No ``--force``, no interactive flags (``-i``), no amend — every commit is
a normal, new, revertible commit; every revert is a normal, new
``git revert`` commit, never a hard reset or history rewrite.
"""
from __future__ import annotations

import subprocess


class GitOpsError(Exception):
    """A git subprocess call failed — the caller must not assume anything
    was actually committed/reverted."""


class DirtyTreeError(GitOpsError):
    """Refused to commit — the working tree has unrelated uncommitted
    changes that could get swept into this commit.

    Deliberately NOT a frozen dataclass: Python's own exception-propagation
    machinery needs to assign ``__traceback__``/``__cause__`` on this
    object as it unwinds — a frozen dataclass blocks ALL attribute
    assignment, including those, and raising this turned into a second,
    unrelated ``FrozenInstanceError`` instead of the intended error (caught
    live by this module's own tests, not assumed away).
    """

    def __init__(self, dirty_files: tuple[str, ...]) -> None:
        self.dirty_files = dirty_files
        super().__init__(f"working tree has unrelated uncommitted changes: {', '.join(dirty_files)}")


def _run(repo_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise GitOpsError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    # rstrip only (never lstrip/strip) — `git status --porcelain`'s status
    # codes are meaningful LEADING characters (e.g. " M path"); stripping
    # those corrupts the very first line's parsing (caught live by this
    # module's own tests, not assumed away).
    return result.stdout.rstrip("\n")


def safe_to_commit(repo_path: str, target_file: str) -> None:
    """Raise :class:`DirtyTreeError` unless the only uncommitted change (if
    any) in `repo_path` is `target_file` itself. Never proceeds past this
    silently — the caller (`improvement/apply.py`) must call this
    immediately before `commit_file`, not rely on having called it earlier."""
    status = _run(repo_path, "status", "--porcelain")
    if not status:
        return
    dirty = []
    for line in status.splitlines():
        path = line[3:].strip()
        if path != target_file:
            dirty.append(path)
    if dirty:
        raise DirtyTreeError(tuple(dirty))


def commit_file(repo_path: str, target_file: str, message: str) -> str:
    """Stage exactly `target_file` and commit it. Returns the new commit
    SHA. Caller must have already called :func:`safe_to_commit`."""
    _run(repo_path, "add", "--", target_file)
    _run(repo_path, "commit", "-m", message)
    return _run(repo_path, "rev-parse", "HEAD")


def revert_commit(repo_path: str, sha: str) -> str:
    """`git revert --no-edit <sha>` — a new commit that undoes `sha`,
    never a reset/rewrite. Returns the new (revert) commit SHA."""
    _run(repo_path, "revert", "--no-edit", sha)
    return _run(repo_path, "rev-parse", "HEAD")
