"""Stale absolute `output_folder` paths in the history DB.

Background: `applications.output_folder` stores absolute paths, and most rows
were written in cloud sessions (`/sessions/<id>/mnt/Job Prospecting/output/X`)
or on another machine. Locally ~100 of 157 stored paths were dead although 94
of those packs sat under `<project_root>/output/` by the same folder name, so
every id-based command (`regenerate-outputs 159`, `rename-application`…)
failed with "Output folder does not exist".

These tests pin:

- the folder name is taken from either separator style;
- `locate_output_folder` reports ok / relocated / missing / none;
- id-based commands fall back to `<project_root>/output/<name>`;
- `repair-output-folders` is a dry run by default (no write, no snapshot),
  and `--apply` rewrites only the relocatable rows after a snapshot.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import paths
from scripts.commands.records import _resolve_app_folder, cmd_rename_application
from scripts.job_history_db import JobHistoryDB

SKILL_ROOT = Path(__file__).resolve().parent.parent
CLI = SKILL_ROOT / "scripts" / "cli.py"


@pytest.mark.parametrize("stored,name", [
    ("/sessions/abc/mnt/Job Prospecting/output/good-01112026-Dev-Acme", "good-01112026-Dev-Acme"),
    (r"C:\Users\someone\Job Prospecting\output\medium-02112026-Dev-Beta", "medium-02112026-Dev-Beta"),
    ("/sessions/abc/mnt/output/cold-03112026-acme/", "cold-03112026-acme"),
    ("mixed/sep\\cold-04112026-x", "cold-04112026-x"),
])
def test_stored_folder_name_handles_both_separators(stored: str, name: str) -> None:
    assert paths.stored_folder_name(stored) == name


def test_locate_output_folder_states(tmp_path: Path) -> None:
    root = tmp_path / "project"
    pack = root / "output" / "good-01112026-Dev-Acme"
    pack.mkdir(parents=True)

    assert paths.locate_output_folder(str(pack), project_root=root) == (pack, "ok")
    assert paths.locate_output_folder(
        "/sessions/x/mnt/output/good-01112026-Dev-Acme", project_root=root
    ) == (pack, "relocated")
    assert paths.locate_output_folder(
        r"D:\elsewhere\output\good-01112026-Dev-Acme", project_root=root
    ) == (pack, "relocated")
    assert paths.locate_output_folder(
        "/sessions/x/mnt/output/gone-folder", project_root=root
    ) == (None, "missing")
    assert paths.locate_output_folder(None, project_root=root) == (None, "none")
    assert paths.locate_output_folder("  ", project_root=root) == (None, "none")


def test_relocation_ignores_a_file_of_the_same_name(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "output").mkdir(parents=True)
    (root / "output" / "not-a-dir").write_text("x", encoding="utf-8")
    assert paths.locate_output_folder("/a/b/not-a-dir", project_root=root) == (None, "missing")


# ---------------------------------------------------------------------------
# id-based commands use the fallback
# ---------------------------------------------------------------------------


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "project"
    (root / "output").mkdir(parents=True)
    monkeypatch.setattr(paths, "resolve_project_root", lambda **_: root)
    return root


@pytest.fixture
def db(tmp_path: Path):
    db = JobHistoryDB(str(tmp_path / "h.db"))
    yield db
    db.close()


def _add(db: JobHistoryDB, folder: str, company: str = "Acme") -> int:
    return db.add_application(company_name=company, job_title="Dev", output_folder=folder,
                              fit_level="good", fit_pct=75, detected_language="fr")


def test_resolve_app_folder_falls_back_to_project_output(project: Path, db) -> None:
    pack = project / "output" / "good-01112026-Dev-Acme"
    pack.mkdir()
    app_id = _add(db, "/sessions/zz/mnt/Job Prospecting/output/good-01112026-Dev-Acme")
    assert _resolve_app_folder(db, str(app_id)) == pack


def test_resolve_app_folder_missing_everywhere_exits_1(project: Path, db, capsys) -> None:
    app_id = _add(db, "/sessions/zz/mnt/output/gone")
    with pytest.raises(SystemExit) as e:
        _resolve_app_folder(db, str(app_id))
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "/sessions/zz/mnt/output/gone" in err and "repair-output-folders" in err


def test_rename_application_follows_a_stale_path(project: Path, db) -> None:
    pack = project / "output" / "good-01112026-Dev-Platform"
    (pack / "_prep").mkdir(parents=True)
    (pack / "_prep" / "job_offer_analysis.json").write_text(
        json.dumps({"company_name": "Platform", "job_title": "Dev"}), encoding="utf-8")
    app_id = _add(db, "/sessions/zz/mnt/output/good-01112026-Dev-Platform", company="Platform")

    cmd_rename_application(db, argparse.Namespace(
        id=app_id, new_company="Real Client", new_slug=None, no_regenerate=True))

    renamed = project / "output" / "good-01112026-Dev-Real-Client"
    assert renamed.is_dir() and not pack.exists()
    assert db.get_application(app_id)["output_folder"] == str(renamed)
    patched = json.loads((renamed / "_prep" / "job_offer_analysis.json").read_text(encoding="utf-8"))
    assert patched["company_name"] == "Real Client"


# ---------------------------------------------------------------------------
# repair-output-folders
# ---------------------------------------------------------------------------


def _seed_repair_db(tmp_path: Path) -> tuple[Path, Path, dict[str, int]]:
    root = tmp_path / "project"
    out = root / "output"
    (out / "good-01112026-Dev-Acme").mkdir(parents=True)
    (out / "cold-02112026-beta").mkdir()
    local = out / "medium-03112026-Dev-Gamma"
    local.mkdir()
    db_path = tmp_path / "h.db"
    db = JobHistoryDB(str(db_path))
    try:
        ids = {
            "cloud": _add(db, "/sessions/a1/mnt/Job Prospecting/output/good-01112026-Dev-Acme"),
            "windows": _add(db, r"Z:\old-pc\output\cold-02112026-beta", company="Beta"),
            "fine": _add(db, str(local), company="Gamma"),
            "gone": _add(db, "/sessions/a1/mnt/Job Prospecting/output/vanished", company="Delta"),
            "none": db.add_application(company_name="Eps", job_title="Dev"),
        }
    finally:
        db.close()
    return root, db_path, ids


def _repair(tmp_path: Path, db_path: Path, root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), "--db", str(db_path), "repair-output-folders",
         "--project-root", str(root), *extra],
        capture_output=True, text=True, encoding="utf-8", cwd=str(SKILL_ROOT),
        env=dict(os.environ, JOB_TAILOR_HOME=str(tmp_path / "home"), PYTHONUTF8="1"),
    )


def _folders(db_path: Path) -> dict[int, str | None]:
    db = JobHistoryDB(str(db_path))
    try:
        return {a["id"]: a["output_folder"] for a in db.list_applications(limit=100)}
    finally:
        db.close()


def test_repair_dry_run_reports_and_writes_nothing(tmp_path: Path) -> None:
    root, db_path, ids = _seed_repair_db(tmp_path)
    before = _folders(db_path)

    result = _repair(tmp_path, db_path, root)

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "already fine          : 1" in out
    assert "repairable (by name)  : 2" in out
    assert "missing everywhere    : 1" in out
    assert "no folder recorded    : 1" in out
    assert "vanished" in out and "Dry run" in out
    assert _folders(db_path) == before
    assert not (tmp_path / "db-backups").exists(), "a dry run must not take a snapshot"


def test_repair_apply_rewrites_only_relocatable_rows(tmp_path: Path) -> None:
    root, db_path, ids = _seed_repair_db(tmp_path)
    before = _folders(db_path)

    result = _repair(tmp_path, db_path, root, "--apply")

    assert result.returncode == 0, result.stderr
    after = _folders(db_path)
    assert after[ids["cloud"]] == str(root / "output" / "good-01112026-Dev-Acme")
    assert after[ids["windows"]] == str(root / "output" / "cold-02112026-beta")
    for key in ("fine", "gone", "none"):
        assert after[ids[key]] == before[ids[key]], key
    assert list((tmp_path / "db-backups").glob("h-*.db")), "--apply must snapshot first"

    # idempotent: nothing left to repair
    again = _repair(tmp_path, db_path, root)
    assert "repairable (by name)  : 0" in again.stdout
