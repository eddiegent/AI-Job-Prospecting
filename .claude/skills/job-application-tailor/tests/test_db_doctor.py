"""Tests for the content fingerprint behind `cli.py doctor` (roadmap 1.1).

The fingerprint exists to detect when the history DB has been silently
replaced/restored across sessions (or when the temp working mirror has drifted
from the canonical target). For that to work it must be:

- **content-based and order-independent** — two DBs holding the same set of
  applications produce the same fingerprint regardless of insertion order, so a
  different *lineage* with the same content doesn't raise a false alarm, and the
  same content in a different rowid layout still matches;
- **sensitive to real changes** — adding a row or changing a status changes it.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# cli.py uses flat imports (`from common import ...`), so it — and the siblings
# it pulls in — must be importable as top-level modules. Put scripts/ on the
# path and import from there (not `scripts.cli`) so the JobHistoryDB the test
# builds is the same class cli.py operates on.
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from cli import cmd_update_status  # noqa: E402
from job_history_db import JobHistoryDB, compute_content_fingerprint  # noqa: E402


def _fp(db: JobHistoryDB) -> dict:
    return compute_content_fingerprint(db._conn)


def _add(db: JobHistoryDB, company: str, title: str, created: str) -> int:
    return db.add_application(company_name=company, job_title=title, created_at=created)


def test_empty_db_fingerprint(tmp_path):
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        info = _fp(db)
        assert info["row_count"] == 0
        assert info["max_id"] is None
        assert info["schema_version"] == 2
        assert isinstance(info["fingerprint"], str) and len(info["fingerprint"]) == 16
    finally:
        db.close()


def test_fingerprint_is_deterministic(tmp_path):
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        _add(db, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        _add(db, "Globex", "Consultant C#", "2026-01-02T00:00:00")
        assert _fp(db)["fingerprint"] == _fp(db)["fingerprint"]
    finally:
        db.close()


def test_fingerprint_is_order_independent(tmp_path):
    """Same applications inserted in a different order → same fingerprint.
    This is what lets us compare two DB lineages by content."""
    a = JobHistoryDB(str(tmp_path / "a.db"))
    b = JobHistoryDB(str(tmp_path / "b.db"))
    try:
        _add(a, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        _add(a, "Globex", "Consultant C#", "2026-01-02T00:00:00")
        # b: reversed insertion order → different autoincrement ids, same content
        _add(b, "Globex", "Consultant C#", "2026-01-02T00:00:00")
        _add(b, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        assert _fp(a)["fingerprint"] == _fp(b)["fingerprint"]
        assert _fp(a)["max_id"] == _fp(b)["max_id"] == 2
    finally:
        a.close()
        b.close()


def test_fingerprint_changes_on_new_row(tmp_path):
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        _add(db, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        before = _fp(db)["fingerprint"]
        _add(db, "Globex", "Consultant C#", "2026-01-02T00:00:00")
        assert _fp(db)["fingerprint"] != before
    finally:
        db.close()


def test_fingerprint_changes_on_status_change(tmp_path):
    db = JobHistoryDB(str(tmp_path / "h.db"))
    try:
        aid = _add(db, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        before = _fp(db)["fingerprint"]
        db.update_status(aid, "applied")
        assert _fp(db)["fingerprint"] != before
    finally:
        db.close()


# ---------------------------------------------------------------------------
# snapshot_before_mutation (roadmap 1.2)
# ---------------------------------------------------------------------------


def test_snapshot_creates_backup(tmp_path):
    db = JobHistoryDB(str(tmp_path / "job_history.db"))
    try:
        _add(db, "Acme", "Dev", "2026-01-01T00:00:00")
        snap = db.snapshot_before_mutation()
        assert snap is not None and snap.exists()
        assert snap.parent.name == "db-backups"
        assert snap.name.startswith("job_history-") and snap.suffix == ".db"
    finally:
        db.close()


def test_snapshot_prunes_to_keep(tmp_path):
    db = JobHistoryDB(str(tmp_path / "job_history.db"))
    try:
        backups = tmp_path / "db-backups"
        backups.mkdir()
        # Five older snapshots with deterministic (earlier) timestamps.
        for i in range(1, 6):
            (backups / f"job_history-20260101-00000{i}.db").write_bytes(b"x")
        db.snapshot_before_mutation(keep=3)  # today's stamp sorts newest
        remaining = sorted(backups.glob("job_history-*.db"))
        assert len(remaining) == 3, [p.name for p in remaining]
        # The just-created snapshot (not a 20260101 seed) survives pruning.
        assert any(not p.name.startswith("job_history-20260101") for p in remaining)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# --expect-company id-reuse guard (roadmap 1.3)
# ---------------------------------------------------------------------------


def test_expect_company_mismatch_refuses(tmp_path):
    """A remembered id that now names a different company must fail loudly
    (exit 2) and leave the row unchanged — the post-divergence hazard."""
    db = JobHistoryDB(str(tmp_path / "job_history.db"))
    try:
        aid = _add(db, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        args = SimpleNamespace(id=aid, status="applied", expect_company="Globex")
        with pytest.raises(SystemExit) as exc:
            cmd_update_status(db, args)
        assert exc.value.code == 2
        assert db.get_application(aid)["status"] == "generated"  # untouched
    finally:
        db.close()


def test_expect_company_match_proceeds(tmp_path):
    """Matching company (case/whitespace-insensitive via normalise) proceeds."""
    db = JobHistoryDB(str(tmp_path / "job_history.db"))
    try:
        aid = _add(db, "Acme SAS", "Dev .NET", "2026-01-01T00:00:00")
        args = SimpleNamespace(id=aid, status="applied", expect_company="acme sas")
        cmd_update_status(db, args)
        assert db.get_application(aid)["status"] == "applied"
    finally:
        db.close()
