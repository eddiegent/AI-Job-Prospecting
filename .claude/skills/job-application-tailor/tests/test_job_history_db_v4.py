"""Tests for the v3 -> v4 schema migration: the `application_events` history.

Before v4 a status change overwrote ``applications.status`` and bumped
``updated_at``, so only the LATEST transition survived. v4 adds an append-only
``application_events`` table alongside it — ``applications.status`` stays the
cached current value so every existing query and index keeps working, while the
events preserve the sequence that used to be lost.

These tests pin:

1. The v3 -> v4 migration runs automatically and reconstructs what is still
   knowable from ``created_at`` / ``updated_at``.
2. Rows already past ``applied`` get an inferred ``applied`` event — without it
   the funnel undercounts, because their real ``applied`` event was overwritten.
3. Every reconstructed row carries the ``[backfill]`` marker, and
   ``response_times()`` excludes them: their dates were inferred, so a duration
   measured against one describes the generation date, not a real reply.
4. The migration is idempotent — reopening never double-inserts.
5. New applications and status changes record events going forward, including
   backdating via ``occurred_at``.
6. Deleting an application cascades to its events.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.job_history_db import _BACKFILL_NOTE, JobHistoryDB


# ---------------------------------------------------------------------------
# Helpers — build a real on-disk v3 DB the way a pre-v4 install looks
# ---------------------------------------------------------------------------

_V3_SCHEMA_SQL = """
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
    org_type        TEXT,
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

# (company, status, created_at, updated_at) — one row per shape the backfill
# has to reason about: never moved, moved once, and moved past `applied`.
_LEGACY_ROWS = [
    ("StillGenerated", "generated", "2026-01-05T09:00:00", "2026-01-05T09:00:00"),
    ("TouchedButGenerated", "generated", "2026-01-06T09:00:00", "2026-02-01T09:00:00"),
    ("Applied", "applied", "2026-01-07T09:00:00", "2026-01-20T09:00:00"),
    ("Rejected", "rejected", "2026-01-08T09:00:00", "2026-02-10T09:00:00"),
    ("Interview", "interview", "2026-01-09T09:00:00", "2026-02-11T09:00:00"),
    ("Dropped", "dropped", "2026-01-10T09:00:00", "2026-02-12T09:00:00"),
]


