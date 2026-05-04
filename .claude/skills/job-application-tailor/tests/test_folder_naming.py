"""Tests for the deferred-slug folder naming.

Background: the offer flow used to create the output folder eagerly with
a placeholder slug derived from the user's input (often a URL like
``linkedin-4402235727``), then rename it twice — first to add the fit
prefix at Step 4, and again later via ``rename-application`` if the
slug needed fixing. D2 collapses this into a single rename: at Step 4,
``rename_folder_with_fit`` rebuilds the slug from ``job_title`` +
``company`` so the final folder ends up at
``[fit_level]-[date]-[job_title-company]/`` in one shot.
"""
from __future__ import annotations

from pathlib import Path

from scripts.common import auto_slug, rename_folder_with_fit


def test_auto_slug_with_title_and_company() -> None:
    assert auto_slug("Senior Developer", "Acme Corp") == "Senior-Developer-Acme-Corp"


def test_auto_slug_company_only() -> None:
    assert auto_slug(None, "Acme Corp") == "Acme-Corp"
    assert auto_slug("", "Acme Corp") == "Acme-Corp"


def test_auto_slug_title_only() -> None:
    assert auto_slug("Senior Developer", None) == "Senior-Developer"


def test_auto_slug_both_empty_returns_untitled() -> None:
    assert auto_slug(None, None) == "untitled"
    assert auto_slug("", "") == "untitled"


def test_auto_slug_collapses_runs_of_dashes() -> None:
    # Multiple internal whitespace and special chars collapse to single dashes
    out = auto_slug("Dev   //  C#", "Big   Co")
    assert "--" not in out
    assert out.startswith("Dev-")


def test_rename_with_fit_only_preserves_existing_slug(tmp_path: Path) -> None:
    """Backward-compatible path: no job_title/company supplied means the
    existing slug stays put. This is the cold flow's contract."""
    folder = tmp_path / "04052026-cold-acme"
    folder.mkdir()
    new = rename_folder_with_fit(folder, 73)
    assert new.name == "good-04052026-cold-acme"
    assert new.exists()


def test_rename_with_fit_and_real_slug_in_one_shot(tmp_path: Path) -> None:
    """The new contract: pass job_title + company at fit-rename time and
    the placeholder slug from folder creation gets replaced in one go."""
    # Folder was created at preflight with a URL-ish placeholder
    folder = tmp_path / "04052026-linkedin-4402235727"
    folder.mkdir()
    new = rename_folder_with_fit(
        folder,
        65,
        job_title="Développeur Senior .Net FW et Core",
        company="INGELINE TECHNOLOGIES",
    )
    # Fit prefix + date + recomputed slug, all in one rename
    assert new.name.startswith("medium-04052026-")
    assert "linkedin-4402235727" not in new.name
    assert "INGELINE-TECHNOLOGIES" in new.name
    assert new.exists()


def test_rename_does_not_double_prefix(tmp_path: Path) -> None:
    """If the folder already has a fit prefix (because Step 4 ran before
    and is being re-run), don't end up with `medium-medium-`."""
    folder = tmp_path / "good-04052026-acme"
    folder.mkdir()
    new = rename_folder_with_fit(folder, 65)
    assert new.name == "medium-04052026-acme"
    assert "medium-medium" not in new.name


def test_rename_with_company_only_when_title_missing(tmp_path: Path) -> None:
    """Edge case: the offer analysis somehow lacks a job_title. Slug
    should still rebuild from the company alone, not stay on placeholder."""
    folder = tmp_path / "04052026-tmp-slug"
    folder.mkdir()
    new = rename_folder_with_fit(folder, 60, job_title=None, company="Acme")
    assert new.name == "medium-04052026-Acme"
