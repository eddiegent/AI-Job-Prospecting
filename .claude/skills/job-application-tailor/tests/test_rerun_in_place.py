"""Rerunning a pack in place: `record-application --update` and
`preflight --reuse-dir`.

Background: a "rerun" of an existing pack (full pipeline, same folder, same
history row) had no support. `record-application` always inserted, so after a
rerun the original row kept its old fit score (apps #166/#167 said 66%/68%
while their packs said 63%/66%), and preflight always created a new folder.

These tests pin:

- `--update` rewrites the pack-derived columns and the skills, and leaves the
  id, status, source, created_at and the status history alone — no new row;
- it refuses an unknown id, a different company, a different flow, a stale
  fit prefix (the row's fit_level comes from the folder name), and
  `--supersede` alongside it;
- `--dry-run` with `--update` previews without writing;
- a `--url` recorded on the first run survives a rerun whose _prep has none;
- `preflight --reuse-dir` points output_dir/prep_dir at the existing pack,
  creates nothing new, refreshes the fact base from a valid cache, and on a
  stale cache moves the pack's old fact base aside (never re-blessed).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.job_history_db import JobHistoryDB

SKILL_ROOT = Path(__file__).resolve().parent.parent
CLI = SKILL_ROOT / "scripts" / "cli.py"


def _env(home: Path) -> dict:
    # Point user data (settings, CV) at a temp dir so no test reads or writes
    # the real resources/.
    return dict(os.environ, JOB_TAILOR_HOME=str(home), PYTHONUTF8="1")


def _run_cli(tmp_path: Path, db_path: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), "--db", str(db_path), *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(SKILL_ROOT), env=_env(tmp_path / "home"),
    )


def _write_offer_prep(folder: Path, *, company: str = "Acme SAS", fit_pct: int = 66,
                      skills: tuple[str, ...] = ("C#", ".NET"), source_url: str | None = None,
                      title: str = "Senior .NET Engineer") -> None:
    prep = folder / "_prep"
    prep.mkdir(parents=True, exist_ok=True)
    job = {
        "company_name": company, "job_title": title, "location": "Paris",
        "domain": "Fintech", "seniority": "senior", "detected_language": "fr",
        "required_skills": list(skills), "preferred_skills": ["Docker"],
    }
    if source_url:
        job["source_url"] = source_url
    (prep / "job_offer_analysis.json").write_text(json.dumps(job), encoding="utf-8")
    (prep / "match_analysis.json").write_text(json.dumps({
        "match_summary": {"overall_fit_pct": fit_pct, "direct_count": 5,
                          "transferable_count": 3, "gap_count": 2},
        "matches": [],
    }), encoding="utf-8")


def _seed_row(db_path: Path, folder: Path, *, status: str = "applied") -> int:
    """A row as the first run recorded it: 68% / good, with --url, then applied."""
    db = JobHistoryDB(str(db_path))
    try:
        app_id = db.add_application(
            company_name="Acme SAS", job_title="Senior .NET Engineer",
            source_url="https://jobs.example/42", fit_level="good", fit_pct=68,
            direct_count=7, transferable_count=1, gap_count=1,
            output_folder=str(folder), detected_language="fr",
            required_skills=["C#", "Azure"], created_at="2026-11-01T10:00:00",
        )
        if status != "generated":
            db.update_status(app_id, status, occurred_at="2026-11-02T09:00:00", note="sent")
        return app_id
    finally:
        db.close()


def _snapshot(db_path: Path, app_id: int) -> tuple[dict, list, list, int]:
    db = JobHistoryDB(str(db_path))
    try:
        return (db.get_application(app_id), db.application_events(app_id),
                sorted((s["skill_type"], s["skill"]) for s in db.get_skills(app_id)),
                db.total_count())
    finally:
        db.close()


# ---------------------------------------------------------------------------
# record-application --update
# ---------------------------------------------------------------------------


def test_update_refreshes_derived_columns_and_keeps_identity(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    old_folder = tmp_path / "good-01112026-Senior-NET-Engineer-Acme-SAS"
    app_id = _seed_row(db_path, old_folder)
    before, events_before, _, _ = _snapshot(db_path, app_id)

    # The rerun scored 66% (below the 70% 'good' line), so rename-with-fit
    # moved the pack to a medium- folder.
    new_folder = tmp_path / "medium-01112026-Senior-NET-Engineer-Acme-SAS"
    _write_offer_prep(new_folder, fit_pct=66, skills=("C#", ".NET", "WPF"))

    result = _run_cli(tmp_path, db_path, "record-application", str(new_folder),
                      "--update", str(app_id))
    assert result.returncode == 0, result.stderr
    assert "Recorded application" not in result.stdout

    row, events, skills, count = _snapshot(db_path, app_id)
    assert count == 1, "an update must not insert a second row"
    assert row["fit_pct"] == 66 and row["fit_level"] == "medium"
    assert (row["direct_count"], row["transferable_count"], row["gap_count"]) == (5, 3, 2)
    assert row["output_folder"] == str(new_folder)
    assert row["domain"] == "Fintech"
    # identity + history untouched
    for col in ("id", "status", "source", "created_at"):
        assert row[col] == before[col], col
    assert row["status"] == "applied"
    assert events == events_before
    # skills replaced, not appended
    assert ("required", "Azure") not in skills
    assert {("required", "C#"), ("required", ".NET"), ("required", "WPF"),
            ("preferred", "Docker")} == set(skills)
    # the --url recorded on the first run survives a _prep without one
    assert row["source_url"] == "https://jobs.example/42"


def test_update_dry_run_writes_nothing(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    folder = tmp_path / "medium-01112026-x"
    app_id = _seed_row(db_path, folder)
    before = _snapshot(db_path, app_id)
    _write_offer_prep(folder, fit_pct=60)

    result = _run_cli(tmp_path, db_path, "record-application", str(folder),
                      "--update", str(app_id), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "Would update" in result.stdout
    assert "fit_pct: 68.0 -> 60" in result.stdout
    assert _snapshot(db_path, app_id) == before


def test_update_unknown_id_exits_1(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    folder = tmp_path / "medium-01112026-x"
    _seed_row(db_path, folder)
    _write_offer_prep(folder, fit_pct=60)
    result = _run_cli(tmp_path, db_path, "record-application", str(folder), "--update", "999")
    assert result.returncode == 1
    assert "not found" in result.stderr


def test_update_refuses_other_company(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    folder = tmp_path / "medium-01112026-x"
    app_id = _seed_row(db_path, folder)
    before = _snapshot(db_path, app_id)
    _write_offer_prep(folder, company="Globex", fit_pct=60)
    result = _run_cli(tmp_path, db_path, "record-application", str(folder),
                      "--update", str(app_id))
    assert result.returncode == 2
    assert "Refusing" in result.stderr and "Globex" in result.stderr
    assert _snapshot(db_path, app_id) == before


def test_update_refuses_stale_fit_prefix(tmp_path: Path) -> None:
    """The row's fit_level is read from the folder prefix, so a folder still
    named good-… after a rerun that scored 'medium' would record the wrong
    level. Refuse and point at rename-with-fit."""
    db_path = tmp_path / "h.db"
    folder = tmp_path / "good-01112026-x"
    app_id = _seed_row(db_path, folder)
    _write_offer_prep(folder, fit_pct=63)
    result = _run_cli(tmp_path, db_path, "record-application", str(folder),
                      "--update", str(app_id))
    assert result.returncode == 2
    assert "rename-with-fit" in result.stderr


def test_update_refuses_supersede_combo(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    folder = tmp_path / "medium-01112026-x"
    app_id = _seed_row(db_path, folder)
    _write_offer_prep(folder, fit_pct=60)
    result = _run_cli(tmp_path, db_path, "record-application", str(folder),
                      "--update", str(app_id), "--supersede")
    assert result.returncode == 2


def test_update_refuses_cold_pack_on_offer_row(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    app_id = _seed_row(db_path, tmp_path / "good-01112026-x")
    cold = tmp_path / "cold-01112026-acme-sas"
    prep = cold / "_prep"
    prep.mkdir(parents=True)
    (prep / "company_profile.json").write_text(json.dumps(
        {"company_name": "Acme SAS", "canonical_url": "https://acme.example",
         "industry": "Robotics", "org_type": "end_employer", "locations": ["Paris"]}),
        encoding="utf-8")
    (prep / "selected_role.json").write_text(json.dumps(
        {"title": "Tech Lead .NET", "seniority_band": "lead", "language": "fr"}),
        encoding="utf-8")
    result = _run_cli(tmp_path, db_path, "record-application", str(cold), "--update", str(app_id))
    assert result.returncode == 2
    assert "cold pack" in result.stderr


def test_update_cold_row(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    cold = tmp_path / "cold-01112026-acme-sas"
    prep = cold / "_prep"
    prep.mkdir(parents=True)
    profile = {"company_name": "Acme SAS", "canonical_url": "https://acme.example",
               "industry": "Robotics", "org_type": "end_employer", "locations": ["Paris"]}
    (prep / "company_profile.json").write_text(json.dumps(profile), encoding="utf-8")
    (prep / "selected_role.json").write_text(json.dumps(
        {"title": "Tech Lead .NET", "seniority_band": "lead", "language": "fr"}),
        encoding="utf-8")
    first = _run_cli(tmp_path, db_path, "record-application", str(cold))
    assert first.returncode == 0, first.stderr

    # Rerun: the role pick and the industry changed.
    (prep / "selected_role.json").write_text(json.dumps(
        {"title": "Senior .NET Desktop Engineer", "seniority_band": "senior", "language": "en"}),
        encoding="utf-8")
    profile["industry"] = "Industrial robotics"
    (prep / "company_profile.json").write_text(json.dumps(profile), encoding="utf-8")
    result = _run_cli(tmp_path, db_path, "record-application", str(cold), "--update", "1")
    assert result.returncode == 0, result.stderr

    row, events, _, count = _snapshot(db_path, 1)
    assert count == 1
    assert row["source"] == "cold"
    assert row["job_title"] == "Senior .NET Desktop Engineer"
    assert row["domain"] == "Industrial robotics"
    assert row["detected_language"] == "en"
    assert row["fit_pct"] is None
    assert [e["status"] for e in events] == ["generated"]


def test_update_resolves_folder_by_id(tmp_path: Path) -> None:
    """`record-application <id> --update <id>` reads the pack the row points at."""
    db_path = tmp_path / "h.db"
    folder = tmp_path / "medium-01112026-x"
    app_id = _seed_row(db_path, folder)
    _write_offer_prep(folder, fit_pct=55)
    result = _run_cli(tmp_path, db_path, "record-application", str(app_id),
                      "--update", str(app_id))
    assert result.returncode == 0, result.stderr
    assert _snapshot(db_path, app_id)[0]["fit_pct"] == 55


def test_plain_record_still_inserts(tmp_path: Path) -> None:
    db_path = tmp_path / "h.db"
    folder = tmp_path / "medium-01112026-x"
    _seed_row(db_path, folder)
    _write_offer_prep(folder, fit_pct=60)
    result = _run_cli(tmp_path, db_path, "record-application", str(folder))
    assert result.returncode == 0, result.stderr
    assert "Recorded application #2" in result.stdout


# ---------------------------------------------------------------------------
# preflight --reuse-dir
# ---------------------------------------------------------------------------


def _make_home(tmp_path: Path, *, with_cache: bool) -> Path:
    from docx import Document

    from scripts.common import file_hash

    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    cv = home / "MASTER_CV.docx"
    doc = Document()
    doc.add_paragraph("Jane Doe — Software Engineer")
    doc.add_paragraph("C# .NET developer, 10 years.")
    doc.save(str(cv))
    if with_cache:
        (home / "cv_fact_base.json").write_text(
            json.dumps({"marker": "from-cache"}), encoding="utf-8")
        (home / ".cv_hash").write_text(file_hash(cv), encoding="utf-8")
    return home


def _run_preflight(home: Path, *args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.preflight", *args],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(SKILL_ROOT), env=dict(os.environ, JOB_TAILOR_HOME=str(home), PYTHONUTF8="1"),
    )
    assert proc.stdout.strip(), proc.stderr
    return proc.returncode, json.loads(proc.stdout.strip().splitlines()[-1])


def _pack(tmp_path: Path, name: str = "medium-01112026-Dev-Acme") -> Path:
    pack = tmp_path / "output" / name
    (pack / "_prep").mkdir(parents=True)
    (pack / "_prep" / "raw_offer.md").write_text("offer text", encoding="utf-8")
    (pack / "_prep" / "cv_fact_base.json").write_text(
        json.dumps({"marker": "old-run"}), encoding="utf-8")
    return pack


def test_reuse_dir_stale_cache_sets_old_fact_base_aside(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_cache=False)
    pack = _pack(tmp_path)
    siblings_before = sorted(p.name for p in pack.parent.iterdir())

    code, state = _run_preflight(home, "--flow", "offer", "--reuse-dir", str(pack))

    assert code == 0, state
    assert state["status"] == "cache_stale"
    assert state["reused"] is True
    assert Path(state["output_dir"]) == pack
    assert Path(state["prep_dir"]) == pack / "_prep"
    # nothing new created next to the pack
    assert sorted(p.name for p in pack.parent.iterdir()) == siblings_before
    # the previous run's fact base can't be mistaken for a current one
    assert not (pack / "_prep" / "cv_fact_base.json").exists()
    prev = pack / "_prep" / "cv_fact_base.prev.json"
    assert json.loads(prev.read_text(encoding="utf-8")) == {"marker": "old-run"}
    assert state["previous_fact_base"] == str(prev)
    # the reused inputs stay
    assert (pack / "_prep" / "raw_offer.md").exists()


def test_reuse_dir_valid_cache_refreshes_fact_base(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_cache=True)
    pack = _pack(tmp_path)

    code, state = _run_preflight(home, "--flow", "offer", "--reuse-dir", str(pack))

    assert code == 0, state
    assert Path(state["output_dir"]) == pack
    # copied from the cache over the old run's file (verification outcome is
    # the existing cache-hit logic, not under test here)
    fb = json.loads((pack / "_prep" / "cv_fact_base.json").read_text(encoding="utf-8"))
    assert fb == {"marker": "from-cache"}
    assert "previous_fact_base" not in state


@pytest.mark.parametrize("flow,name,expect", [
    ("offer", "cold-01112026-acme", "--flow cold"),
    ("cold", "medium-01112026-Dev-Acme", "--flow offer"),
])
def test_reuse_dir_refuses_flow_mismatch(tmp_path: Path, flow, name, expect) -> None:
    home = _make_home(tmp_path, with_cache=False)
    pack = _pack(tmp_path, name)
    code, state = _run_preflight(home, "--flow", flow, "--reuse-dir", str(pack))
    assert code == 1
    assert state["status"] == "error" and expect in state["message"]
    # refused before touching the fact base
    assert (pack / "_prep" / "cv_fact_base.json").exists()


def test_reuse_dir_refuses_missing_or_non_pack(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_cache=False)
    code, state = _run_preflight(home, "--flow", "offer", "--reuse-dir", str(tmp_path / "nope"))
    assert code == 1 and "does not exist" in state["message"]

    bare = tmp_path / "output" / "medium-01112026-bare"
    bare.mkdir(parents=True)
    code, state = _run_preflight(home, "--flow", "offer", "--reuse-dir", str(bare))
    assert code == 1 and "_prep" in state["message"]


def test_preflight_requires_input_or_reuse_dir(tmp_path: Path) -> None:
    home = _make_home(tmp_path, with_cache=False)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.preflight", "--flow", "offer"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(SKILL_ROOT), env=dict(os.environ, JOB_TAILOR_HOME=str(home)),
    )
    assert proc.returncode == 2
    assert "--reuse-dir" in proc.stderr
