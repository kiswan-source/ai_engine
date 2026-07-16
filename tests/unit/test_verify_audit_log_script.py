"""Unit tests for scripts/verify_audit_log.py — the operator-facing CLI
wrapper around security.audit_log.verify_chain (Fase 1 / SEC-8). Invoked as
a subprocess, the way an operator actually runs it, not imported (scripts/
isn't a package).
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = str(Path(__file__).resolve().parent.parent.parent / "scripts" / "verify_audit_log.py")


def _run(path: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, SCRIPT, path], capture_output=True, text=True)


def test_exits_zero_on_clean_chain(tmp_path):
    path = tmp_path / "audit.log"
    import asyncio

    from security import audit_log

    async def _write():
        import api.config as config_module

        config_module.settings.AUDIT_LOG_PATH = str(path)
        await audit_log.record("test.event", actor="a")

    asyncio.run(_write())

    result = _run(str(path))
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_ignores_lock_file_when_scanning_backups(tmp_path):
    """The .lock file security/audit_log.py's flock creates alongside the
    real log must not be mistaken for a numbered backup (`<path>.N`)."""
    path = tmp_path / "audit.log"
    path.write_text('{"event_type": "e", "actor": "a", "detail": {}, "trace_id": "", "timestamp": 1.0}\n')
    (tmp_path / "audit.log.lock").write_text("")  # what audit_log.py actually creates

    result = _run(str(path))
    assert result.returncode == 0
    assert "invalid literal for int()" not in result.stderr


def test_exits_one_and_reports_backup_and_current_separately(tmp_path):
    path = tmp_path / "audit.log"
    path.write_text('{"event_type": "e", "actor": "a", "detail": {}, "trace_id": "", "timestamp": 1.0, "prev_hash": "", "entry_hash": "bad"}\n')
    backup = tmp_path / "audit.log.1"
    backup.write_text('{"event_type": "e", "actor": "a", "detail": {}, "trace_id": "", "timestamp": 1.0, "prev_hash": "", "entry_hash": "also_bad"}\n')

    result = _run(str(path))
    assert result.returncode == 1
    assert "RUSAK" in result.stdout
    assert str(backup) in result.stdout
    assert str(path) in result.stdout


def test_exits_zero_on_missing_file(tmp_path):
    result = _run(str(tmp_path / "does-not-exist.log"))
    assert result.returncode == 0
