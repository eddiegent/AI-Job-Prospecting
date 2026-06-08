"""Integration test: generate_outputs.py renders the interview prep and the
cold-flow company dossier to responsive HTML deliverables.

Runs the script as a subprocess with minimal schema-valid fixtures and
``--skip-pdf`` so it needs neither Microsoft Word nor a network."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_BASE = Path(__file__).resolve().parents[1]
GENERATE = SKILL_BASE / "scripts" / "generate_outputs.py"
SETTINGS = SKILL_BASE / "config" / "settings.default.yaml"
NAMING = SKILL_BASE / "config" / "naming_rules.yaml"


def _write_fixtures(prep: Path) -> None:
    prep.mkdir(parents=True, exist_ok=True)
    (prep / "tailored_cv.json").write_text(
        json.dumps(
            {
                "candidate_name": "Test User",
                "title": "Developer",
                "experience": [
                    {
                        "role_line": "Developer",
                        "metadata_line": "Acme | Paris | January 2020 - Present",
                        "bullets": ["Built things"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (prep / "letter.json").write_text(
        json.dumps(
            {
                "greeting": "Bonjour,",
                "paragraphs": ["Un paragraphe."],
                "signoff": "Cordialement,",
                "name": "Test User",
            }
        ),
        encoding="utf-8",
    )
    (prep / "interview_prep.md").write_text(
        "# Prep\n\n## Section\n\n| A | B |\n|---|---|\n| 1 | 2 |\n",
        encoding="utf-8",
    )
    (prep / "company_dossier.md").write_text(
        "# Dossier\n\n## Angle\n\n- premier point\n- https://example.com/team\n",
        encoding="utf-8",
    )


def _run(out_dir: Path, prep: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONUTF8": "1"}
    cmd = [
        sys.executable,
        str(GENERATE),
        "--tailored-cv-json", str(prep / "tailored_cv.json"),
        "--letter-json", str(prep / "letter.json"),
        "--interview-markdown", str(prep / "interview_prep.md"),
        "--dossier-markdown", str(prep / "company_dossier.md"),
        "--output-dir", str(out_dir),
        "--job-title", "Test Role",
        "--settings", str(SETTINGS),
        "--naming-rules", str(NAMING),
        "--language", "fr",
        "--skip-pdf",
    ]
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_interview_and_dossier_render_to_html(tmp_path: Path) -> None:
    out_dir = tmp_path / "cold-08062026-acme"
    prep = out_dir / "_prep"
    _write_fixtures(prep)

    result = _run(out_dir, prep)
    assert result.returncode == 0, result.stderr

    # Interview prep deliverable is HTML, not Markdown.
    interview = out_dir / "Interview_prep_Test_User_Test_Role.html"
    assert interview.exists()
    assert not (out_dir / "Interview_prep_Test_User_Test_Role.md").exists()
    interview_html = interview.read_text(encoding="utf-8")
    assert interview_html.startswith("<!DOCTYPE html>")
    assert '<meta name="viewport"' in interview_html
    assert "<table>" in interview_html  # the pipe table converted

    # Cold dossier deliverable is HTML at a fixed filename; Markdown source stays in _prep.
    dossier = out_dir / "company_dossier.html"
    assert dossier.exists()
    dossier_html = dossier.read_text(encoding="utf-8")
    assert dossier_html.startswith("<!DOCTYPE html>")
    assert "<h1>Dossier</h1>" in dossier_html
    assert '<a href="https://example.com/team">' in dossier_html  # bare URL autolinked
    assert (prep / "company_dossier.md").exists()  # source preserved

    summary = json.loads((out_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["interview_file"].endswith(".html")
    assert summary["dossier_file"].endswith("company_dossier.html")


def test_dossier_omitted_when_flag_absent(tmp_path: Path) -> None:
    out_dir = tmp_path / "medium-08062026-acme"
    prep = out_dir / "_prep"
    _write_fixtures(prep)

    env = {**os.environ, "PYTHONUTF8": "1"}
    cmd = [
        sys.executable,
        str(GENERATE),
        "--tailored-cv-json", str(prep / "tailored_cv.json"),
        "--letter-json", str(prep / "letter.json"),
        "--interview-markdown", str(prep / "interview_prep.md"),
        "--output-dir", str(out_dir),
        "--job-title", "Test Role",
        "--settings", str(SETTINGS),
        "--naming-rules", str(NAMING),
        "--language", "fr",
        "--skip-pdf",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr
    assert not (out_dir / "company_dossier.html").exists()
    summary = json.loads((out_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["dossier_file"] is None
