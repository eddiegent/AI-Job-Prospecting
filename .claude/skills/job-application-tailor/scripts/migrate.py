"""Phase 4.5 — migrate a legacy loose install to the plugin layout.

A legacy install keeps everything under the project directory:

    <project>/resources/MASTER_CV.docx
    <project>/resources/job_history.db
    <project>/resources/cv_fact_base.json
    <project>/resources/.cv_hash
    <project>/output/<fit>-<date>-<slug>/...

The plugin layout puts everything under a user-owned data dir (see
``scripts/paths.py::resolve_user_data_dir``) so the plugin code and the
user data are cleanly separable:

    <target>/MASTER_CV.docx
    <target>/job_history.db
    <target>/cv_fact_base.json
    <target>/.cv_hash
    <target>/output/<fit>-<date>-<slug>/...

This module performs that migration in a way that is safe enough to run
against real, months-of-hand-tuned data:

1. **Phase 0 backup required.** ``apply_migration`` refuses to run
   unless a non-empty ``backups/`` directory exists — so the Phase 0
   pre-flight backup has been taken before any write happens.
2. **Copy, never move.** The legacy tree is left byte-identical so the
   user can keep using the old layout until they are confident in the
   new one.
3. **Staging + verification gate.** Files are copied to an in-target
   scratch dir first, a caller-supplied ``verify_fn`` runs against the
   staged copy, and only on success does the migration rename-commit
   the scratch dir into its final location.
4. **DB output_folder rewrite.** Every ``applications.output_folder``
   row whose value lives under the legacy output path is rewritten to
   the new absolute path. A sidecar ``.migration_rollback.json`` records
   the original values for ``rollback_migration``.
5. **Idempotency marker.** A ``.migrated_from`` file records the
   legacy project root; subsequent runs become a no-op.

None of the functions here read or write files under the user's
``~/.claude/`` directory — the migration scope is strictly legacy
``<project>/resources/`` + ``<project>/output/`` → plugin user data dir.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


class MigrationError(RuntimeError):
    """Raised when a migration precondition fails or verification rejects the copy."""


MARKER_NAME = ".migrated_from"
ROLLBACK_NAME = ".migration_rollback.json"
_STAGING_DIRNAME = ".migration_staging"


# ----- detection --------------------------------------------------------

@dataclass
class LegacyLayout:
    project_root: Path
    resources: Path
    output: Path
    db_path: Path | None
    files_in_resources: list[Path] = field(default_factory=list)


def detect_legacy_install(project_root: Path) -> LegacyLayout | None:
    """Return a ``LegacyLayout`` if ``project_root`` looks like a loose install.

    The probe is specific: we require ``resources/MASTER_CV.docx`` to
    exist. A bare ``resources/`` directory with no CV is treated as "not
    a legacy install" so an aborted or empty install can't accidentally
    anchor the migration against a meaningless location.
    """
    project_root = Path(project_root)
    resources = project_root / "resources"
    if not (resources / "MASTER_CV.docx").exists():
        return None

    files = [p for p in resources.rglob("*") if p.is_file()]
    db_path = resources / "job_history.db"
    return LegacyLayout(
        project_root=project_root,
        resources=resources,
        output=project_root / "output",
        db_path=db_path if db_path.exists() else None,
        files_in_resources=files,
    )


# ----- planning ---------------------------------------------------------

def _read_db_output_folders(db_path: Path) -> list[tuple[int, str]]:
    # sqlite3.connect's context manager commits on exit but does NOT close.
    # On Windows that leaves the file handle open long enough to break a
    # subsequent shutil.move of the DB, so we close explicitly everywhere.
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, output_folder FROM applications "
            "WHERE output_folder IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    return [(int(r[0]), str(r[1])) for r in rows]


def _rewrite_path(old: str, legacy_output: Path, new_output: Path) -> str:
    """Rewrite ``old`` so its ``legacy_output`` prefix becomes ``new_output``.

    Uses string-prefix replacement on resolved paths so it survives the
    OS's path-separator differences — both sides of the comparison are
    normalised through ``Path`` before the swap.
    """
    legacy_str = str(legacy_output)
    if old.startswith(legacy_str):
        suffix = old[len(legacy_str):].lstrip("/\\")
        return str(new_output / suffix) if suffix else str(new_output)
    # Path.is_relative_to fallback for resolved forms.
    try:
        rel = Path(old).relative_to(legacy_output)
        return str(new_output / rel)
    except ValueError:
        return old


def plan_migration(*, legacy: Path, target: Path) -> dict[str, Any]:
    """Return a plan dict. Pure function — no filesystem writes."""
    legacy = Path(legacy)
    target = Path(target)
    layout = detect_legacy_install(legacy)
    if layout is None:
        return {
            "legacy_detected": False,
            "file_copies": [],
            "db_rewrites": [],
            "marker_path": str(target / MARKER_NAME),
        }

    file_copies: list[tuple[str, str]] = []
    # resources/ files (including the DB — it gets copied, then rewritten)
    for src in layout.files_in_resources:
        rel = src.relative_to(layout.resources)
        dst = target / rel
        file_copies.append((str(src), str(dst)))
    # output/ tree
    if layout.output.exists():
        for src in layout.output.rglob("*"):
            if src.is_file():
                rel = src.relative_to(layout.output)
                dst = target / "output" / rel
                file_copies.append((str(src), str(dst)))

    db_rewrites: list[tuple[int, str, str]] = []
    new_output = target / "output"
    if layout.db_path is not None:
        for app_id, old_path in _read_db_output_folders(layout.db_path):
            new_path = _rewrite_path(old_path, layout.output, new_output)
            if new_path != old_path:
                db_rewrites.append((app_id, old_path, new_path))

    return {
        "legacy_detected": True,
        "legacy_project_root": str(layout.project_root),
        "legacy_output": str(layout.output),
        "target": str(target),
        "file_copies": file_copies,
        "db_rewrites": db_rewrites,
        "marker_path": str(target / MARKER_NAME),
    }


# ----- apply ------------------------------------------------------------

def _backup_is_present(backups_dir: Path) -> bool:
    if not backups_dir.exists() or not backups_dir.is_dir():
        return False
    return any(backups_dir.iterdir())


def _default_verify(staging_dir: Path) -> list[str]:
    """Baseline verification: the staged DB reopens and its schema is intact."""
    problems: list[str] = []
    db_path = staging_dir / "job_history.db"
    if db_path.exists():
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT COUNT(*) FROM applications").fetchone()
        except sqlite3.DatabaseError as exc:
            problems.append(f"staged DB is not readable: {exc}")
        finally:
            if conn is not None:
                conn.close()
    return problems


def _apply_db_rewrites(db_path: Path, rewrites: list[tuple[int, str, str]]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        for app_id, _, new_path in rewrites:
            conn.execute(
                "UPDATE applications SET output_folder = ?, "
                "updated_at = COALESCE(updated_at, '') WHERE id = ?",
                (new_path, app_id),
            )
        conn.commit()
    finally:
        conn.close()


def apply_migration(
    *,
    legacy: Path,
    target: Path,
    backups_dir: Path,
    verify_fn: Callable[[Path], list[str]] | None = None,
) -> dict[str, Any]:
    """Copy legacy data to ``target`` with a verification gate.

    Returns a report dict; raises ``MigrationError`` on precondition or
    verification failure.
    """
    legacy = Path(legacy)
    target = Path(target)
    backups_dir = Path(backups_dir)

    marker = target / MARKER_NAME
    if marker.exists():
        return {
            "already_migrated": True,
            "target": str(target),
            "file_copies": 0,
            "db_rewrites": 0,
        }

    if not _backup_is_present(backups_dir):
        raise MigrationError(
            f"Phase 0 backup missing or empty at {backups_dir}. "
            "Run scripts/backup_user_data.py first."
        )

    plan = plan_migration(legacy=legacy, target=target)
    if not plan["legacy_detected"]:
        raise MigrationError(
            f"No legacy install detected at {legacy} "
            "(expected resources/MASTER_CV.docx)."
        )

    target.mkdir(parents=True, exist_ok=True)
    staging = target / _STAGING_DIRNAME
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()

    try:
        # 1. Copy files to staging under the same relative layout they'd
        #    end up at under `target`.
        for src_str, dst_str in plan["file_copies"]:
            src = Path(src_str)
            dst_rel = Path(dst_str).relative_to(target)
            staged_dst = staging / dst_rel
            staged_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, staged_dst)

        # 2. Rewrite the DB in place inside staging, recording originals
        #    for rollback.
        staged_db = staging / "job_history.db"
        original_paths: dict[int, str] = {}
        if staged_db.exists() and plan["db_rewrites"]:
            for app_id, old_path, _ in plan["db_rewrites"]:
                original_paths[app_id] = old_path
            _apply_db_rewrites(staged_db, plan["db_rewrites"])

        # 3. Verification gate.
        verify = verify_fn or _default_verify
        problems = verify(staging)
        if problems:
            raise MigrationError(
                "Post-copy verification failed:\n  - "
                + "\n  - ".join(problems)
            )

        # 4. Commit: move each staged file to its real destination.
        for src_str, dst_str in plan["file_copies"]:
            dst_rel = Path(dst_str).relative_to(target)
            staged_src = staging / dst_rel
            final_dst = target / dst_rel
            final_dst.parent.mkdir(parents=True, exist_ok=True)
            if final_dst.exists():
                final_dst.unlink()
            shutil.move(str(staged_src), str(final_dst))

        # 5. Write sidecar rollback + marker.
        if original_paths:
            (target / ROLLBACK_NAME).write_text(
                json.dumps(
                    {"output_folder_originals": original_paths},
                    indent=2,
                ),
                encoding="utf-8",
            )
        marker.write_text(
            str(plan["legacy_project_root"]), encoding="utf-8"
        )

        return {
            "already_migrated": False,
            "target": str(target),
            "file_copies": len(plan["file_copies"]),
            "db_rewrites": len(plan["db_rewrites"]),
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


# ----- rollback ---------------------------------------------------------

def rollback_migration(*, target: Path) -> dict[str, Any]:
    """Restore the DB's ``output_folder`` column using the sidecar file."""
    target = Path(target)
    sidecar = target / ROLLBACK_NAME
    if not sidecar.exists():
        raise MigrationError(
            f"No rollback sidecar at {sidecar}; nothing to restore."
        )
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    originals = data.get("output_folder_originals", {})

    db_path = target / "job_history.db"
    if not db_path.exists():
        raise MigrationError(f"No DB at {db_path} to roll back.")

    conn = sqlite3.connect(str(db_path))
    try:
        for app_id_str, original in originals.items():
            conn.execute(
                "UPDATE applications SET output_folder = ? WHERE id = ?",
                (original, int(app_id_str)),
            )
        conn.commit()
    finally:
        conn.close()
    return {"restored_rows": len(originals)}


