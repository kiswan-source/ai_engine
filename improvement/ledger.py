"""Append-only, hash-chained ledger for the Continuous Improvement Engine
(Fase 7, DCF v5 mandate: "Semua improvement: dianalisis, diuji, divalidasi,
memiliki rollback"). Same hash-chain technique as
``security/audit_log.py`` (SEC-8) — a recommendation or an applied/reverted
action can't be quietly edited or deleted after the fact without breaking
the chain, verifiable with :func:`verify_chain`, not just asserted.

No rotation here (unlike ``audit_log.py``) — this ledger's write volume is
orders of magnitude lower (one scheduler tick's worth of recommendations,
not every guardrail/tool event), so an unbounded file is fine for now.

Every recommendation, whether or not it ever gets auto-applied, is
recorded — the append-only property is what makes "AI ENGINE improves
itself" auditable instead of a black box, per the mandate's own framing.
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
from improvement.models import ImprovementAction, ImprovementRecommendation, to_json_dict

logger = get_logger(__name__)


@dataclass(frozen=True)
class LedgerEntry:
    """One append-only ledger line."""

    record_type: str  # "recommendation" | "action_applied" | "action_reviewed"
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    prev_hash: str = ""
    entry_hash: str = ""


def _canonical_hash(record_type: str, payload: dict[str, Any], timestamp: float, prev_hash: str) -> str:
    data = json.dumps(
        {"record_type": record_type, "payload": payload, "timestamp": timestamp, "prev_hash": prev_hash},
        sort_keys=True, default=str,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _last_entry_hash(path: str) -> str:
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                return ""
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


def _write(record_type: str, payload: dict[str, Any]) -> LedgerEntry:
    from api.config import settings

    path = settings.IMPROVEMENT_LEDGER_PATH
    timestamp = time.time()
    try:
        lock_path = path + ".lock"
        with open(lock_path, "a") as lock_f:
            fcntl.flock(lock_f, fcntl.LOCK_EX)
            try:
                prev_hash = _last_entry_hash(path)
                entry_hash = _canonical_hash(record_type, payload, timestamp, prev_hash)
                entry = LedgerEntry(record_type=record_type, payload=payload, timestamp=timestamp,
                                     prev_hash=prev_hash, entry_hash=entry_hash)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(entry), default=str) + "\n")
                return entry
            finally:
                fcntl.flock(lock_f, fcntl.LOCK_UN)
    except OSError as exc:
        # A ledger write failure must never block the caller's actual
        # analysis/apply/review flow (same Bab 10.4 principle audit_log.py
        # already follows) — the entry just won't be durable this once.
        logger.error("improvement_ledger.write_failed", error=str(exc))
        return LedgerEntry(record_type=record_type, payload=payload, timestamp=timestamp)


def record_recommendation(rec: ImprovementRecommendation) -> LedgerEntry:
    return _write("recommendation", to_json_dict(rec))


def record_action_applied(action: ImprovementAction) -> LedgerEntry:
    return _write("action_applied", to_json_dict(action))


def record_action_reviewed(action: ImprovementAction) -> LedgerEntry:
    return _write("action_reviewed", to_json_dict(action))


def read_recent(limit: int = 100) -> list[LedgerEntry]:
    from api.config import settings

    try:
        with open(settings.IMPROVEMENT_LEDGER_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []
    return [LedgerEntry(**json.loads(line)) for line in lines[-limit:] if line.strip()]


def pending_actions() -> list[ImprovementAction]:
    """Reconstruct which applied actions have no matching "action_reviewed"
    entry yet — the ledger is the only source of truth for this (no
    separate in-memory queue that a process restart would lose)."""
    applied: dict[str, ImprovementAction] = {}
    reviewed_ids: set[str] = set()
    for entry in read_recent(limit=10_000):
        if entry.record_type == "action_applied":
            action = ImprovementAction(**entry.payload)
            applied[action.id] = action
        elif entry.record_type == "action_reviewed":
            reviewed_ids.add(entry.payload["id"])
    return [a for aid, a in applied.items() if aid not in reviewed_ids]


def verify_chain(path: str | None = None) -> tuple[bool, list[str]]:
    if path is None:
        from api.config import settings
        path = settings.IMPROVEMENT_LEDGER_PATH

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
            continue
        recomputed = _canonical_hash(
            raw.get("record_type", ""), raw.get("payload", {}), raw.get("timestamp", 0.0), raw.get("prev_hash", ""),
        )
        if recomputed != entry_hash:
            problems.append(f"line {i}: entry_hash tidak cocok — entri kemungkinan diubah")
        if chain_started and raw.get("prev_hash", "") != expected_prev:
            problems.append(f"line {i}: prev_hash tidak menyambung — kemungkinan entri dihapus/disisipkan")
        expected_prev = entry_hash
        chain_started = True

    return not problems, problems
