"""Tests for the pipeline-support subcommands (scripts/commands/pipeline.py)
and the timeline report. These commands replaced the inline `python -c` blobs
the docs used to carry, so each one is pinned here.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.error
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.commands.pipeline import (
    cmd_cache_raw_offer,
    cmd_check_forbidden_labels,
    cmd_detect_platform,
    cmd_probe_url,
    cmd_rename_cold_folder,
    cmd_rename_with_fit,
    cmd_save_cv_cache,
)
from scripts.commands.reporting import cmd_timeline
from scripts.job_history_db import JobHistoryDB


def _write_prep(folder: Path, name: str, payload: dict) -> None:
    prep = folder / "_prep"
    prep.mkdir(parents=True, exist_ok=True)
    (prep / name).write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------- probe-url

def test_probe_url_ok(monkeypatch, capsys):
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: object())
    cmd_probe_url(None, Namespace(url="https://example.com/job"))
    assert capsys.readouterr().out.strip() == "OK"


def test_probe_url_blocked(monkeypatch, capsys):
    def raise_403(req, timeout):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", raise_403)
    cmd_probe_url(None, Namespace(url="https://blocked.example"))
    assert capsys.readouterr().out.strip() == "BLOCKED 403"


def test_probe_url_other_error(monkeypatch, capsys):
    def raise_oserror(req, timeout):
        raise OSError("dns fail")
    monkeypatch.setattr("urllib.request.urlopen", raise_oserror)
    cmd_probe_url(None, Namespace(url="https://nowhere.example"))
    assert capsys.readouterr().out.startswith("OTHER_ERROR OSError")


# ----------------------------------------------------------- cache-raw-offer

def test_cache_raw_offer_writes_stdin(tmp_path, monkeypatch, capsys):
    run = tmp_path / "14072026-acme"
    (run / "_prep").mkdir(parents=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO("OFFER TEXT — développeur"))
    cmd_cache_raw_offer(None, Namespace(target=str(run)))
    assert (run / "_prep" / "raw_offer.md").read_text(encoding="utf-8") == "OFFER TEXT — développeur"
    assert "Cached raw offer" in capsys.readouterr().out


def test_cache_raw_offer_rejects_empty_stdin(tmp_path, monkeypatch):
    run = tmp_path / "14072026-acme"
    (run / "_prep").mkdir(parents=True)
    monkeypatch.setattr(sys, "stdin", io.StringIO("   \n"))
    with pytest.raises(SystemExit) as e:
        cmd_cache_raw_offer(None, Namespace(target=str(run)))
    assert e.value.code == 2


def test_cache_raw_offer_missing_prep_exits_2(tmp_path):
    with pytest.raises(SystemExit) as e:
        cmd_cache_raw_offer(None, Namespace(target=str(tmp_path / "nope")))
    assert e.value.code == 2


# ----------------------------------------------------------- detect-platform

def test_detect_platform_hits_known_aggregator(tmp_path, capsys):
    run = tmp_path / "14072026-x"
    _write_prep(run, "job_offer_analysis.json", {"company_name": "Free-Work"})
    cmd_detect_platform(None, Namespace(target=str(run)))
    assert capsys.readouterr().out.strip().lower() == "free-work"


def test_detect_platform_empty_for_direct_employer(tmp_path, capsys):
    run = tmp_path / "14072026-x"
    _write_prep(run, "job_offer_analysis.json", {"company_name": "Acme Robotics"})
    cmd_detect_platform(None, Namespace(target=str(run)))
    assert capsys.readouterr().out.strip() == ""


# ------------------------------------------------------------ rename-with-fit

def test_rename_with_fit_renames_and_prints(tmp_path, capsys):
    run = tmp_path / "14072026-placeholder-slug"
    _write_prep(run, "match_analysis.json", {"match_summary": {"overall_fit_pct": 75}})
    _write_prep(run, "job_offer_analysis.json",
                {"job_title": "Senior Dev", "company_name": "Acme"})
    cmd_rename_with_fit(None, Namespace(target=str(run)))
    new_path = Path(capsys.readouterr().out.strip())
    assert new_path.exists()
    assert new_path.name.startswith("good-14072026-")
    assert "Acme" in new_path.name


def test_rename_with_fit_missing_summary_exits_2(tmp_path):
    run = tmp_path / "14072026-x"
    _write_prep(run, "match_analysis.json", {"matches": []})
    _write_prep(run, "job_offer_analysis.json", {"job_title": "X"})
    with pytest.raises(SystemExit) as e:
        cmd_rename_with_fit(None, Namespace(target=str(run)))
    assert e.value.code == 2


# --------------------------------------------------------- rename-cold-folder

def test_rename_cold_folder_canonicalises(tmp_path, capsys):
    run = tmp_path / "cold-14072026-https-linkedin-acme"
    _write_prep(run, "company_profile.json", {"company_name": "Acme Robotics SAS"})
    cmd_rename_cold_folder(None, Namespace(target=str(run)))
    new_path = Path(capsys.readouterr().out.strip())
    assert new_path.exists()
    assert new_path.name.startswith("cold-14072026-")
    assert "Acme" in new_path.name


def test_rename_cold_folder_existing_target_exits_1(tmp_path):
    run = tmp_path / "cold-14072026-placeholder"
    _write_prep(run, "company_profile.json", {"company_name": "Acme"})
    # Pre-create the canonical target so the rename collides
    from scripts.common import rename_cold_folder_with_canonical_name  # noqa: PLC0415
    probe = tmp_path / "cold-14072026-probe"
    (probe / "_prep").mkdir(parents=True)
    target_name = rename_cold_folder_with_canonical_name(probe, "Acme").name
    if target_name != run.name:  # only meaningful when a real collision exists
        with pytest.raises(SystemExit) as e:
            cmd_rename_cold_folder(None, Namespace(target=str(run)))
        assert e.value.code == 1


# ----------------------------------------------------- check-forbidden-labels

@pytest.fixture
def prefs_home(tmp_path, monkeypatch):
    home = tmp_path / "userdata"
    home.mkdir()
    (home / "user_prefs.yaml").write_text(
        'forbidden_title_labels:\n  - "Backend"\n', encoding="utf-8"
    )
    monkeypatch.setenv("JOB_TAILOR_HOME", str(home))
    return home


def test_forbidden_labels_flags_candidates(tmp_path, prefs_home, capsys):
    f = tmp_path / "role_candidates.json"
    f.write_text(json.dumps({"candidates": [
        {"title": "Senior Backend Engineer"},
        {"title": "Desktop & Services Lead"},
    ]}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cmd_check_forbidden_labels(None, Namespace(json_file=str(f)))
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "candidates[0]" in out and "Backend" in out
    assert "candidates[1]" not in out


def test_forbidden_labels_clean_selected_role(tmp_path, prefs_home, capsys):
    f = tmp_path / "selected_role.json"
    f.write_text(json.dumps({"title": "Senior .NET — Desktop & Services"}), encoding="utf-8")
    cmd_check_forbidden_labels(None, Namespace(json_file=str(f)))
    assert "OK" in capsys.readouterr().out


def test_forbidden_labels_flags_tailored_cv_title(tmp_path, prefs_home):
    f = tmp_path / "tailored_cv.json"
    f.write_text(json.dumps({"title": "Backend Developer", "experience": []}),
                 encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        cmd_check_forbidden_labels(None, Namespace(json_file=str(f)))
    assert e.value.code == 1


# --------------------------------------------------------------- save-cv-cache

def test_save_cv_cache_missing_cv_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_TAILOR_HOME", str(tmp_path / "empty"))
    run = tmp_path / "14072026-x"
    (run / "_prep").mkdir(parents=True)
    with pytest.raises(SystemExit) as e:
        cmd_save_cv_cache(None, Namespace(target=str(run), cv=None))
    assert e.value.code == 2


# -------------------------------------------------------------------- timeline

def _seed_db(tmp_path) -> JobHistoryDB:
    db = JobHistoryDB(str(tmp_path / "hist.db"))
    common = dict(fit_pct=80.0, fit_level="good", direct_count=1,
                  transferable_count=0, gap_count=0, required_skills=["c#"],
                  output_folder="/tmp/x", detected_language="fr")
    db.add_application(company_name="A", job_title="Dev",
                       created_at="2026-06-03T10:00:00", **common)
    db.add_application(company_name="B", job_title="Dev",
                       created_at="2026-07-01T10:00:00", **common)
    db.add_application(company_name="C", job_title="Dev",
                       created_at="2026-07-02T10:00:00", **common)
    return db


def test_timeline_groups_by_month(tmp_path):
    db = _seed_db(tmp_path)
    try:
        rows = db.timeline(group_by="month")
    finally:
        db.close()
    assert [r["period"] for r in rows] == ["2026-07", "2026-06"]
    assert rows[0]["applications"] == 2
    assert rows[1]["applications"] == 1
    assert rows[0]["avg_fit_pct"] == 80.0


def test_timeline_rejects_bad_group_by(tmp_path):
    db = _seed_db(tmp_path)
    try:
        with pytest.raises(ValueError):
            db.timeline(group_by="fortnight")
    finally:
        db.close()


def test_timeline_command_renders_table(tmp_path, capsys):
    db = _seed_db(tmp_path)
    try:
        cmd_timeline(db, Namespace(group_by="month", since=None, source=None,
                                   org_type=None, json=False))
    finally:
        db.close()
    out = capsys.readouterr().out
    assert "2026-07" in out and "2026-06" in out


def test_timeline_command_json(tmp_path, capsys):
    db = _seed_db(tmp_path)
    try:
        cmd_timeline(db, Namespace(group_by="week", since=None, source=None,
                                   org_type=None, json=True))
    finally:
        db.close()
    payload = json.loads(capsys.readouterr().out)
    assert payload["group_by"] == "week"
    assert sum(p["applications"] for p in payload["periods"]) == 3
