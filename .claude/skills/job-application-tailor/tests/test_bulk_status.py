"""Tests for the `bulk-status` subcommand (PIPELINE_HARDENING_ROADMAP 3.2).

Bulk status lets the user move several applications to the same status in one
call instead of issuing `update-status` one id at a time. The contract:

- every existing id is updated to the target status;
- a missing id is skipped (not fatal to the rest) but makes the command exit
  non-zero so a typo in a batch doesn't pass silently;
- duplicate ids in the argument list are applied once.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from scripts.commands.status import cmd_bulk_status  # noqa: E402
from job_history_db import JobHistoryDB  # noqa: E402


def _seed(db: JobHistoryDB, *companies: str) -> list[int]:
    return [db.add_application(company_name=c, job_title="Dev") for c in companies]


def test_bulk_status_updates_all_ids(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        ids = _seed(db, "Alpha", "Beta", "Gamma")
        cmd_bulk_status(db, SimpleNamespace(ids=ids, status="applied"))
        for app_id in ids:
            assert db.get_application(app_id)["status"] == "applied"
    finally:
        db.close()


def test_bulk_status_skips_missing_and_exits_nonzero(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        (existing,) = _seed(db, "Alpha")
        with pytest.raises(SystemExit) as exc:
            cmd_bulk_status(db, SimpleNamespace(ids=[existing, 999], status="interview"))
        assert exc.value.code == 1
        # The valid id was still updated despite the missing sibling.
        assert db.get_application(existing)["status"] == "interview"
    finally:
        db.close()


def test_bulk_status_deduplicates_ids(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        (app_id,) = _seed(db, "Alpha")
        cmd_bulk_status(db, SimpleNamespace(ids=[app_id, app_id], status="offer"))
        assert db.get_application(app_id)["status"] == "offer"
    finally:
        db.close()
