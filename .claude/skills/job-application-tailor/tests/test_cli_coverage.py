"""Coverage for previously untested CLI surfaces: check-duplicate (the dedup
gate), export-csv, the company-list commands, backfill_history (the documented
disaster-recovery path), and the two doc-drift guards.
"""
from __future__ import annotations

import json
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.backfill_history import backfill
from scripts.commands.companies import (
    cmd_company_add,
    cmd_company_check,
    cmd_company_list,
    cmd_company_remove,
)
from scripts.commands.records import cmd_check_duplicate
from scripts.commands.reporting import cmd_export_csv
from scripts.job_history_db import JobHistoryDB

SKILL_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def db(tmp_path):
    db = JobHistoryDB(str(tmp_path / "hist.db"))
    yield db
    db.close()


def _offer_prep(tmp_path, *, company="Acme", title="Dev C#", url="https://x.example/1",
                skills=("c#", ".net")) -> Path:
    folder = tmp_path / "14072026-run"
    prep = folder / "_prep"
    prep.mkdir(parents=True)
    (prep / "job_offer_analysis.json").write_text(json.dumps({
        "company_name": company, "job_title": title, "source_url": url,
        "required_skills": list(skills), "detected_language": "fr",
    }), encoding="utf-8")
    return folder


def _add_app(db, *, company="Acme", title="Dev C#", url="https://x.example/1"):
    db.add_application(
        company_name=company, job_title=title, source_url=url,
        fit_pct=80.0, fit_level="good", direct_count=1, transferable_count=0,
        gap_count=0, required_skills=["c#"], output_folder="/tmp/x",
        detected_language="fr",
    )


# ------------------------------------------------------------ check-duplicate

def test_check_duplicate_clean_exits_0(db, tmp_path):
    folder = _offer_prep(tmp_path)
    with pytest.raises(SystemExit) as e:
        cmd_check_duplicate(db, Namespace(target=str(folder), url=None, json=False))
    assert e.value.code == 0


def test_check_duplicate_same_url_flags(db, tmp_path, capsys):
    _add_app(db, url="https://x.example/1")
    folder = _offer_prep(tmp_path, url="https://x.example/1")
    with pytest.raises(SystemExit) as e:
        cmd_check_duplicate(db, Namespace(target=str(folder), url=None, json=False))
    assert e.value.code == 1
    assert "Acme" in capsys.readouterr().out


def test_check_duplicate_blacklist_flags(db, tmp_path, capsys):
    cmd_company_add(db, Namespace(name="Evil Corp", list_type="blacklist", reason="ghosted"))
    capsys.readouterr()
    folder = _offer_prep(tmp_path, company="Evil Corp", url="https://y.example/2")
    with pytest.raises(SystemExit) as e:
        cmd_check_duplicate(db, Namespace(target=str(folder), url=None, json=False))
    assert e.value.code == 1
    out = capsys.readouterr().out
    assert "BLACKLIST" in out.upper()


def test_check_duplicate_bad_target_exits_2(db, tmp_path):
    with pytest.raises(SystemExit) as e:
        cmd_check_duplicate(db, Namespace(target=str(tmp_path / "nope"), url=None, json=False))
    assert e.value.code == 2


