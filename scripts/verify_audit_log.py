#!/usr/bin/env python3
"""Operator tool (Fase 1 / SEC-8): verify the audit log's hash chain hasn't
been tampered with. Checks the live file plus every rotated backup found
next to it, oldest first, so a break is reported against the file/line it
actually occurred in.

Usage: python3 scripts/verify_audit_log.py [path]
  path defaults to settings.AUDIT_LOG_PATH.
Exit: 0 if every file present verifies clean, 1 otherwise.
"""
import glob
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    from api.config import settings
    from security.audit_log import verify_chain

    base = sys.argv[1] if len(sys.argv) > 1 else settings.AUDIT_LOG_PATH
    numbered = []
    for p in glob.glob(base + ".*"):
        suffix = p.rsplit(".", 1)[-1]
        if suffix.isdigit():  # skips the `.lock` file audit_log.py's flock uses
            numbered.append((int(suffix), p))
    backups = [p for _, p in sorted(numbered, reverse=True)]
    files = backups + [base]  # oldest backup first, current file last

    all_ok = True
    for path in files:
        ok, problems = verify_chain(path)
        status = "OK" if ok else "RUSAK"
        print(f"[{status}] {path}")
        for p in problems:
            print(f"    - {p}")
        all_ok = all_ok and ok

    if all_ok:
        print("Seluruh berkas audit log terverifikasi utuh.")
    else:
        print("PERINGATAN: rantai audit log rusak pada satu atau lebih berkas di atas.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
