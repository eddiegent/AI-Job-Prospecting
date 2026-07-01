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

from scripts.job_history_db import JobHistoryDB, compute_content_fingerprint


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