def test_check_duplicate_json_payload(db, tmp_path, capsys):
    _add_app(db, url="https://x.example/1")
    folder = _offer_prep(tmp_path, url="https://x.example/1")
    with pytest.raises(SystemExit):
        cmd_check_duplicate(db, Namespace(target=str(folder), url=None, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert {"blacklist", "duplicates", "same_company_context"} <= set(payload)
    assert payload["duplicates"], "URL duplicate must appear in the JSON payload"


# ---------------------------------------------------------------- export-csv

def test_export_csv_to_file(db, tmp_path):
    _add_app(db, company="Café & Co", title="Développeur")
    out = tmp_path / "export.csv"
    cmd_export_csv(db, Namespace(output=str(out)))
    text = out.read_text(encoding="utf-8")
    assert "Café & Co" in text
    assert "Développeur" in text


def test_export_csv_to_stdout(db, capsys):
    _add_app(db)
    cmd_export_csv(db, Namespace(output=None))
    assert "Acme" in capsys.readouterr().out


# ------------------------------------------------------------- company lists

def test_company_list_roundtrip(db, capsys):
    cmd_company_add(db, Namespace(name="Evil Corp", list_type="blacklist", reason="ghosted"))
    cmd_company_add(db, Namespace(name="Nice Corp", list_type="whitelist", reason=None))
    capsys.readouterr()

    cmd_company_check(db, Namespace(name="Evil Corp"))
    assert "blacklist" in capsys.readouterr().out

    cmd_company_list(db, Namespace(type="all"))
    out = capsys.readouterr().out
    assert "Evil Corp" in out and "Nice Corp" in out and "ghosted" in out

    cmd_company_remove(db, Namespace(name="Evil Corp"))
    capsys.readouterr()
    cmd_company_check(db, Namespace(name="Evil Corp"))
    assert "not on any list" in capsys.readouterr().out


def test_company_remove_unknown_exits_1(db):
    with pytest.raises(SystemExit) as e:
        cmd_company_remove(db, Namespace(name="Ghost Inc"))
    assert e.value.code == 1


# ------------------------------------------------------------------ backfill

def _run_folder(output_dir: Path, name: str, *, company: str, title: str,
                fit_pct: int = 75) -> Path:
    folder = output_dir / name
    prep = folder / "_prep"
    prep.mkdir(parents=True)
    (prep / "job_offer_analysis.json").write_text(json.dumps({
        "company_name": company, "job_title": title,
        "required_skills": ["c#"], "detected_language": "fr",
    }), encoding="utf-8")
    (prep / "match_analysis.json").write_text(json.dumps({
        "match_summary": {"overall_fit_pct": fit_pct, "direct_count": 2,
                          "transferable_count": 1, "gap_count": 1},
    }), encoding="utf-8")
    return folder


def test_backfill_imports_and_is_idempotent(db, tmp_path):
    output = tmp_path / "output"
    _run_folder(output, "good-23032026-Dev-Acme", company="Acme", title="Dev")
    _run_folder(output, "medium-24032026-Dev-Beta", company="Beta", title="Dev")
    (output / "not-a-run").mkdir()  # no _prep -> skipped

    result = backfill(output, db)
    assert sorted(result["imported"]) == ["good-23032026-Dev-Acme", "medium-24032026-Dev-Beta"]
    assert any("not-a-run" in s for s in result["skipped"])
    assert db.total_count() == 2

    # Second pass must not duplicate anything
    again = backfill(output, db)
    assert again["imported"] == []
    assert db.total_count() == 2


def test_backfill_derives_fit_and_date(db, tmp_path):
    output = tmp_path / "output"
    _run_folder(output, "good-23032026-Dev-Acme", company="Acme", title="Dev", fit_pct=82)
    backfill(output, db)
    rows = db.list_applications(limit=10)
    assert rows[0]["fit_level"] == "good"
    assert rows[0]["fit_pct"] == 82
    assert rows[0]["created_at"].startswith("2026-03-23")


# ------------------------------------------------------------- drift guards

def test_gen_cli_reference_check_is_in_sync():
    proc = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "gen_cli_reference.py"), "--check"],
        capture_output=True, text=True, cwd=str(SKILL_ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_gen_cli_reference_render_covers_registry():
    from scripts.commands import _ORDER
    from scripts.gen_cli_reference import render
    content = render()
    for name in _ORDER:
        assert f"### `{name}`" in content, name


def test_lint_cli_usage_flags_unknown_flag(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_text(
        "```bash\npython scripts/cli.py list --bogus-flag\n```\n", encoding="utf-8"
    )
    proc = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "lint_cli_usage.py"), str(bad)],
        capture_output=True, text=True, cwd=str(SKILL_ROOT),
    )
    assert proc.returncode == 1
    assert "bogus" in (proc.stdout + proc.stderr)


def test_lint_cli_usage_passes_valid_invocation(tmp_path):
    good = tmp_path / "good.md"
    good.write_text(
        "```bash\npython scripts/cli.py list --status applied --limit 10\n```\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [sys.executable, str(SKILL_ROOT / "scripts" / "lint_cli_usage.py"), str(good)],
        capture_output=True, text=True, cwd=str(SKILL_ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
