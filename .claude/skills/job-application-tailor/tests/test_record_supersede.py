"""Tests for `record-application --supersede` (PIPELINE_HARDENING_ROADMAP 3.3).

Re-prospecting a company on a later date used to leave two live rows (the
`#41` vs `#100` duplication) because the dated folder name differs, so no
collision fired. `--supersede` marks the prior duplicate row `dropped` before
recording the new one, so the pipeline shows one active application per role.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from cli import cmd_record_application  # noqa: E402
from job_history_db import JobHistoryDB  # noqa: E402


def _cold_folder(base: Path, name: str, *, title: str = "Tech Lead .NET") -> Path:
    folder = base / name
    prep = folder / "_prep"
    prep.mkdir(parents=True)
    (prep / "company_profile.json").write_text(json.dumps({
        "company_name": "Acme SAS",
        "canonical_url": "https://acme.example",
        "industry": "Robotics",
        "org_type": "end_employer",
        "size_band": "scaleup",
        "locations": ["Paris"],
        "mission_statement": "Build robots.",
        "research_gaps": [],
    }), encoding="utf-8")
    (prep / "selected_role.json").write_text(
        json.dumps({"title": title, "seniority_band": "senior"}), encoding="utf-8"
    )
    return folder


def _record(db, folder, *, supersede=False):
    cmd_record_application(db, SimpleNamespace(
        target=str(folder), url=None, source=None, language=None,
        dry_run=False, supersede=supersede,
    ))


def test_supersede_drops_prior_same_company_role(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        _record(db, _cold_folder(tmp_path, "cold-01012026-acme"))
        _record(db, _cold_folder(tmp_path, "cold-15062026-acme"), supersede=True)

        rows = db.list_applications()
        assert len(rows) == 2
        by_status = {r["status"] for r in rows}
        assert by_status == {"generated", "dropped"}
        # Exactly one live row remains for the company+role.
        live = [r for r in rows if r["status"] != "dropped"]
        assert len(live) == 1
        assert live[0]["output_folder"].endswith("cold-15062026-acme")
    finally:
        db.close()


def test_without_supersede_leaves_parallel_rows(tmp_path: Path) -> None:
    """Baseline: the old behaviour (two live rows) still happens without the
    flag — supersede is opt-in, never automatic."""
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        _record(db, _cold_folder(tmp_path, "cold-01012026-acme"))
        _record(db, _cold_folder(tmp_path, "cold-15062026-acme"))
        rows = db.list_applications()
        assert len(rows) == 2
        assert all(r["status"] == "generated" for r in rows)
    finally:
        db.close()


def test_supersede_ignores_different_role(tmp_path: Path) -> None:
    """A different role at the same company is a distinct application, not a
    duplicate — supersede must not drop it."""
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        _record(db, _cold_folder(tmp_path, "cold-01012026-acme", title="Data Engineer"))
        _record(db, _cold_folder(tmp_path, "cold-15062026-acme", title="Tech Lead .NET"),
                supersede=True)
        rows = db.list_applications()
        assert len(rows) == 2
        assert all(r["status"] == "generated" for r in rows)
    finally:
        db.close()
