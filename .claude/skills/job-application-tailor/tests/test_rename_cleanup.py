"""Tests for the rename-application stale-slug cleanup helper.

Background: ``rename-application`` renames a folder, then runs
``regenerate-outputs``. The regenerate step writes new-slug filenames but
leaves the old-slug files in place, so the folder ends up with two copies
of every deliverable. ``delete_stale_slug_deliverables`` removes the
pre-rename files before the regenerate fires.
"""
from __future__ import annotations

from pathlib import Path

from scripts.common import delete_stale_slug_deliverables


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_removes_old_slug_deliverables_at_root(tmp_path: Path) -> None:
    old = "linkedin-4402235727"
    new = "Developpeur-Senior-NET-INGELINE"
    for ext in ("docx", "pdf", "txt", "md"):
        _touch(tmp_path / f"CV_Edward_Gent_{old}.{ext}")
        _touch(tmp_path / f"CV_Edward_Gent_{new}.{ext}")
    _touch(tmp_path / "run_summary.json")
    _touch(tmp_path / "_prep" / "cv_fact_base.json")

    removed = delete_stale_slug_deliverables(tmp_path, old, new)

    assert sorted(removed) == sorted(
        [f"CV_Edward_Gent_{old}.{ext}" for ext in ("docx", "md", "pdf", "txt")]
    )
    # New-slug files survive
    for ext in ("docx", "pdf", "txt", "md"):
        assert (tmp_path / f"CV_Edward_Gent_{new}.{ext}").exists()
    # Non-deliverable files survive
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "_prep" / "cv_fact_base.json").exists()


def test_does_not_descend_into_prep(tmp_path: Path) -> None:
    """_prep/ contents must not be touched even if a file there happens to
    match the slug pattern (defensive — the helper uses non-recursive glob)."""
    old = "abc"
    _touch(tmp_path / "_prep" / f"trick_{old}.json")
    _touch(tmp_path / f"CV_X_{old}.docx")

    removed = delete_stale_slug_deliverables(tmp_path, old, "xyz")

    assert removed == [f"CV_X_{old}.docx"]
    assert (tmp_path / "_prep" / f"trick_{old}.json").exists()


def test_noop_when_slug_unchanged(tmp_path: Path) -> None:
    _touch(tmp_path / "CV_X_same.docx")
    removed = delete_stale_slug_deliverables(tmp_path, "same", "same")
    assert removed == []
    assert (tmp_path / "CV_X_same.docx").exists()


def test_noop_when_old_slug_missing(tmp_path: Path) -> None:
    _touch(tmp_path / "CV_X_anything.docx")
    removed = delete_stale_slug_deliverables(tmp_path, "", "new")
    assert removed == []
    assert (tmp_path / "CV_X_anything.docx").exists()


def test_handles_special_chars_in_slug(tmp_path: Path) -> None:
    """Slugs can include dots and hash characters (e.g. ``C#``, ``.Net``)."""
    old = "Developpeur-Senior-.Net-FW-et-Core-C#-et-SQL-INGELINE"
    new = "different-slug"
    _touch(tmp_path / f"CV_Edward_Gent_{old}.docx")
    _touch(tmp_path / f"Lettre_courte_Edward_Gent_{old}.txt")
    _touch(tmp_path / f"CV_Edward_Gent_{new}.docx")

    removed = delete_stale_slug_deliverables(tmp_path, old, new)

    assert sorted(removed) == sorted(
        [f"CV_Edward_Gent_{old}.docx", f"Lettre_courte_Edward_Gent_{old}.txt"]
    )
    assert (tmp_path / f"CV_Edward_Gent_{new}.docx").exists()
