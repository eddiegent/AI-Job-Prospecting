"""Tests for the ``dropped`` application status.

A ``dropped`` application is one the user has explicitly decided not to
pursue. Two behaviours are pinned here:

1. ``update_status`` accepts ``'dropped'`` (and still rejects garbage).
2. Dropped rows are excluded from *all three* duplicate checks in
   ``find_duplicates`` — exact URL, company+title, and company+skill
   overlap — so walking away from a role never blocks or warns on a
   fresh application to the same target. A live row to the same target
   must still be detected (the filter only removes dropped rows).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.job_history_db import JobHistoryDB


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


def test_update_status_accepts_dropped(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(company_name="Acme", job_title="Engineer")
        assert db.update_status(app_id, "dropped") is True
        row = db.get_application(app_id)
        assert row is not None
        assert row["status"] == "dropped"
    finally:
        db.close()


def test_update_status_still_rejects_unknown(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(company_name="Acme", job_title="Engineer")
        with pytest.raises(ValueError, match="Invalid status"):
            db.update_status(app_id, "abandoned")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# find_duplicates — dropped rows are excluded from every check
# ---------------------------------------------------------------------------


def test_dropped_excluded_from_url_match(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        url = "https://jobs.example.com/acme/eng/42"
        app_id = db.add_application(
            company_name="Acme", job_title="Engineer", source_url=url
        )

        # While live, the URL is a duplicate hit.
        assert db.find_duplicates(
            company_name="Different Co", job_title="Different Title", source_url=url
        ), "live row should match on exact URL"

        # Once dropped, the same URL no longer matches.
        db.update_status(app_id, "dropped")
        assert (
            db.find_duplicates(
                company_name="Different Co",
                job_title="Different Title",
                source_url=url,
            )
            == []
        )
    finally:
        db.close()


def test_dropped_excluded_from_company_title_match(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        app_id = db.add_application(company_name="Acme", job_title="Backend Engineer")

        assert db.find_duplicates(
            company_name="Acme", job_title="Backend Engineer"
        ), "live row should match on company + title"

        db.update_status(app_id, "dropped")
        assert (
            db.find_duplicates(company_name="Acme", job_title="Backend Engineer") == []
        )
    finally:
        db.close()


def test_dropped_excluded_from_skill_overlap_match(tmp_path: Path) -> None:
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        skills = ["C#", ".NET", "Azure"]
        app_id = db.add_application(
            company_name="Acme",
            job_title="Backend Engineer",
            required_skills=skills,
        )

        # A different title at the same company falls through to the
        # skill-overlap check (100% overlap >= 0.80 threshold).
        assert db.find_duplicates(
            company_name="Acme",
            job_title="Platform Engineer",
            required_skills=skills,
        ), "live row should match on company + skill overlap"

        db.update_status(app_id, "dropped")
        assert (
            db.find_duplicates(
                company_name="Acme",
                job_title="Platform Engineer",
                required_skills=skills,
            )
            == []
        )
    finally:
        db.close()


def test_live_row_still_detected_alongside_dropped_one(tmp_path: Path) -> None:
    """A dropped row to a company must not suppress detection of a separate
    *live* row to the same company + title."""
    db = JobHistoryDB(str(tmp_path / "history.db"))
    try:
        dropped_id = db.add_application(
            company_name="Acme", job_title="Backend Engineer"
        )
        db.update_status(dropped_id, "dropped")
        live_id = db.add_application(company_name="Acme", job_title="Backend Engineer")

        matches = db.find_duplicates(
            company_name="Acme", job_title="Backend Engineer"
        )
        ids = {m["id"] for m in matches}
        assert live_id in ids
        assert dropped_id not in ids
    finally:
        db.close()
