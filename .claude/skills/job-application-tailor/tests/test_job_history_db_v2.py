"""Tests for the Phase F v1 -> v2 schema migration on job_history.db.

The cold-prospect skill adds two columns to ``applications``:

- ``source`` (``'offer'`` default / ``'cold'``) — segments offer-flow rows
  from speculative-application rows.
- ``company_profile_snapshot`` — compact JSON subset of the researched
  company profile, persisted for later dashboards.

These tests pin the behaviour users depend on when they upgrade an
already-populated v1 DB:

1. The migration runs automatically on first open and preserves legacy
   rows by giving them ``source='offer'`` via the column default.
2. Cold inserts round-trip (``source='cold'`` + JSON snapshot).
3. Unknown ``source`` values are rejected at the API boundary rather
   than landing in the DB and corrupting downstream stats.
4. A fresh DB is created at v2 directly — no upgrade path is traversed.
5. Reopening a v2 DB is a no-op — the migration is idempotent.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.job_history_db import JobHistoryDB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_V1_SCHEMA_SQL = """
CREATE TABLE schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT NOT NULL,
    company_norm    TEXT NOT NULL,
    job_title       TEXT NOT NULL,
    job_title_norm  TEXT NOT NULL,
    location        TEXT,
    source_url      TEXT,
    domain          TEXT,
    seniority       TEXT,
    fit_level       TEXT,
    fit_pct         REAL,
    direct_count    INTEGER,
    transferable_count INTEGER,
    gap_count       INTEGER,
    output_folder   TEXT,
    detected_language TEXT,
    status          TEXT NOT NULL DEFAULT 'generated',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE job_skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    skill           TEXT NOT NULL,
    skill_norm      TEXT NOT NULL,
    skill_type      TEXT NOT NULL CHECK(skill_type IN ('required', 'preferred'))
);

