"""First-run onboarding smoke: `python -m scripts.preflight` against a fresh,
empty user-data dir must return status=first_run and seed the templates.

Regression pin: preflight's first-run branch used a function-level bare
`from init import ...` that only resolved when the scripts dir itself was on
sys.path — running via `-m scripts.preflight` (exactly what job-prep-cv
SKILL.md documents) crashed with ModuleNotFoundError on a fresh install. The
module-level imports were converted to the scripts.X form in the package-
layout refactor, but function-level ones were missed, and no test exercised
this path.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]


def _run_preflight(home: Path) -> dict:
    env = dict(os.environ, JOB_TAILOR_HOME=str(home), PYTHONUTF8="1")
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.preflight",
         "--flow", "offer", "--input", "Smoke Test Offer"],
        capture_output=True, text=True, encoding="utf-8",
        cwd=str(SKILL_ROOT), env=env,
    )
    assert proc.stdout.strip(), proc.stderr
    return json.loads(proc.stdout)


def test_first_run_seeds_templates_and_stops(tmp_path):
    home = tmp_path / "fresh-home"
    result = _run_preflight(home)

    assert result["status"] == "first_run", result
    assert result.get("next_steps"), "first_run must tell the user what to do next"

    # init.py must have seeded the onboarding files without inventing a CV
    assert (home / "MASTER_CV.example.docx").exists() or any(
        home.glob("*.docx")
    ), f"example CV not seeded; home contains {sorted(p.name for p in home.iterdir())}"
    assert (home / "cv_addendum.template.md").exists()
    assert (home / "user_prefs.template.yaml").exists()
    assert not (home / "MASTER_CV.docx").exists(), (
        "first run must NOT fabricate a real MASTER_CV.docx"
    )


def test_project_root_plugin_install_falls_back_to_user_data_dir(tmp_path, monkeypatch):
    """Regression pin: on an installed plugin (no .git/.claude between the
    skill base and the home dir), the walk must NOT match ~/.claude — that is
    Claude Code's global config, not a project — and packs must land under
    the user-data dir instead of ~/output."""
    from scripts import preflight

    home = tmp_path / "userhome"
    (home / ".claude").mkdir(parents=True)  # the global config decoy
    skill_base = home / "AppData" / "plugins" / "job-prospecting" / "skills" / "tailor"
    skill_base.mkdir(parents=True)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("JOB_TAILOR_HOME", str(data_dir))
    monkeypatch.setattr(preflight, "_git_toplevel", lambda: None)

    resolved = preflight._resolve_project_root(skill_base=skill_base, home=home)
    assert resolved == data_dir


def test_project_root_repo_layout_still_walks_to_repo(tmp_path, monkeypatch):
    from scripts import preflight

    home = tmp_path / "userhome"
    repo = home / "projects" / "my-repo"
    skill_base = repo / ".claude" / "skills" / "job-application-tailor"
    skill_base.mkdir(parents=True)
    (repo / ".git").mkdir()
    monkeypatch.setattr(preflight, "_git_toplevel", lambda: None)

    resolved = preflight._resolve_project_root(skill_base=skill_base, home=home)
    assert resolved == repo


def test_first_run_is_idempotent(tmp_path):
    home = tmp_path / "fresh-home"
    first = _run_preflight(home)
    second = _run_preflight(home)
    assert first["status"] == "first_run"
    assert second["status"] == "first_run", (
        "a second run before the user adds a CV must remain first_run, "
        f"got {second['status']}"
    )
