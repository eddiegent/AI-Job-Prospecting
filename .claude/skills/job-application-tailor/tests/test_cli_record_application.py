"""Tests for the ``record-application`` CLI wrapper.

This subcommand collapses the Step 10 inline-Python block (one of the
last DB-touching steps that wasn't a wrapper) into a single deterministic
invocation. The wrapper reads `_prep/job_offer_analysis.json` (offer
flow) or `_prep/selected_role.json` + `_prep/company_profile.json`
(cold flow), composes the `add_application()` kwargs once, and inserts.

These tests pin:

- offer-flow happy path with match_summary fields populated;
- cold-flow happy path (`source='cold'`, snapshot present, fit_* NULL);
- `--url` override when the JSON doesn't carry source_url;
- `--dry-run` prints kwargs without writing;
- missing `_prep/` files surface a clean error and exit 2;
- integer-id resolution against the DB.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.job_history_db import JobHistoryDB

SKILL_ROOT = Path(__file__).resolve().parent.parent
CLI = SKILL_ROOT / "scripts" / "cli.py"


# ---------------------------------------------------------------------------
# Fixtures: build a realistic _prep/ directory for each flow
# ---------------------------------------------------------------------------


def _write_offer_prep(folder: Path, *, source_url: str | None = "https://example.com/job/42") -> None:
    prep = folder / "_prep"
    prep.mkdir(parents=True, exist_ok=True)
    job = {
        "company_name": "Acme SAS",
        "job_title": "Senior .NET Engineer",
        "location": "Paris",
        "domain": "Fintech",
        "seniority": "senior",
        "detected_language": "fr",
        "required_skills": ["C#", ".NET", "Azure"],
        "preferred_skills": ["Docker"],
    }
    if source_url is not None:
        job["source_url"] = source_url
    (prep / "job_offer_analysis.json").write_text(
        json.dumps(job, ensure_ascii=False), encoding="utf-8"
    )
    match = {
        "match_summary": {
            "direct_count": 7,
            "transferable_count": 2,
            "gap_count": 1,
            "overall_fit_pct": 75,
        },
        "matches": [],
    }
    (prep / "match_analysis.json").write_text(
        json.dumps(match, ensure_ascii=False), encoding="utf-8"
    )


def _write_cold_prep(folder: Path) -> None:
    prep = folder / "_prep"
    prep.mkdir(parents=True, exist_ok=True)
    profile = {
        "company_name": "Acme SAS",
        "canonical_url": "https://acme.example",
        "industry": "Robotics",
        "size_band": "scaleup",
        "headcount_estimate": 120,
        "locations": ["Paris, FR", "Lyon, FR"],
        "mission_statement": "Build useful robots.",
        "products_services": ["AGVs"],
        "research_gaps": ["LinkedIn page gated"],
        "sources": [],
        "generated_at": "2026-04-20T10:00:00",
        "input_raw": "acme.example",
    }
    (prep / "company_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False), encoding="utf-8"
    )
    role = {
        "title": "Tech Lead .NET — Desktop & Services",
        "source": "generalist",
        "seniority_band": "lead",
        "generated_at": "2026-04-20T10:05:00",
        "company_name": "Acme SAS",
    }
    (prep / "selected_role.json").write_text(
        json.dumps(role, ensure_ascii=False), encoding="utf-8"
    )


def _run_cli(db_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke cli.py the same way SKILL.md does — as a subprocess. We use
    the real entry point rather than calling cmd_record_application
    directly so the argparse + dispatcher wiring stays under test too."""
    return subprocess.run(
        [sys.executable, str(CLI), "--db", str(db_path), "record-application", *args],
        capture_output=True,
        text=True,
        cwd=str(SKILL_ROOT),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Offer flow
# ---------------------------------------------------------------------------


def test_offer_flow_happy_path(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "good-06052026-senior-net-engineer"
    folder.mkdir()
    _write_offer_prep(folder)

    result = _run_cli(db_path, str(folder))

    assert result.returncode == 0, result.stderr
    assert "Recorded application #1" in result.stdout

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row is not None
        assert row["company_name"] == "Acme SAS"
        assert row["job_title"] == "Senior .NET Engineer"
        assert row["source"] == "offer"
        assert row["source_url"] == "https://example.com/job/42"
        assert row["fit_level"] == "good"
        assert row["fit_pct"] == 75
        assert row["direct_count"] == 7
        assert row["transferable_count"] == 2
        assert row["gap_count"] == 1
        assert row["detected_language"] == "fr"
        assert row["output_folder"] == str(folder)
        skills = db.get_skills(1)
        labels = {(s["skill_type"], s["skill"]) for s in skills}
        assert ("required", "C#") in labels
        assert ("required", ".NET") in labels
        assert ("preferred", "Docker") in labels
    finally:
        db.close()


def test_offer_flow_low_fit_when_no_known_prefix(tmp_path: Path) -> None:
    """A folder without a fit-level prefix (legacy, or pre-Step-4) lands
    as `fit_level='low'` — same fallback the inline block used."""
    db_path = tmp_path / "history.db"
    folder = tmp_path / "06052026-some-role"
    folder.mkdir()
    _write_offer_prep(folder)

    result = _run_cli(db_path, str(folder))
    assert result.returncode == 0, result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row["fit_level"] == "low"
    finally:
        db.close()


def test_url_override_when_offer_json_has_no_source_url(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "good-06052026-some-role"
    folder.mkdir()
    _write_offer_prep(folder, source_url=None)

    result = _run_cli(db_path, str(folder), "--url", "https://forced.example/job")
    assert result.returncode == 0, result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row["source_url"] == "https://forced.example/job"
    finally:
        db.close()


def test_offer_flow_without_match_analysis(tmp_path: Path) -> None:
    """`match_analysis.json` is absent on dry-run / pre-Step-4 folders.
    The wrapper must still record the row — it just leaves the count and
    fit_pct columns NULL."""
    db_path = tmp_path / "history.db"
    folder = tmp_path / "good-06052026-some-role"
    folder.mkdir()
    _write_offer_prep(folder)
    (folder / "_prep" / "match_analysis.json").unlink()

    result = _run_cli(db_path, str(folder))
    assert result.returncode == 0, result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row["fit_pct"] is None
        assert row["direct_count"] is None
        assert row["transferable_count"] is None
        assert row["gap_count"] is None
        # fit_level still derives from the folder prefix.
        assert row["fit_level"] == "good"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Cold flow
# ---------------------------------------------------------------------------


def test_cold_flow_happy_path(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "cold-06052026-acme-sas"
    folder.mkdir()
    _write_cold_prep(folder)

    result = _run_cli(db_path, str(folder))
    assert result.returncode == 0, result.stderr
    assert "Recorded application #1" in result.stdout

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row is not None
        assert row["source"] == "cold"
        assert row["company_name"] == "Acme SAS"
        assert row["job_title"] == "Tech Lead .NET — Desktop & Services"
        assert row["seniority"] == "lead"
        assert row["domain"] == "Robotics"
        assert row["location"] == "Paris, FR"
        assert row["source_url"] == "https://acme.example"
        assert row["detected_language"] == "fr"
        # Cold flow leaves the scoring columns NULL.
        assert row["fit_level"] is None
        assert row["fit_pct"] is None
        assert row["direct_count"] is None
        # Snapshot must round-trip with the curated subset.
        snapshot = json.loads(row["company_profile_snapshot"])
        assert snapshot["company_name"] == "Acme SAS"
        assert snapshot["size_band"] == "scaleup"
        assert snapshot["research_gaps_count"] == 1
        assert snapshot["headcount_estimate"] == 120
        # Cold rows must not populate job_skills.
        assert db.get_skills(1) == []
    finally:
        db.close()


def test_cold_flow_language_override(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "cold-06052026-acme-sas"
    folder.mkdir()
    _write_cold_prep(folder)

    result = _run_cli(db_path, str(folder), "--language", "en")
    assert result.returncode == 0, result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row["detected_language"] == "en"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# --dry-run, --source override, error handling, integer id
# ---------------------------------------------------------------------------


def test_dry_run_prints_kwargs_without_writing(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "good-06052026-some-role"
    folder.mkdir()
    _write_offer_prep(folder)

    result = _run_cli(db_path, str(folder), "--dry-run")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["company_name"] == "Acme SAS"
    assert payload["source"] == "offer"
    assert payload["fit_pct"] == 75

    db = JobHistoryDB(str(db_path))
    try:
        assert db.total_count() == 0
    finally:
        db.close()


def test_source_override_forces_offer_on_cold_prefixed_folder(tmp_path: Path) -> None:
    """Belt-and-braces: a user can force the offer pipeline on a
    cold-prefixed folder if needed (e.g. the folder was renamed without
    the cold prefix being stripped first)."""
    db_path = tmp_path / "history.db"
    folder = tmp_path / "cold-06052026-acme-sas"
    folder.mkdir()
    _write_offer_prep(folder)

    result = _run_cli(db_path, str(folder), "--source", "offer")
    assert result.returncode == 0, result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        row = db.get_application(1)
        assert row["source"] == "offer"
    finally:
        db.close()


def test_missing_prep_artefacts_exits_with_clean_error(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "good-06052026-some-role"
    (folder / "_prep").mkdir(parents=True)
    # No JSON files inside _prep.

    result = _run_cli(db_path, str(folder))
    assert result.returncode == 2
    assert "job_offer_analysis.json" in result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        assert db.total_count() == 0
    finally:
        db.close()


def test_missing_cold_artefacts_exits_with_clean_error(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    folder = tmp_path / "cold-06052026-acme-sas"
    (folder / "_prep").mkdir(parents=True)
    # selected_role.json missing
    (folder / "_prep" / "company_profile.json").write_text(
        json.dumps({"company_name": "X", "canonical_url": ""}), encoding="utf-8"
    )

    result = _run_cli(db_path, str(folder))
    assert result.returncode == 2
    assert "selected_role.json" in result.stderr


def test_integer_id_resolves_via_db(tmp_path: Path) -> None:
    """If the user passes an integer instead of a path, the wrapper
    resolves the folder via `db.get_application(id)`. This is the
    pattern `regenerate-outputs` and `rename-application` already use."""
    db_path = tmp_path / "history.db"
    folder = tmp_path / "good-06052026-resolved-by-id"
    folder.mkdir()
    _write_offer_prep(folder)

    db = JobHistoryDB(str(db_path))
    try:
        seed_id = db.add_application(
            company_name="Seed",
            job_title="Seed Role",
            output_folder=str(folder),
        )
    finally:
        db.close()

    # Passing the integer id must record a *second* row using the seed
    # row's output_folder (the wrapper writes a new application — the
    # subcommand is record, not update).
    result = _run_cli(db_path, str(seed_id))
    assert result.returncode == 0, result.stderr

    db = JobHistoryDB(str(db_path))
    try:
        assert db.total_count() == 2
        latest = db.get_application(seed_id + 1)
        assert latest["company_name"] == "Acme SAS"
        assert latest["output_folder"] == str(folder)
    finally:
        db.close()


def test_unknown_integer_id_exits_with_error(tmp_path: Path) -> None:
    db_path = tmp_path / "history.db"
    JobHistoryDB(str(db_path)).close()

    result = _run_cli(db_path, "999")
    assert result.returncode == 1
    assert "999" in result.stderr
