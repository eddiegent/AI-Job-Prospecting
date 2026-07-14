"""Diagnostics: doctor (read-only DB health/fingerprint report)."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from scripts.job_history_db import JobHistoryDB, compute_content_fingerprint
from scripts.commands import Command


def _inspect_db_file(path) -> dict | None:
    """Read-only fingerprint + stat of a SQLite DB file, or None if absent."""
    if path is None or not Path(path).exists():
        return None
    con = sqlite3.connect(str(path))
    try:
        info = compute_content_fingerprint(con)
    finally:
        con.close()
    st = Path(path).stat()
    info["path"] = str(path)
    info["mtime"] = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
    info["size_bytes"] = st.st_size
    return info


def cmd_doctor(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Read-only health / fingerprint report (PIPELINE_HARDENING_ROADMAP 1.1).

    Surfaces two things a normal `list` never shows: a stable content
    fingerprint (compare it across sessions — if it changes with no writes in
    between, the DB was replaced/restored externally), and the temp working
    MIRROR the DB layer operates on. The mirror is copied from the canonical
    target only when the target looks newer (mtime-gated); a stale mirror can
    quietly overwrite newer rows on the next open, which is the leading suspect
    for silent history divergence.
    """
    target = _inspect_db_file(db.db_path)
    mirror = _inspect_db_file(db._mirror_path)
    diverged = bool(target and mirror and target["fingerprint"] != mirror["fingerprint"])
    backups_dir = Path(db.db_path).parent / "db-backups"
    snaps = sorted(backups_dir.glob(f"{Path(db.db_path).stem}-*.db")) if backups_dir.exists() else []
    report = {
        "job_tailor_home": os.environ.get("JOB_TAILOR_HOME"),
        "target": target,
        "mirror": mirror,
        "mirror_diverged": diverged,
        "backups": {
            "dir": str(backups_dir),
            "count": len(snaps),
            "latest": str(snaps[-1]) if snaps else None,
        },
    }

    if getattr(args, "json", False):
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print("DB doctor")
    print(f"  JOB_TAILOR_HOME : {report['job_tailor_home'] or '(unset)'}")
    for label, info in (("target (canonical)", target), ("mirror (temp working copy)", mirror)):
        print(f"  {label}:")
        if info is None:
            print("    (absent)")
            continue
        print(f"    path        : {info['path']}")
        print(f"    mtime       : {info['mtime']}   size: {info['size_bytes']} bytes")
        print(f"    schema ver  : {info['schema_version']}")
        print(f"    rows        : {info['row_count']}   max id: {info['max_id']}")
        print(f"    fingerprint : {info['fingerprint']}")
    if diverged:
        print("  WARNING: target and mirror fingerprints DIFFER — the temp mirror holds")
        print("    different data than the canonical DB. A stale mirror can overwrite")
        print("    newer rows on next open (mtime-gated sync). If the canonical target")
        print("    is the source of truth, delete the mirror so it is re-copied fresh:")
        if mirror:
            print(f"      rm \"{mirror['path']}\"")
    else:
        print("  target and mirror agree (or mirror absent) — no divergence detected.")
    b = report["backups"]
    print(f"  db-backups      : {b['count']} snapshot(s) in {b['dir']}")
    if b["latest"]:
        print(f"    latest        : {Path(b['latest']).name}")


def _configure_doctor(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="Emit the report as JSON")


COMMANDS = [
    Command('doctor',
            help='Read-only DB health/fingerprint report; surfaces the temp mirror and any divergence',
            configure=_configure_doctor, handler=cmd_doctor),
]
