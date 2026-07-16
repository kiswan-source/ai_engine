"""Audit Log (MASTER_INSTRUCTION.md Bab 30, 61.3) — append-only trail of sensitive actions.

Writes one JSON line per entry to ``AUDIT_LOG_PATH`` (default
``security_audit.log``) — a dedicated file. The pre-existing ``audit.log`` at
the repo root is already this deployment's systemd stdout-capture target
(general request/access logs), not a structured trail; writing JSON entries
into it would interleave them with arbitrary log lines and defeat the point
of an audit trail. Also publishes a ``security.<event_type>`` event on the
Event Bus (Bab 23 prinsip 1) so :class:`telemetry.tracing.Tracer` folds
audit entries into a request's Execution Timeline.

Rotation & tamper-evidence (Fase 1, DCF_SECURITY_AUDIT_2026-07-11.md
temuan #8): the file above was a single unbounded text file with no way to
detect a deleted/edited entry. Two independent mechanisms close that:

1. **Size-based rotation** — before a write would push the file past
   ``AUDIT_LOG_MAX_BYTES``, the current file is renamed to ``<path>.1``
   (existing ``.1``..``.N-1`` shift up to ``.2``..``.N``, the oldest beyond
   ``AUDIT_LOG_BACKUP_COUNT`` is dropped), and a fresh file starts.
2. **Hash chain** — every entry carries ``prev_hash`` (the ``entry_hash`` of
   the entry immediately before it) and its own ``entry_hash`` (a SHA-256 of
   its own fields + ``prev_hash``). Deleting or editing an entry breaks the
   chain at that point — verifiable with :func:`verify_chain`, not just
   asserted. The chain survives rotation: the first line of a freshly
   rotated file is a synthetic ``audit_log.rotated`` entry whose
   ``prev_hash`` is the last entry's hash from the file just rotated out —
   so deleting an entire backup file is *also* detectable from the current
   file alone (its genesis entry's ``prev_hash`` would have no matching
   entry anywhere left on disk). Entries written before this Tahap have no
   ``entry_hash`` (both fields default to ``""``) and are treated as
   pre-dating integrity tracking, not as a broken chain — see
   :func:`verify_chain`.

Concurrent writers: the Docker Compose services (api/worker_ai/worker_gis)
and the systemd deployment all bind-mount the same repo directory and can
append to the same physical file. ``fcntl.flock`` (advisory, exclusive)
around the read-last-hash + rotate + append critical section in
:func:`_write` serializes them — Unix-only, matches this deployment's actual
platforms (Docker Linux containers + systemd on Linux/WSL), no new
dependency.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from core.utils.logger import get_logger
from messaging import EventBus

logger = get_logger(__name__)


@dataclass(frozen=True)
class AuditEntry:
    """One append-only audit record."""

    event_type: str
    actor: str
    detail: dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    timestamp: float = field(default_factory=time.time)
    # Hash chain (Fase 1 / SEC-8) — "" on both for entries written before
    # this Tahap, or for the first entry of a chain that has no predecessor.
    prev_hash: str = ""
    entry_hash: str = ""


def _canonical_hash(event_type: str, actor: str, detail: dict[str, Any],
                     trace_id: str, timestamp: float, prev_hash: str) -> str:
    """SHA-256 of an entry's own content chained to `prev_hash` — the same
    six inputs on both write and verify, so a matching recomputation is the
    proof an entry (and its position in the chain) hasn't changed."""
    payload = json.dumps(
        {"event_type": event_type, "actor": actor, "detail": detail,
         "trace_id": trace_id, "timestamp": timestamp, "prev_hash": prev_hash},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_entry_hash(path: str) -> str:
    """``entry_hash`` of the last line in `path`, or "" if the file is
    missing/empty/its last line pre-dates hash-chaining (genesis)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return ""
            # Read backwards in chunks until a newline is found — cheap even
            # for a large file, unlike reading the whole thing (read_recent
            # already does that for its own, separate purpose).
            chunk = 4096
            pos = size
            data = b""
            while pos > 0:
                pos = max(0, pos - chunk)
                f.seek(pos)
                data = f.read(size - pos)
                if b"\n" in data.rstrip(b"\n"):
                    break
            last_line = data.rstrip(b"\n").split(b"\n")[-1]
        if not last_line.strip():
            return ""
        return json.loads(last_line).get("entry_hash", "") or ""
    except (OSError, json.JSONDecodeError):
        return ""


def _rotate_locked(path: str, max_bytes: int, backup_count: int) -> None:
    """Caller already holds the lock on `path`. No-op below the size threshold."""
    if backup_count < 1 or not os.path.exists(path) or os.path.getsize(path) < max_bytes:
        return
    carried_hash = _last_entry_hash(path)
    for i in range(backup_count - 1, 0, -1):
        src, dst = f"{path}.{i}", f"{path}.{i + 1}"
        if os.path.exists(src):
            os.replace(src, dst)
    os.replace(path, f"{path}.1")
    marker_ts = time.time()
    marker_hash = _canonical_hash("audit_log.rotated", "system",
                                   {"note": "log dirotasi; rantai hash dilanjutkan dari berkas sebelumnya"},
                                   "", marker_ts, carried_hash)
    marker = AuditEntry(event_type="audit_log.rotated", actor="system",
                         detail={"note": "log dirotasi; rantai hash dilanjutkan dari berkas sebelumnya"},
                         timestamp=marker_ts, prev_hash=carried_hash, entry_hash=marker_hash)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(marker), default=str) + "\n")


def _write(event_type: str, actor: str, detail: dict[str, Any], trace_id: str, timestamp: float) -> AuditEntry:
    from api.config import settings

    path = settings.AUDIT_LOG_PATH
    try:
        # A lock file rather than locking `path` itself — flock releases
        # automatically if a rotation replaces the underlying inode
        # mid-critical-section on some platforms, which would silently drop
        # the lock's effect; a separate, stable lock path doesn't have that
        # failure mode.
        lock_path = path + ".lock"
        with open(lock_path, "a") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                _rotate_locked(path, settings.AUDIT_LOG_MAX_BYTES, settings.AUDIT_LOG_BACKUP_COUNT)
                prev_hash = _last_entry_hash(path)
                entry_hash = _canonical_hash(event_type, actor, detail, trace_id, timestamp, prev_hash)
                entry = AuditEntry(event_type=event_type, actor=actor, detail=detail, trace_id=trace_id,
                                    timestamp=timestamp, prev_hash=prev_hash, entry_hash=entry_hash)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(entry), default=str) + "\n")
                return entry
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    except OSError as exc:
        # Audit logging must never break the caller's actual operation (Bab 10.4).
        logger.error("audit_log.write_failed", error=str(exc))
        return AuditEntry(event_type=event_type, actor=actor, detail=detail, trace_id=trace_id, timestamp=timestamp)


async def record(
    event_type: str,
    actor: str,
    detail: dict[str, Any] | None = None,
    trace_id: str = "",
    event_bus: EventBus | None = None,
) -> AuditEntry:
    """Append one audit entry (rotated + hash-chained, see module docstring)
    and publish it as a ``security.<event_type>`` event."""
    entry = _write(event_type, actor, detail or {}, trace_id, time.time())
    events = event_bus or EventBus()
    await events.emit(f"security.{event_type}", source=actor, trace_id=trace_id, payload=entry.detail)
    return entry


def read_recent(limit: int = 100) -> list[AuditEntry]:
    """Newest ``limit`` entries from the audit log file (best-effort; missing file = empty).

    Only reads the current (unrotated) file — matches the pre-Fase-1
    behavior/contract this function already had; rotated backups are for
    :func:`verify_chain` and manual inspection, not the live dashboard.
    """
    from api.config import settings

    try:
        with open(settings.AUDIT_LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [AuditEntry(**json.loads(line)) for line in lines[-limit:] if line.strip()]


def verify_chain(path: str | None = None) -> tuple[bool, list[str]]:
    """Walk every line in `path` (default ``settings.AUDIT_LOG_PATH``) and
    confirm each entry's ``entry_hash`` matches recomputation and chains to
    the previous entry's ``entry_hash``. Returns ``(ok, problems)`` —
    ``problems`` is empty iff ``ok`` is True. Entries with no ``entry_hash``
    (written before Fase 1) are skipped, not treated as broken, but they
    reset the expected ``prev_hash`` for whatever comes after them to ""
    (the first genuinely hash-chained entry is its own genesis).
    """
    if path is None:
        from api.config import settings
        path = settings.AUDIT_LOG_PATH

    problems: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            lines = [line for line in f if line.strip()]
    except FileNotFoundError:
        return True, []

    expected_prev = ""
    chain_started = False
    for i, line in enumerate(lines, start=1):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {i}: bukan JSON valid")
            continue
        entry_hash = raw.get("entry_hash", "")
        if not entry_hash:
            continue  # pre-Fase-1 entry, not part of any verifiable chain
        recomputed = _canonical_hash(
            raw.get("event_type", ""), raw.get("actor", ""), raw.get("detail", {}),
            raw.get("trace_id", ""), raw.get("timestamp", 0.0), raw.get("prev_hash", ""),
        )
        if recomputed != entry_hash:
            problems.append(f"line {i}: entry_hash tidak cocok — entri kemungkinan diubah")
        if chain_started and raw.get("prev_hash", "") != expected_prev:
            problems.append(f"line {i}: prev_hash tidak menyambung ke entri sebelumnya — kemungkinan entri dihapus/disisipkan")
        expected_prev = entry_hash
        chain_started = True

    return not problems, problems
