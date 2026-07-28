"""Tests for the Phase 2 v2 -> v3 schema migration on job_history.db.

Phase 2 (PIPELINE_HARDENING_ROADMAP) adds one column to ``applications``:

- ``org_type`` — the researched organisation type (``end_employer`` / ``esn``
  / ``staffing_agency`` / ``recruitment_agency`` / ``unknown``). Only the cold
  flow populates it; offer-flow and legacy rows stay NULL.

These tests pin:

1. The v2 -> v3 migration runs automatically and leaves existing rows NULL
   (no backfill needed).
2. A v1 DB fast-forwards straight to v3, gaining every intermediate column.
3. Cold inserts round-trip org_type; offer inserts leave it NULL.
4. Unknown org_type values are rejected at the API boundary.
5. The migration is idempotent (reopening a v3 DB is a no-op).
6. The new segmentation filters (``source`` / ``org_type``) narrow every
   reporting/list method consistently.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.job_history_db import _SCHEMA_VERSION, JobHistoryDB


# ---------------------------------------------------------------------------
# Helpers — build a real on-disk v2 DB the way a months-old install looks
# ---------------------------------------------------------------------------

_V2_SCHEMA_SQL = """
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
    source          TEXT NOT NULL DEFAULT 'offer',
    company_profile_snapshot TEXT,
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

_V1_SCHEMA_SQL = _V2_SCHEMA_SQL.replace(
    "    source          TEXT NOT NULL DEFAULT 'offer',\n"
    "    company_profile_snapshot TEXT,\n",
    "",
)