# ----- CLI --------------------------------------------------------------

def _print_plan(plan: dict[str, Any]) -> None:
    if not plan["legacy_detected"]:
        print("No legacy install detected. Nothing to do.")
        return
    print(f"Legacy project root: {plan['legacy_project_root']}")
    print(f"Target user data dir: {plan['target']}")
    print(f"Files to copy: {len(plan['file_copies'])}")
    print(f"DB rows to rewrite: {len(plan['db_rewrites'])}")
    if plan["db_rewrites"]:
        print("Sample rewrites:")
        for app_id, old, new in plan["db_rewrites"][:3]:
            print(f"  [{app_id}] {old}")
            print(f"      -> {new}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    from scripts.paths import resolve_user_data_dir

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually copy files and rewrite the DB (default is dry run).",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Reverse the DB output_folder rewrite using the sidecar.",
    )
    parser.add_argument(
        "--legacy",
        type=Path,
        default=Path.cwd(),
        help="Path to the legacy project root (default: CWD).",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Path to the new user data dir (default: resolve_user_data_dir()).",
    )
    parser.add_argument(
        "--backups-dir",
        type=Path,
        default=None,
        help="Path to the Phase 0 backups dir (default: <legacy>/backups).",
    )
    args = parser.parse_args(argv)

    target = args.target or resolve_user_data_dir()
    backups_dir = args.backups_dir or (args.legacy / "backups")

    if args.rollback:
        report = rollback_migration(target=target)
        print(f"Rollback complete: {report['restored_rows']} rows restored.")
        return 0

    if not args.apply:
        plan = plan_migration(legacy=args.legacy, target=target)
        print("DRY RUN — no files written.")
        _print_plan(plan)
        print("\nRe-run with --apply to execute.")
        return 0

    try:
        report = apply_migration(
            legacy=args.legacy,
            target=target,
            backups_dir=backups_dir,
        )
    except MigrationError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1

    if report["already_migrated"]:
        print(f"Target {target} is already migrated. No-op.")
    else:
        print(
            f"Migrated {report['file_copies']} files and "
            f"{report['db_rewrites']} DB rows to {target}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
