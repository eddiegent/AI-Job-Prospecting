"""Phase 4.5 regression tests for scripts/migrate.py.

These are the most safety-critical tests in the whole roadmap. Each one
pins an invariant that, if violated, would corrupt or orphan real user
data: months of hand-tuned CV history, dozens of generated application
packs, and a SQLite DB whose ``applications.output_folder`` column is
absolute-path-sensitive.

Migration model under test:

* ``detect_legacy_install(project_root)`` — read-only probe; returns
  either a dict describing the legacy layout or None.
* ``plan_migration(legacy, target)`` — pure function; returns a dict
  with ``file_copies`` (src, dst pairs), ``db_rewrites``
  (application_id, old_path, new_path triples), and ``marker_path``.
* ``apply_migration(legacy, target, *, backups_dir, verify_fn=None)`` —
  copies files to a scratch dir inside ``target``, runs the verification
  hook, and only if verification passes commits the copy to its final
  location and writes the ``.migrated_from`` marker. Refuses to run if
  ``backups_dir`` does not exist or is empty — Phase 0 must come first.
* ``rollback_migration(target)`` — uses the sidecar file
  ``.migration_rollback.json`` written by ``apply_migration`` to restore
  the DB's ``output_folder`` column to its pre-migration values.

Tests cover every task listed in the Phase 4.5 section of
``PLUGIN_ROADMAP.md``. The one integration test that would need a model
call (Step 5 tailor run against migrated data) is intentionally not
replicated here — see the decision log.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from scripts import migrate as migrate_mod
from scripts.job_history_db import JobHistoryDB


# ----- fixtures ---------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_application(db: JobHistoryDB, *, output_folder: str, company: str) -> int:
    return db.add_application(
        company_name=company,
        job_title="Senior Backend Engineer",
        source_url=f"https://example.com/{company.lower()}/job/1",
        fit_level="good",
        fit_pct=78.0,
        output_folder=output_folder,
        required_skills=["Python", "PostgreSQL"],
    )


def _make_legacy_install(
    tmp_path: Path,
    *,
    project_name: str = "Job Prospecting",
    with_backup: bool = True,
) -> dict:
    """Build a realistic legacy install tree.

    Uses ``project_name`` so tests can exercise paths-with-spaces by
    passing ``"Job Prospecting"`` (with a space) — matches the real
    layout this migration has to survive.
    """
    project_root = tmp_path / project_name
    project_root.mkdir()

    resources = project_root / "resources"
    resources.mkdir()
    (resources / "MASTER_CV.docx").write_bytes(b"pretend-docx-bytes\x00")
    (resources / "cv_fact_base.json").write_text(
        '{"candidate_name": "Test User"}', encoding="utf-8"
    )
    (resources / ".cv_hash").write_text("deadbeef", encoding="utf-8")

    output = project_root / "output"
    output.mkdir()
    pack1 = output / "good-10042026-helios-analytics-backend-engineer"
    pack2 = output / "medium-08042026-northbridge-software-full-stack"
    for pack in (pack1, pack2):
        prep = pack / "_prep"
        prep.mkdir(parents=True)
        (prep / "job_offer_analysis.json").write_text(
            '{"company": "x"}', encoding="utf-8"
        )
        (pack / "tailored_cv.docx").write_bytes(b"fake docx")

    db_path = resources / "job_history.db"
    db = JobHistoryDB(db_path)
    _seed_application(db, output_folder=str(pack1), company="Helios Analytics")
    _seed_application(db, output_folder=str(pack2), company="Northbridge Software")
    db.close()

    backups_dir = project_root / "backups"
    if with_backup:
        backups_dir.mkdir()
        (backups_dir / "pre-plugin-migration-2026-04-10-1553").mkdir()
        (
            backups_dir
            / "pre-plugin-migration-2026-04-10-1553"
            / "manifest.json"
        ).write_text("{}", encoding="utf-8")

    return {
        "project_root": project_root,
        "legacy_resources": resources,
        "legacy_output": output,
        "db_path": db_path,
        "backups_dir": backups_dir,
        "pack1": pack1,
        "pack2": pack2,
    }


# ----- dry run ----------------------------------------------------------

def test_dry_run_writes_nothing_anywhere(tmp_path, monkeypatch):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    pre_hashes = {
        p.relative_to(tmp_path).as_posix(): _sha256(p)
        for p in (tmp_path).rglob("*")
        if p.is_file()
    }

    plan = migrate_mod.plan_migration(
        legacy=legacy["project_root"], target=target
    )

    post_hashes = {
        p.relative_to(tmp_path).as_posix(): _sha256(p)
        for p in (tmp_path).rglob("*")
        if p.is_file()
    }

    assert pre_hashes == post_hashes
    assert not target.exists()
    assert "file_copies" in plan
    assert "db_rewrites" in plan
    assert len(plan["db_rewrites"]) == 2


def test_detect_legacy_returns_none_when_no_resources(tmp_path):
    empty = tmp_path / "empty_project"
    empty.mkdir()
    assert migrate_mod.detect_legacy_install(empty) is None


# ----- apply ------------------------------------------------------------

def test_apply_copies_all_legacy_files_to_new_location(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )

    # Every legacy file must have a byte-identical copy under target.
    for src in legacy["legacy_resources"].rglob("*"):
        if src.is_file() and src.name != "job_history.db":
            # The DB is compared separately below — its output_folder
            # column is intentionally rewritten during migration.
            rel = src.relative_to(legacy["legacy_resources"])
            dst = target / rel
            assert dst.exists(), f"missing {dst}"
            assert _sha256(src) == _sha256(dst), f"SHA mismatch on {rel}"

    for src in legacy["legacy_output"].rglob("*"):
        if src.is_file():
            rel = src.relative_to(legacy["legacy_output"])
            dst = target / "output" / rel
            assert dst.exists(), f"missing {dst}"
            assert _sha256(src) == _sha256(dst), f"SHA mismatch on output/{rel}"


def test_apply_does_not_move_or_delete_legacy_files(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    pre = {
        p.relative_to(legacy["project_root"]).as_posix(): _sha256(p)
        for p in legacy["project_root"].rglob("*")
        if p.is_file() and "backups" not in p.parts
    }

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )

    post = {
        p.relative_to(legacy["project_root"]).as_posix(): _sha256(p)
        for p in legacy["project_root"].rglob("*")
        if p.is_file() and "backups" not in p.parts
    }

    assert pre == post, "legacy tree was mutated by apply_migration"


def test_apply_rewrites_db_output_folder_column(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )

    new_db_path = target / "job_history.db"
    with sqlite3.connect(str(new_db_path)) as conn:
        rows = conn.execute(
            "SELECT output_folder FROM applications ORDER BY id"
        ).fetchall()

    legacy_output_str = str(legacy["legacy_output"])
    new_output_str = str(target / "output")
    for (folder,) in rows:
        assert folder is not None
        assert legacy_output_str not in folder, (
            f"rewritten row still contains legacy prefix: {folder}"
        )
        assert folder.startswith(new_output_str), (
            f"rewritten row does not point at new output dir: {folder}"
        )
        # And the pointed-to directory actually exists.
        assert Path(folder).exists(), f"rewritten path does not exist: {folder}"


def test_apply_is_a_noop_on_second_run(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )
    first = {
        p.relative_to(target).as_posix(): _sha256(p)
        for p in target.rglob("*")
        if p.is_file()
    }

    report = migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )
    second = {
        p.relative_to(target).as_posix(): _sha256(p)
        for p in target.rglob("*")
        if p.is_file()
    }

    assert first == second
    assert report["already_migrated"] is True


def test_apply_requires_phase_0_backup_to_exist(tmp_path):
    legacy = _make_legacy_install(tmp_path, with_backup=False)
    target = tmp_path / "new_location"

    with pytest.raises(migrate_mod.MigrationError, match="backup"):
        migrate_mod.apply_migration(
            legacy=legacy["project_root"],
            target=target,
            backups_dir=legacy["backups_dir"],
        )

    assert not target.exists(), "target must not be created on safety failure"


def test_verification_gate_blocks_apply_on_failure(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    def always_fails(staging_dir: Path) -> list[str]:
        return ["synthetic verification failure"]

    with pytest.raises(migrate_mod.MigrationError, match="verification"):
        migrate_mod.apply_migration(
            legacy=legacy["project_root"],
            target=target,
            backups_dir=legacy["backups_dir"],
            verify_fn=always_fails,
        )

    # Real destination must not have been touched. (The staging dir is
    # cleaned up on failure.)
    assert not (target / "MASTER_CV.docx").exists()
    assert not (target / "job_history.db").exists()
    # Legacy untouched.
    assert (legacy["legacy_resources"] / "MASTER_CV.docx").exists()


# ----- rollback ---------------------------------------------------------

def test_rollback_restores_db_output_folder_column(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    # Capture pre-migration output_folder values.
    with sqlite3.connect(str(legacy["db_path"])) as conn:
        original = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT id, output_folder FROM applications"
            )
        }

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )
    migrate_mod.rollback_migration(target=target)

    with sqlite3.connect(str(target / "job_history.db")) as conn:
        rolled = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT id, output_folder FROM applications"
            )
        }

    assert rolled == original


# ----- post-migration history integrity ---------------------------------

def test_find_duplicates_still_works_after_migration(tmp_path):
    legacy = _make_legacy_install(tmp_path)
    target = tmp_path / "new_location"

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )

    migrated_db = JobHistoryDB(target / "job_history.db")
    matches = migrated_db.find_duplicates(
        company_name="Helios Analytics",
        job_title="Senior Backend Engineer",
        source_url="https://example.com/helios analytics/job/1",
    )
    migrated_db.close()

    assert matches, "find_duplicates returned nothing post-migration"
    hit = matches[0]
    assert hit["output_folder"].startswith(str(target / "output"))
    assert Path(hit["output_folder"]).exists()


def test_skill_can_run_against_migrated_data():
    """Full Step-5 run against migrated data is a manual eval, not a unit test.

    Running the tailor step requires a model call, which is slow, non-
    deterministic, and outside pytest's scope. The invariants that would
    have been caught by this test are already pinned by:

    - ``test_find_duplicates_still_works_after_migration`` — DB + path
      rewrite round-trip under realistic use.
    - ``test_apply_copies_all_legacy_files_to_new_location`` — SHA-256
      identity of every non-DB file.
    - ``test_apply_rewrites_db_output_folder_column`` — new paths exist.

    Between them, a model-free integration failure would show up before
    the manual smoke pass. This placeholder stays so the roadmap's test
    manifest stays traceable.
    """
    pytest.skip("Manual eval — see docstring")


# ----- paths with spaces ------------------------------------------------

def test_migrate_handles_paths_with_spaces(tmp_path):
    legacy = _make_legacy_install(tmp_path, project_name="Job Prospecting")
    target = tmp_path / "New Location With Spaces"

    migrate_mod.apply_migration(
        legacy=legacy["project_root"],
        target=target,
        backups_dir=legacy["backups_dir"],
    )

    assert " " in str(legacy["project_root"])
    assert " " in str(target)
    assert (target / "MASTER_CV.docx").exists()

    with sqlite3.connect(str(target / "job_history.db")) as conn:
        rows = conn.execute(
            "SELECT output_folder FROM applications"
        ).fetchall()
    for (folder,) in rows:
        assert Path(folder).exists()
        assert " " in folder