def _build_v3_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.executescript(_V3_SCHEMA_SQL)
        conn.execute("INSERT INTO schema_version(version) VALUES(3)")
        for company, status, created, updated in _LEGACY_ROWS:
            conn.execute(
                """INSERT INTO applications
                   (company_name, company_norm, job_title, job_title_norm,
                    status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (company, company.lower(), "Engineer", "engineer", status, created, updated),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def migrated(tmp_path: Path) -> JobHistoryDB:
    """A v3 DB opened once through JobHistoryDB, i.e. migrated to v4."""
    db_path = tmp_path / "job_history.db"
    _build_v3_db(db_path)
    db = JobHistoryDB(db_path)
    yield db
    db.close()


def _events(db: JobHistoryDB, company: str) -> list[dict]:
    row = db._conn.execute(
        "SELECT id FROM applications WHERE company_name = ?", (company,)
    ).fetchone()
    return db.application_events(row["id"])


# ---------------------------------------------------------------------------
# 1. Migration runs and reconstructs the knowable history
# ---------------------------------------------------------------------------


def test_migration_bumps_schema_version(migrated: JobHistoryDB) -> None:
    version = migrated._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == 4


def test_every_application_gets_a_generated_event(migrated: JobHistoryDB) -> None:
    for company, _status, created, _updated in _LEGACY_ROWS:
        events = _events(migrated, company)
        assert events[0]["status"] == "generated"
        assert events[0]["occurred_at"] == created


def test_untouched_row_has_only_its_birth_event(migrated: JobHistoryDB) -> None:
    assert len(_events(migrated, "StillGenerated")) == 1


def test_row_still_generated_gets_no_second_event(migrated: JobHistoryDB) -> None:
    """A folder rename bumps `updated_at` without changing status.

    Emitting a second 'generated' event there would invent a transition that
    never happened, so the backfill skips rows whose status never moved.
    """
    assert len(_events(migrated, "TouchedButGenerated")) == 1


def test_moved_row_lands_on_its_current_status(migrated: JobHistoryDB) -> None:
    events = _events(migrated, "Applied")
    assert [e["status"] for e in events] == ["generated", "applied"]
    assert events[-1]["occurred_at"] == "2026-01-20T09:00:00"


# ---------------------------------------------------------------------------
# 2. Rows past `applied` get the inferred applied event
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("company", ["Rejected", "Interview"])
def test_rows_past_applied_gain_an_inferred_applied_event(
    migrated: JobHistoryDB, company: str
) -> None:
    statuses = [e["status"] for e in _events(migrated, company)]
    assert statuses == ["generated", "applied", company.lower()]


def test_dropped_does_not_imply_applied(migrated: JobHistoryDB) -> None:
    """`dropped` means "decided not to pursue" — it does not imply applying."""
    statuses = [e["status"] for e in _events(migrated, "Dropped")]
    assert "applied" not in statuses


def test_funnel_counts_everyone_who_ever_applied(migrated: JobHistoryDB) -> None:
    stages = {s["stage"]: s["count"] for s in migrated.funnel()["stages"]}
    # Applied + Rejected + Interview — the last two had their applied event
    # overwritten before v4 existed, and counting current status would miss them.
    assert stages["applied"] == 3
    assert stages["interview"] == 1
    assert stages["generated"] == len(_LEGACY_ROWS)


def test_funnel_reports_exits_separately(migrated: JobHistoryDB) -> None:
    exits = migrated.funnel()["exits"]
    assert exits == {"rejected": 1, "dropped": 1}


# ---------------------------------------------------------------------------
# 3. Backfilled rows are marked, and excluded from response times
# ---------------------------------------------------------------------------


def test_every_backfilled_event_is_marked(migrated: JobHistoryDB) -> None:
    notes = [
        r["note"] for r in migrated._conn.execute("SELECT note FROM application_events")
    ]
    assert notes and all(n.startswith(_BACKFILL_NOTE) for n in notes)


def test_response_times_ignores_backfilled_events(migrated: JobHistoryDB) -> None:
    """The inferred `applied` date is anchored to `created_at`, so a duration
    measured from it reports how long the pack sat around, not how fast anyone
    replied. Better to report nothing than a confident wrong number."""
    assert migrated.response_times() == []


def test_response_time_appears_once_a_real_transition_is_recorded(
    migrated: JobHistoryDB,
) -> None:
    app_id = migrated.add_application(
        company_name="Fresh", job_title="Engineer", created_at="2026-02-01T09:00:00"
    )
    migrated.update_status(app_id, "applied", occurred_at="2026-03-01T12:00:00")
    migrated.update_status(app_id, "interview", occurred_at="2026-03-09T12:00:00")
    rows = migrated.response_times()
    assert len(rows) == 1
    assert rows[0]["days"] == pytest.approx(8.0)
    assert rows[0]["next_status"] == "interview"


def test_pending_application_reports_no_duration(migrated: JobHistoryDB) -> None:
    app_id = migrated.add_application(
        company_name="Waiting", job_title="Engineer", created_at="2026-02-01T09:00:00"
    )
    migrated.update_status(app_id, "applied", occurred_at="2026-03-01T12:00:00")
    rows = migrated.response_times()
    assert len(rows) == 1
    assert rows[0]["days"] is None


def test_hand_typed_note_cannot_masquerade_as_backfill(migrated: JobHistoryDB) -> None:
    """The marker is bracketed so a free-text `--note` can't collide with it and
    silently drop a real measurement out of the report."""
    app_id = migrated.add_application(
        company_name="Noted", job_title="Engineer", created_at="2026-02-01T09:00:00"
    )
    migrated.update_status(
        app_id, "applied", occurred_at="2026-03-01T12:00:00", note="backfilled by hand"
    )
    migrated.update_status(app_id, "rejected", occurred_at="2026-03-05T12:00:00")
    assert [r["company_name"] for r in migrated.response_times()] == ["Noted"]


# ---------------------------------------------------------------------------
# 4. Idempotency
# ---------------------------------------------------------------------------


def test_migration_does_not_double_insert(tmp_path: Path) -> None:
    db_path = tmp_path / "job_history.db"
    _build_v3_db(db_path)
    db = JobHistoryDB(db_path)
    first = db._conn.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
    db.close()
    db = JobHistoryDB(db_path)
    try:
        assert db._conn.execute(
            "SELECT COUNT(*) FROM application_events"
        ).fetchone()[0] == first
    finally:
        db.close()


def test_fresh_database_has_no_backfill(tmp_path: Path) -> None:
    db = JobHistoryDB(tmp_path / "new.db")
    try:
        assert db._conn.execute("SELECT COUNT(*) FROM application_events").fetchone()[0] == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 5. Events going forward
# ---------------------------------------------------------------------------


def test_new_application_opens_its_history(migrated: JobHistoryDB) -> None:
    app_id = migrated.add_application(company_name="Brand New", job_title="Engineer")
    events = migrated.application_events(app_id)
    assert len(events) == 1
    assert events[0]["status"] == "generated"


def test_add_application_event_matches_created_at(migrated: JobHistoryDB) -> None:
    """A replayed run passes an explicit `created_at`; the event must follow it
    rather than stamping "now", or the row and its history disagree."""
    app_id = migrated.add_application(
        company_name="Replayed", job_title="Engineer", created_at="2025-12-01T08:00:00"
    )
    assert migrated.application_events(app_id)[0]["occurred_at"] == "2025-12-01T08:00:00"


def test_update_status_records_note_and_backdate(migrated: JobHistoryDB) -> None:
    app_id = migrated.add_application(
        company_name="Backdated", job_title="Engineer", created_at="2026-02-01T09:00:00"
    )
    migrated.update_status(
        app_id, "applied", occurred_at="2026-02-14T09:30:00", note="via referral"
    )
    last = migrated.application_events(app_id)[-1]
    assert last["occurred_at"] == "2026-02-14T09:30:00"
    assert last["note"] == "via referral"
    assert migrated.get_application(app_id)["status"] == "applied"


def test_update_status_on_missing_id_writes_nothing(migrated: JobHistoryDB) -> None:
    before = migrated._conn.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
    assert migrated.update_status(99999, "applied") is False
    after = migrated._conn.execute("SELECT COUNT(*) FROM application_events").fetchone()[0]
    assert after == before


def test_invalid_status_is_rejected(migrated: JobHistoryDB) -> None:
    app_id = migrated.add_application(company_name="Bad", job_title="Engineer")
    with pytest.raises(ValueError):
        migrated.update_status(app_id, "ghosted")
    with pytest.raises(ValueError):
        migrated.add_event(app_id, "ghosted")


# ---------------------------------------------------------------------------
# 6. Follow-ups, timeline basis, and cascade
# ---------------------------------------------------------------------------


def test_follow_up_flags_only_silent_applications(migrated: JobHistoryDB) -> None:
    old = {"created_at": "2025-12-01T09:00:00"}
    quiet = migrated.add_application(company_name="Quiet", job_title="Engineer", **old)
    migrated.update_status(quiet, "applied", occurred_at="2026-01-01T09:00:00")
    recent = migrated.add_application(company_name="JustApplied", job_title="Engineer")
    migrated.update_status(recent, "applied")           # today -> not yet silent
    moved = migrated.add_application(company_name="Moved", job_title="Engineer", **old)
    migrated.update_status(moved, "applied", occurred_at="2026-01-01T09:00:00")
    migrated.update_status(moved, "interview")          # latest event isn't 'applied'

    flagged = {r["company_name"] for r in migrated.follow_ups(days=21)}
    assert "Quiet" in flagged
    assert "JustApplied" not in flagged
    assert "Moved" not in flagged


def test_follow_up_days_threshold_is_honoured(migrated: JobHistoryDB) -> None:
    app_id = migrated.add_application(
        company_name="Silent", job_title="Engineer", created_at="2025-12-01T09:00:00"
    )
    migrated.update_status(app_id, "applied", occurred_at="2026-01-01T09:00:00")
    assert any(r["id"] == app_id for r in migrated.follow_ups(days=1))
    assert not any(r["id"] == app_id for r in migrated.follow_ups(days=100_000))


# ---------------------------------------------------------------------------
# 7. Backdating guards
# ---------------------------------------------------------------------------


def test_backdate_before_the_application_existed_is_rejected(
    migrated: JobHistoryDB,
) -> None:
    """Left unguarded this corrupts silently rather than loudly: the out-of-order
    event leaves `generated` as the newest entry, so the row vanishes from
    follow-up and response-time instead of reporting something visibly wrong."""
    app_id = migrated.add_application(
        company_name="Anachronism", job_title="Engineer", created_at="2026-05-01T09:00:00"
    )
    with pytest.raises(ValueError, match="before application"):
        migrated.update_status(app_id, "applied", occurred_at="2026-01-01T09:00:00")
    assert migrated.get_application(app_id)["status"] == "generated"
    assert len(migrated.application_events(app_id)) == 1


def test_backdate_in_the_future_is_rejected(migrated: JobHistoryDB) -> None:
    """Catches the mistyped year that would otherwise poison every duration."""
    app_id = migrated.add_application(company_name="Typo", job_title="Engineer")
    with pytest.raises(ValueError, match="in the future"):
        migrated.update_status(app_id, "applied", occurred_at="2062-07-14T09:00:00")


def test_backdate_on_the_creation_moment_is_allowed(migrated: JobHistoryDB) -> None:
    """`add_application` stamps the birth event at exactly `created_at`, so the
    boundary has to be inclusive or every new row would fail its own insert."""
    app_id = migrated.add_application(
        company_name="Boundary", job_title="Engineer", created_at="2026-05-01T09:00:00"
    )
    migrated.update_status(app_id, "applied", occurred_at="2026-05-01T09:00:00")
    assert migrated.get_application(app_id)["status"] == "applied"


def test_timeline_applied_basis_excludes_never_applied(migrated: JobHistoryDB) -> None:
    generated_only = migrated.timeline(group_by="month", basis="generated")
    applied_basis = migrated.timeline(group_by="month", basis="applied")
    assert sum(r["applications"] for r in generated_only) == len(_LEGACY_ROWS)
    # Only the three rows that ever reached 'applied' can be bucketed by it.
    assert sum(r["applications"] for r in applied_basis) == 3


def test_timeline_rejects_unknown_basis(migrated: JobHistoryDB) -> None:
    with pytest.raises(ValueError):
        migrated.timeline(basis="sideways")


def test_deleting_an_application_cascades_to_its_events(migrated: JobHistoryDB) -> None:
    app_id = migrated.add_application(company_name="Doomed", job_title="Engineer")
    migrated.update_status(app_id, "applied")
    migrated._conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    migrated._conn.commit()
    assert migrated.application_events(app_id) == []
