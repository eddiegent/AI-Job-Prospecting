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

import pytest

from scripts.common import (
    auto_slug,
    rename_cold_folder_with_canonical_name,
    rename_folder_with_fit,
)


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


# --- Cold-flow rename ---------------------------------------------------


def test_cold_rename_replaces_url_placeholder_with_canonical_name(tmp_path: Path) -> None:
    """The motivating case: preflight created the folder from a LinkedIn
    URL, so the slug is unreadable. Step 3 hands us the canonical company
    name from research, and the rename swaps the slug in one shot."""
    folder = tmp_path / "cold-14052026-https-wwwlinkedincom-company-francebillet"
    folder.mkdir()
    new = rename_cold_folder_with_canonical_name(folder, "France Billet")
    assert new.name == "cold-14052026-France-Billet"
    assert new.exists()
    assert not folder.exists()


def test_cold_rename_is_idempotent_when_slug_already_canonical(tmp_path: Path) -> None:
    """Re-running Step 3 (or running it after a manual rename) must be a
    no-op — no rename, no error, returns the same path back."""
    folder = tmp_path / "cold-14052026-France-Billet"
    folder.mkdir()
    new = rename_cold_folder_with_canonical_name(folder, "France Billet")
    assert new == folder
    assert new.exists()


def test_cold_rename_refuses_to_overwrite_existing_folder(tmp_path: Path) -> None:
    """Collision guard: if the target folder already exists (left over
    from a previous run), the rename must fail loudly rather than wipe
    the existing pack. The caller surfaces the error to the user."""
    src = tmp_path / "cold-14052026-https-wwwlinkedincom-company-francebillet"
    src.mkdir()
    dst = tmp_path / "cold-14052026-France-Billet"
    dst.mkdir()
    with pytest.raises(FileExistsError):
        rename_cold_folder_with_canonical_name(src, "France Billet")
    assert src.exists()
    assert dst.exists()


def test_cold_rename_only_acts_on_cold_prefixed_folders(tmp_path: Path) -> None:
    """Defensive: passing an offer-flow folder (no ``cold-`` prefix)
    leaves it untouched. The helper recognises only the cold shape."""
    folder = tmp_path / "14052026-some-slug"
    folder.mkdir()
    new = rename_cold_folder_with_canonical_name(folder, "France Billet")
    assert new == folder
    assert new.exists()
