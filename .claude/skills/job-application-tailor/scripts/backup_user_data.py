"""Pre-flight backup of user data before plugin-migration work.

Phase 0 of PLUGIN_ROADMAP.md. The vital user data lives in gitignored
files (MASTER_CV.docx, job_history.db, cv_fact_base.json, output/) with
no other recovery path, so Phases 3 and 4.5 must not run without a
verified backup on disk first.

This module is intentionally small and dependency-free: it uses only the
stdlib so it can run on a fresh install before `pip install -r
requirements.txt` has completed.

Usage:
    python -m scripts.backup_user_data <project-root> [<backup-root>]

The script copies ``<project-root>/resources`` and ``<project-root>/output``
into ``<backup-root>/pre-plugin-migration-<timestamp>/``, exports every
SQLite table in ``resources/job_history.db`` to a CSV in ``db_export/``,
writes a ``manifest.json`` with a SHA-256 per backed-up file, and drops a
``README.txt`` with restoration instructions.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Iterable


BACKUP_DIR_PREFIX = "pre-plugin-migration-"
SUBDIRS_TO_COPY = ("resources", "output")


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def backup(
    source_root: Path,
    backup_root: Path,
    timestamp: str | None = None,
) -> Path:
    """Create a timestamped backup folder under ``backup_root``.

    Returns the path to the created folder. Raises ``FileExistsError`` if
    a backup with the same timestamp already exists — the caller must pick
    a new timestamp rather than silently overwriting a previous backup.
    """
    source_root = Path(source_root)
    backup_root = Path(backup_root)

    if timestamp is None:
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")

    target = backup_root / f"{BACKUP_DIR_PREFIX}{timestamp}"
    if target.exists():
        raise FileExistsError(
            f"Backup target {target} already exists; pick a different timestamp "
            f"or delete the existing folder manually."
        )

    target.mkdir(parents=True)

    copied_files: list[Path] = []
    for subdir in SUBDIRS_TO_COPY:
        src = source_root / subdir
        if not src.exists():
            continue
        dst = target / subdir
        shutil.copytree(src, dst)
        copied_files.extend(p for p in dst.rglob("*") if p.is_file())

    db_export_dir = target / "db_export"
    db_path = source_root / "resources" / "job_history.db"
    if db_path.exists():
        db_export_dir.mkdir()
        exported = _export_sqlite_to_csv(db_path, db_export_dir)
        copied_files.extend(exported)

    manifest = _build_manifest(target, copied_files)
    manifest_path = target / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    readme_path = target / "README.txt"
    readme_path.write_text(_readme_text(source_root, timestamp), encoding="utf-8")

    return target


def verify_backup(backup_dir: Path) -> list[str]:
    """Re-hash every file listed in the manifest and flag mismatches.

    Returns a list of violation messages. An empty list means the backup
    is intact.
    """
    backup_dir = Path(backup_dir)
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return [f"manifest.json missing under {backup_dir}"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    violations: list[str] = []
    for rel, recorded_hash in manifest.get("files", {}).items():
        abs_path = backup_dir / rel
        if not abs_path.exists():
            violations.append(f"Missing file: {rel}")
            continue
        actual = _sha256_of(abs_path)
        if actual != recorded_hash:
            violations.append(
                f"SHA-256 mismatch for {rel}: manifest={recorded_hash[:12]}..., "
                f"actual={actual[:12]}..."
            )
    return violations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_manifest(backup_dir: Path, files: Iterable[Path]) -> dict:
    entries: dict[str, str] = {}
    for f in files:
        rel = f.relative_to(backup_dir).as_posix()
        entries[rel] = _sha256_of(f)
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "file_count": len(entries),
        "files": entries,
    }


def _export_sqlite_to_csv(db_path: Path, out_dir: Path) -> list[Path]:
    """Dump every user table in the DB to a CSV. Returns the written files."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    written: list[Path] = []
    try:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        table_names = [row[0] for row in cursor.fetchall()]
        for table in table_names:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            csv_path = out_dir / f"{table}.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                if rows:
                    writer.writerow(rows[0].keys())
                    for row in rows:
                        writer.writerow([row[k] for k in row.keys()])
                else:
                    # Empty table: still write the header from PRAGMA.
                    cols = [
                        r[1]
                        for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
                    ]
                    writer.writerow(cols)
            written.append(csv_path)
    finally:
        conn.close()
    return written


def _readme_text(source_root: Path, timestamp: str) -> str:
    return (
        f"Pre-plugin-migration backup\n"
        f"===========================\n\n"
        f"Created:      {timestamp}\n"
        f"Source root:  {source_root}\n\n"
        f"Contents:\n"
        f"  resources/   — full copy of {source_root / 'resources'}\n"
        f"  output/      — full copy of {source_root / 'output'}\n"
        f"  db_export/   — CSV dump of every table in job_history.db\n"
        f"  manifest.json — SHA-256 of every backed-up file\n\n"
        f"If something in the plugin migration goes wrong, you can restore\n"
        f"the original state by copying resources/ and output/ from this\n"
        f"folder back to the source root. Verify integrity first with:\n\n"
        f"    python -m scripts.backup_user_data --verify <this-folder>\n\n"
        f"Do NOT modify or delete this backup until you have confirmed the\n"
        f"plugin install works end-to-end.\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "--verify":
        violations = verify_backup(Path(argv[1]))
        if violations:
            print("Backup verification FAILED:")
            for v in violations:
                print(f"  - {v}")
            return 1
        print("Backup verification OK.")
        return 0

    if not argv:
        print("Usage: python -m scripts.backup_user_data <project-root> [<backup-root>]")
        print("       python -m scripts.backup_user_data --verify <backup-folder>")
        return 2

    source_root = Path(argv[0]).resolve()
    backup_root = Path(argv[1]).resolve() if len(argv) > 1 else source_root / "backups"
    created = backup(source_root, backup_root)
    print(f"Backup created at: {created}")
    violations = verify_backup(created)
    if violations:
        print("WARNING: post-backup verification found issues:")
        for v in violations:
            print(f"  - {v}")
        return 1
    print("Verification OK.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main(sys.argv[1:]))
