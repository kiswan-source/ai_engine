"""Unit tests for audit log rotation + hash-chain tamper-evidence (Fase 1,
DCF_SECURITY_AUDIT_2026-07-11.md temuan #8) — see security/audit_log.py's
module docstring for the full design. Isolated to a temp file, same pattern
as test_audit_log.py.
"""
import json

import pytest

from security import audit_log


@pytest.fixture(autouse=True)
def _isolated_path(tmp_path, monkeypatch):
    path = str(tmp_path / "security_audit.log")
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_PATH", path)
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_MAX_BYTES", 10_000_000)
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_BACKUP_COUNT", 5)
    return path


# ─── Hash chain ──────────────────────────────────────────────────────────

async def test_first_entry_has_empty_prev_hash_and_a_real_entry_hash():
    entry = await audit_log.record("test.event", actor="a")
    assert entry.prev_hash == ""
    assert entry.entry_hash != ""


async def test_second_entry_chains_to_first():
    first = await audit_log.record("test.event", actor="a")
    second = await audit_log.record("test.event", actor="b")
    assert second.prev_hash == first.entry_hash
    assert second.entry_hash != first.entry_hash


async def test_verify_chain_ok_on_untouched_log(_isolated_path):
    for i in range(5):
        await audit_log.record("test.event", actor="a", detail={"i": i})

    ok, problems = audit_log.verify_chain(_isolated_path)
    assert ok is True
    assert problems == []


async def test_verify_chain_detects_edited_entry(_isolated_path):
    await audit_log.record("test.event", actor="a", detail={"amount": 1})
    await audit_log.record("test.event", actor="b", detail={"amount": 2})

    with open(_isolated_path, encoding="utf-8") as f:
        lines = f.readlines()
    tampered = json.loads(lines[0])
    tampered["detail"]["amount"] = 9999  # change content, leave entry_hash as-is
    lines[0] = json.dumps(tampered) + "\n"
    with open(_isolated_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    ok, problems = audit_log.verify_chain(_isolated_path)
    assert ok is False
    assert any("tidak cocok" in p for p in problems)


async def test_verify_chain_detects_deleted_middle_entry(_isolated_path):
    await audit_log.record("test.event", actor="a")
    await audit_log.record("test.event", actor="b")
    await audit_log.record("test.event", actor="c")

    with open(_isolated_path, encoding="utf-8") as f:
        lines = f.readlines()
    del lines[1]  # remove the middle entry
    with open(_isolated_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    ok, problems = audit_log.verify_chain(_isolated_path)
    assert ok is False
    assert any("tidak menyambung" in p for p in problems)


async def test_verify_chain_ok_on_missing_file(tmp_path):
    ok, problems = audit_log.verify_chain(str(tmp_path / "does-not-exist.log"))
    assert ok is True
    assert problems == []


async def test_legacy_entry_without_hash_is_skipped_not_flagged(_isolated_path):
    legacy = {"event_type": "old.event", "actor": "a", "detail": {}, "trace_id": "", "timestamp": 1.0}
    with open(_isolated_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(legacy) + "\n")
    await audit_log.record("new.event", actor="b")

    ok, problems = audit_log.verify_chain(_isolated_path)
    assert ok is True
    assert problems == []


async def test_legacy_entries_still_readable_via_read_recent(_isolated_path):
    legacy = {"event_type": "old.event", "actor": "a", "detail": {}, "trace_id": "", "timestamp": 1.0}
    with open(_isolated_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(legacy) + "\n")

    recent = audit_log.read_recent()
    assert len(recent) == 1
    assert recent[0].event_type == "old.event"
    assert recent[0].prev_hash == ""
    assert recent[0].entry_hash == ""


# ─── Rotation ────────────────────────────────────────────────────────────

async def test_rotates_when_max_bytes_exceeded(_isolated_path, monkeypatch):
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_MAX_BYTES", 1)  # rotate on every write
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_BACKUP_COUNT", 3)

    await audit_log.record("test.event", actor="a")  # file now > 1 byte
    await audit_log.record("test.event", actor="b")  # triggers rotation before this write

    import os
    assert os.path.exists(_isolated_path)
    assert os.path.exists(_isolated_path + ".1")


async def test_rotation_carries_hash_chain_forward(_isolated_path, monkeypatch):
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_MAX_BYTES", 1)
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_BACKUP_COUNT", 3)

    first = await audit_log.record("test.event", actor="a")
    await audit_log.record("test.event", actor="b")  # rotates; backup.1 ends with `first`

    with open(_isolated_path, encoding="utf-8") as f:
        current_lines = [json.loads(line) for line in f if line.strip()]
    # First line of the fresh file is the rotation marker, chained to `first`.
    assert current_lines[0]["event_type"] == "audit_log.rotated"
    assert current_lines[0]["prev_hash"] == first.entry_hash

    with open(_isolated_path + ".1", encoding="utf-8") as f:
        backup_lines = [json.loads(line) for line in f if line.strip()]
    assert backup_lines[-1]["entry_hash"] == first.entry_hash


async def test_old_backups_beyond_backup_count_are_dropped(_isolated_path, monkeypatch):
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_MAX_BYTES", 1)
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_BACKUP_COUNT", 2)

    for i in range(6):  # far more than backup_count -> forces multiple rotations
        await audit_log.record("test.event", actor="a", detail={"i": i})

    import os
    assert os.path.exists(_isolated_path + ".1")
    assert os.path.exists(_isolated_path + ".2")
    assert not os.path.exists(_isolated_path + ".3")


async def test_verify_chain_across_rotated_backup_and_current_file(_isolated_path, monkeypatch):
    """Deleting an entire backup file is detectable from the current file's
    genesis prev_hash having no matching entry left on disk — verified here
    by checking the two files together form one continuous, verifiable chain."""
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_MAX_BYTES", 1)
    monkeypatch.setattr("api.config.settings.AUDIT_LOG_BACKUP_COUNT", 3)

    await audit_log.record("test.event", actor="a")
    await audit_log.record("test.event", actor="b")  # rotates

    ok_backup, problems_backup = audit_log.verify_chain(_isolated_path + ".1")
    ok_current, problems_current = audit_log.verify_chain(_isolated_path)
    assert ok_backup is True and problems_backup == []
    assert ok_current is True and problems_current == []

    with open(_isolated_path + ".1", encoding="utf-8") as f:
        backup_last_hash = json.loads(f.readlines()[-1])["entry_hash"]
    with open(_isolated_path, encoding="utf-8") as f:
        current_first_prev_hash = json.loads(f.readlines()[0])["prev_hash"]
    assert current_first_prev_hash == backup_last_hash  # the two files chain together
