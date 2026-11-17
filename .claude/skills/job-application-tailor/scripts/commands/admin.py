"""Diagnostics and repair: doctor (read-only DB health/fingerprint report),
repair-output-folders (re-point stale pack paths; dry run by default)."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from scripts import paths
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


def _app_label(app: dict) -> str:
    return f"#{app['id']} {app['company_name']} — {app['job_title']}"


def cmd_repair_output_folders(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Re-point rows whose stored `output_folder` no longer exists.

    `output_folder` holds absolute paths, and most of the history was written
    in cloud sessions (`/sessions/<id>/mnt/...`) or on another machine, so the
    stored path is dead here even though the pack sits under this project's
    `output/` by the same folder name. Every id-based lookup already falls
    back to that location (`paths.resolve_output_folder`); this makes the fix
    permanent so the DB, `get` and exports show real paths again.

    Dry run unless `--apply`: it rewrites the relocatable rows only, never
    touches a row whose pack is missing everywhere (those are listed so the
    user can decide), and snapshots the DB first (via `writes_if`).
    """
    root = Path(args.project_root) if args.project_root else paths.resolve_project_root()
    apps = sorted(db.list_applications(limit=10**9), key=lambda a: a["id"])
    buckets: dict[str, list[tuple[dict, Path | None]]] = {
        "ok": [], "relocated": [], "missing": [], "none": [],
    }
    for app in apps:
        found, state = paths.locate_output_folder(app.get("output_folder"), project_root=root)
        buckets[state].append((app, found))

    relocated, missing = buckets["relocated"], buckets["missing"]
    print(f"Output folders ({len(apps)} rows, looking under {root / 'output'}):")
    print(f"  already fine          : {len(buckets['ok'])}")
    print(f"  repairable (by name)  : {len(relocated)}")
    print(f"  missing everywhere    : {len(missing)}")
    print(f"  no folder recorded    : {len(buckets['none'])}")

    if relocated:
        print("\nRepairable — stored path is gone, pack found under output/:")
        for app, found in relocated:
            print(f"  {_app_label(app)}")
            print(f"    {app['output_folder']}")
            print(f"    -> {found}")
    if missing:
        print("\nMissing everywhere — left as is (restore the pack, or fix with update-output-folder):")
        for app, _ in missing:
            print(f"  {_app_label(app)}: {app['output_folder']}")

    if not args.apply:
        if relocated:
            print(f"\nDry run — nothing written. Re-run with --apply to rewrite {len(relocated)} row(s).")
        return
    for app, found in relocated:
        db.update_output_folder(app["id"], str(found))
    print(f"\nRewrote output_folder on {len(relocated)} row(s).")


def _configure_repair_output_folders(p: argparse.ArgumentParser) -> None:
    p.description = (
        "Find rows whose stored output_folder doesn't exist but whose pack is under "
        "<project_root>/output/ by the same folder name, and list the rows whose pack is "
        "missing everywhere. Dry run by default; --apply rewrites the repairable rows "
        "(after a DB snapshot)."
    )
    p.add_argument("--apply", action="store_true",
                   help="Write the repaired paths (default: dry run, report only)")
    p.add_argument("--project-root",
                   help="Directory whose output/ holds the packs (default: the git toplevel, "
                   "else the project marker above the skill, else the user data dir — same as preflight)")


COMMANDS = [
    Command('doctor',
            help='Read-only DB health/fingerprint report; surfaces the temp mirror and any divergence',
            configure=_configure_doctor, handler=cmd_doctor),
    Command('repair-output-folders',
            help='Re-point rows whose stored output_folder is stale to the pack under output/ (dry run unless --apply)',
            configure=_configure_repair_output_folders, handler=cmd_repair_output_folders,
            mutating=True, writes_if=lambda a: bool(getattr(a, "apply", False))),
]
