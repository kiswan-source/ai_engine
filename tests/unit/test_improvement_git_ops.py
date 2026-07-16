"""Unit tests for improvement/git_ops.py (Fase 7, DCF v5 mandate). Every
test operates on a disposable `tmp_path` git repo — NEVER the real
ai_engine repo, so an assertion failure here can never accidentally
commit/revert anything in the actual project history.
"""
import subprocess

import pytest

from improvement.git_ops import DirtyTreeError, commit_file, revert_commit, safe_to_commit


def _git(repo_path, *args):
    subprocess.run(["git", "-C", str(repo_path), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "config.yaml").write_text("KEY: 1\n")
    _git(tmp_path, "add", "config.yaml")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def test_safe_to_commit_passes_on_clean_tree(repo):
    safe_to_commit(str(repo), "config.yaml")  # must not raise


def test_safe_to_commit_passes_when_only_target_file_is_dirty(repo):
    (repo / "config.yaml").write_text("KEY: 2\n")
    safe_to_commit(str(repo), "config.yaml")  # must not raise


def test_safe_to_commit_refuses_when_another_file_is_dirty(repo):
    (repo / "other.txt").write_text("someone's in-progress work\n")

    with pytest.raises(DirtyTreeError) as exc_info:
        safe_to_commit(str(repo), "config.yaml")
    assert "other.txt" in str(exc_info.value)


def test_commit_file_creates_a_real_commit(repo):
    (repo / "config.yaml").write_text("KEY: 2\n")

    sha = commit_file(str(repo), "config.yaml", "improvement: adjust KEY")

    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline", "-1"], capture_output=True, text=True, check=True,
    ).stdout
    assert sha[:7] in log
    assert "improvement: adjust KEY" in log
    # working tree is clean again after the commit
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True, check=True,
    ).stdout
    assert status.strip() == ""


def test_revert_commit_restores_previous_content(repo):
    (repo / "config.yaml").write_text("KEY: 2\n")
    sha = commit_file(str(repo), "config.yaml", "improvement: adjust KEY")

    revert_commit(str(repo), sha)

    assert (repo / "config.yaml").read_text() == "KEY: 1\n"


def test_revert_commit_is_itself_a_new_commit_not_a_reset(repo):
    (repo / "config.yaml").write_text("KEY: 2\n")
    sha = commit_file(str(repo), "config.yaml", "improvement: adjust KEY")

    revert_commit(str(repo), sha)

    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--oneline"], capture_output=True, text=True, check=True,
    ).stdout
    lines = [l for l in log.splitlines() if l.strip()]
    assert len(lines) == 3  # initial + adjust + revert — history preserved, nothing erased