CREATE TABLE company_lists (
    company_norm    TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    list_type       TEXT NOT NULL CHECK(list_type IN ('blacklist', 'whitelist')),
    reason          TEXT,
    created_at      TEXT NOT NULL
);
"""


def _build_v1_db(path: Path, *, with_legacy_row: bool = True) -> None:
    """Create a pre-Phase-F schema at ``path``. Nothing imports the
    production ``JobHistoryDB`` code here — we want the DB to look exactly
    the way a user's months-old install looks on disk."""
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_V1_SCHEMA_SQL)
        conn.execute("INSERT INTO schema_version(version) VALUES(1)")
        if with_legacy_row:
            conn.execute(
                """INSERT INTO applications
                   (company_name, company_norm, job_title, job_title_norm,
                    status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    "LegacyCorp",
                    "legacycorp",
                    "Senior Engineer",
                    "senior engineer",
                    "generated",
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _column_names(db_path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return [r[1] for r in rows]
    finally:
        conn.close()


def _schema_version(db_path: Path) -> int | None:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# v1 -> v2 migration
# ---------------------------------------------------------------------------


def test_v1_db_upgrades_on_first_open(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    _build_v1_db(db_path)
    assert _schema_version(db_path) == 1

    db = JobHistoryDB(str(db_path))
    try:
        assert _schema_version(db_path) == 2
        cols = _column_names(db_path, "applications")
        assert "source" in cols
        assert "company_profile_snapshot" in cols
    finally:
        db.close()


def test_legacy_rows_default_to_source_offer(tmp_path: Path) -> None:
    """The whole point of adding the column with a DEFAULT — users must
    not have to run a backfill for their existing application history."""
    db_path = tmp_path / "history.db"
    _build_v1_db(db_path)

    db = JobHistoryDB(str(db_path))
    try:
        row = db._conn.execute(
            "SELECT source, company_profile_snapshot FROM applications "
            "WHERE company_name = ?",
            ("LegacyCorp",),
        ).fetchone()
        assert row["source"] == "offer"
        assert row["company_profile_snapshot"] is None
    finally:
        db.close()


def test_reopen_of_v2_db_is_noop(tmp_path: Path) -> None:
    """Idempotency: opening a v2 DB must not re-run the v1->v2 ALTER
    TABLE (SQLite would raise ``duplicate column name`` if it did)."""
    db_path = tmp_path / "history.db"
    _build_v1_db(db_path)

    # First open triggers the upgrade.
    JobHistoryDB(str(db_path)).close()
    assert _schema_version(db_path) == 2

    # Second open must silently succeed.
    db = JobHistoryDB(str(db_path))
    try:
        assert _schema_version(db_path) == 2
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fresh DB: v2 on creation
# ---------------------------------------------------------------------------


def test_fresh_db_is_created_at_v2(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    db = JobHistoryDB(str(db_path))
    try:
        assert _schema_version(db_path) == 2
        cols = _column_names(db_path, "applications")
        assert "source" in cols
        assert "company_profile_snapshot" in cols
    finally:
        db.close()


# ---------------------------------------------------------------------------
# add_application — source + snapshot + validation
# ---------------------------------------------------------------------------


def test_add_application_defaults_to_offer_source(tmp_path: Path) -> None:
    """The tailor (offer) flow never passes ``source`` — its rows must
    still end up tagged ``'offer'`` so stats by source stay correct."""
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(
            company_name="OfferCo",
            job_title="Backend Engineer",
        )
        row = db.get_application(app_id)
        assert row is not None
        assert row["source"] == "offer"
        assert row["company_profile_snapshot"] is None
    finally:
        db.close()


def test_add_application_cold_round_trip(tmp_path: Path) -> None:
    """Full cold-flow insert: source='cold' plus a JSON snapshot of the
    researched company profile. Both must read back exactly as written."""
    snapshot = {
        "company_name": "Acme SAS",
        "canonical_url": "https://acme.example",
        "industry": "Robotics",
        "size_band": "scaleup",
        "mission_statement": "Build useful robots.",
    }
    snap_json = json.dumps(snapshot, ensure_ascii=False)

    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(
            company_name="Acme SAS",
            job_title="Tech Lead .NET — Desktop & Services",
            source="cold",
            company_profile_snapshot=snap_json,
            output_folder="/tmp/output/cold-20260420-acme-sas",
            detected_language="fr",
        )
        row = db.get_application(app_id)
        assert row is not None
        assert row["source"] == "cold"
        assert row["output_folder"] == "/tmp/output/cold-20260420-acme-sas"
        # The snapshot is stored as opaque text — we just need round-trip.
        assert json.loads(row["company_profile_snapshot"]) == snapshot
    finally:
        db.close()


def test_add_application_rejects_unknown_source(tmp_path: Path) -> None:
    """Guard the column at the API boundary — the CHECK constraint
    approach would be additive to the schema, but a Python-side check
    catches the mistake before it hits the DB and keeps the error message
    useful."""
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        with pytest.raises(ValueError, match="source must be"):
            db.add_application(
                company_name="Bad",
                job_title="Engineer",
                source="speculative_v2",
            )
        # The write must not have landed.
        assert db.total_count() == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# _upgrade_schema — direct unit-level check
# ---------------------------------------------------------------------------


def test_upgrade_schema_is_idempotent_on_partial_state(tmp_path: Path) -> None:
    """Belt-and-braces: if a prior run added `source` but crashed before
    `company_profile_snapshot` landed, the next open must fill the gap
    rather than erroring with ``duplicate column name``."""
    db_path = tmp_path / "history.db"
    _build_v1_db(db_path)

    # Simulate the half-migrated state by manually adding only `source`.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "ALTER TABLE applications ADD COLUMN source TEXT NOT NULL DEFAULT 'offer'"
        )
        conn.commit()
    finally:
        conn.close()

    db = JobHistoryDB(str(db_path))
    try:
        cols = _column_names(db_path, "applications")
        assert "source" in cols
        assert "company_profile_snapshot" in cols
        assert _schema_version(db_path) == 2
    finally:
        db.close()