def _build_db(path: Path, sql: str, version: int, *, with_legacy_row: bool = True) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(sql)
        conn.execute("INSERT INTO schema_version(version) VALUES(?)", (version,))
        if with_legacy_row:
            conn.execute(
                """INSERT INTO applications
                   (company_name, company_norm, job_title, job_title_norm,
                    status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    "LegacyCorp", "legacycorp",
                    "Senior Engineer", "senior engineer",
                    "generated", "2026-01-01T00:00:00", "2026-01-01T00:00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _column_names(db_path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    finally:
        conn.close()


def _schema_version(db_path: Path) -> int | None:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# v2 -> v3 migration
# ---------------------------------------------------------------------------


def test_v2_db_upgrades_to_v3_on_first_open(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    _build_db(db_path, _V2_SCHEMA_SQL, 2)
    assert _schema_version(db_path) == 2

    db = JobHistoryDB(str(db_path))
    try:
        assert _schema_version(db_path) == _SCHEMA_VERSION
        assert "org_type" in _column_names(db_path, "applications")
    finally:
        db.close()


def test_legacy_rows_get_null_org_type(tmp_path: Path) -> None:
    """Adding org_type without a DEFAULT means existing rows read back NULL —
    no backfill required, and NULL is the correct 'unclassified' value."""
    db_path = tmp_path / "history.db"
    _build_db(db_path, _V2_SCHEMA_SQL, 2)

    db = JobHistoryDB(str(db_path))
    try:
        row = db._conn.execute(
            "SELECT org_type FROM applications WHERE company_name = ?", ("LegacyCorp",)
        ).fetchone()
        assert row["org_type"] is None
    finally:
        db.close()


def test_v1_db_fast_forwards_to_v3(tmp_path: Path) -> None:
    """A very old (v1) DB must gain source, company_profile_snapshot AND
    org_type in one open — every intermediate migration clause runs."""
    db_path = tmp_path / "history.db"
    _build_db(db_path, _V1_SCHEMA_SQL, 1)
    assert _schema_version(db_path) == 1

    db = JobHistoryDB(str(db_path))
    try:
        assert _schema_version(db_path) == _SCHEMA_VERSION
        cols = _column_names(db_path, "applications")
        assert {"source", "company_profile_snapshot", "org_type"} <= set(cols)
        row = db._conn.execute(
            "SELECT source, org_type FROM applications WHERE company_name = ?",
            ("LegacyCorp",),
        ).fetchone()
        assert row["source"] == "offer"     # from the v2 default
        assert row["org_type"] is None       # v3 column, no backfill
    finally:
        db.close()


def test_reopen_of_v3_db_is_noop(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    _build_db(db_path, _V2_SCHEMA_SQL, 2)
    JobHistoryDB(str(db_path)).close()
    assert _schema_version(db_path) == _SCHEMA_VERSION

    db = JobHistoryDB(str(db_path))
    try:
        assert _schema_version(db_path) == _SCHEMA_VERSION
    finally:
        db.close()


def test_fresh_db_is_created_at_v3(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "fresh.db"))
    try:
        assert _schema_version(tmp_path / "fresh.db") == _SCHEMA_VERSION
        assert "org_type" in _column_names(tmp_path / "fresh.db", "applications")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# add_application — org_type round-trip + validation
# ---------------------------------------------------------------------------


def test_offer_insert_leaves_org_type_null(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(company_name="OfferCo", job_title="Backend Eng")
        assert db.get_application(app_id)["org_type"] is None
    finally:
        db.close()


@pytest.mark.parametrize(
    "org_type",
    ["end_employer", "esn", "staffing_agency", "recruitment_agency", "unknown"],
)
def test_cold_insert_round_trips_org_type(tmp_path: Path, org_type: str) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(
            company_name="EsnCo", job_title="Consultant",
            source="cold", org_type=org_type,
        )
        assert db.get_application(app_id)["org_type"] == org_type
    finally:
        db.close()


def test_add_application_rejects_unknown_org_type(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        with pytest.raises(ValueError, match="org_type must be"):
            db.add_application(
                company_name="Bad", job_title="Engineer",
                source="cold", org_type="headhunter",
            )
        assert db.total_count() == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Segmentation filters — source / org_type
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_db(tmp_path: Path):
    db = JobHistoryDB(str(tmp_path / "seg.db"))
    db.add_application(
        company_name="OfferCo", job_title="Backend Eng",
        fit_level="good", fit_pct=80.0, domain="Fintech",
        required_skills=["python", "sql"],
    )
    db.add_application(
        company_name="EsnCo", job_title="Consultant",
        source="cold", org_type="esn", domain="ESN",
        required_skills=["python", "azure"],
    )
    db.add_application(
        company_name="AcmeRobots", job_title="Dev",
        source="cold", org_type="end_employer", domain="Robotics",
        required_skills=["cpp"],
    )
    try:
        yield db
    finally:
        db.close()


def test_total_count_filters(seeded_db) -> None:
    assert seeded_db.total_count() == 3
    assert seeded_db.total_count(source="cold") == 2
    assert seeded_db.total_count(source="offer") == 1
    assert seeded_db.total_count(org_type="esn") == 1
    assert seeded_db.total_count(source="cold", org_type="end_employer") == 1


def test_list_applications_filters(seeded_db) -> None:
    cold = seeded_db.list_applications(source="cold")
    assert {a["company_name"] for a in cold} == {"EsnCo", "AcmeRobots"}
    esn = seeded_db.list_applications(org_type="esn")
    assert [a["company_name"] for a in esn] == ["EsnCo"]


def test_stats_by_org_type_buckets_null_as_unset(seeded_db) -> None:
    rows = {r["org_type"]: r["count"] for r in seeded_db.stats_by_org_type()}
    assert rows == {"esn": 1, "end_employer": 1, "(unset)": 1}
    # Filtered to the cold flow, the offer row's (unset) bucket disappears.
    cold_rows = {r["org_type"]: r["count"] for r in seeded_db.stats_by_org_type(source="cold")}
    assert cold_rows == {"esn": 1, "end_employer": 1}


def test_stats_by_status_and_domain_filters(seeded_db) -> None:
    offer_domains = {r["domain"] for r in seeded_db.stats_by_domain(source="offer")}
    assert offer_domains == {"Fintech"}
    cold_statuses = seeded_db.stats_by_status(source="cold")
    assert sum(r["count"] for r in cold_statuses) == 2


def test_skill_trends_filters(seeded_db) -> None:
    cold_skills = {r["skill"] for r in seeded_db.skill_gap_trends(source="cold")}
    assert cold_skills == {"python", "azure", "cpp"}
    offer_skills = {r["skill"] for r in seeded_db.skill_gap_trends(source="offer")}
    assert offer_skills == {"python", "sql"}
    # avg_fit_pct ignores NULLs: the offer row (fit 80) is the only one with a
    # score, so python's average across offer rows is 80.0 — cold NULLs excluded.
    offer_python = next(r for r in seeded_db.skill_gap_trends(source="offer") if r["skill"] == "python")
    assert offer_python["avg_fit_pct"] == 80.0
