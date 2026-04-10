"""Phase 4 regression tests for scripts/init.py — first-run onboarding.

These tests pin the invariants that make ``init`` safe to re-run. The
init script must:

1. Create the resolved user data dir (and its ``output/`` subfolder) if
   missing.
2. Copy the sample CV as ``MASTER_CV.example.docx`` — **never** as
   ``MASTER_CV.docx``, so a user who runs init after saving their real CV
   cannot accidentally overwrite it with the fictional sample.
3. Copy both user customization templates (``cv_addendum.template.md``
   and ``user_prefs.template.yaml``) into the data dir.
4. Be idempotent: a second run makes no changes (SHA-256 compare).
5. Leave an existing ``MASTER_CV.docx`` untouched.

The sample/template sources live under ``samples/`` in the skill install.
``init_user_data`` accepts ``samples_dir`` as a kwarg so tests can exercise
it with synthetic inputs without depending on the real sample CV existing
yet (that's Task #2). Production callers pass nothing and the function
derives ``samples_dir`` from ``SKILL_ROOT``.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts import init as init_mod


# ----- helpers ----------------------------------------------------------

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_samples(tmp_path: Path) -> Path:
    """Create a fake ``samples/`` dir with the three source files.

    Uses synthetic bytes — the tests assert identity after copy, not
    content semantics, so real docx/markdown/yaml is unnecessary here.
    """
    samples = tmp_path / "samples"
    samples.mkdir()
    (samples / "MASTER_CV.example.docx").write_bytes(b"fake-docx-bytes\x00\x01\x02")
    (samples / "cv_addendum.template.md").write_text(
        "# CV Addendum Template\n", encoding="utf-8"
    )
    (samples / "user_prefs.template.yaml").write_text(
        "# user prefs template\n", encoding="utf-8"
    )
    return samples


def _hashes(dir_path: Path) -> dict[str, str]:
    return {
        p.relative_to(dir_path).as_posix(): _sha256(p)
        for p in dir_path.rglob("*")
        if p.is_file()
    }


# ----- directory creation -----------------------------------------------

def test_init_creates_user_data_dir_if_missing(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"
    assert not target.exists()

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)

    assert target.is_dir()
    assert (target / "output").is_dir()


# ----- non-destructive copy of master CV --------------------------------

def test_init_does_not_overwrite_existing_master_cv(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"
    target.mkdir()
    real_cv = target / "MASTER_CV.docx"
    real_bytes = b"the-real-user-cv-bytes"
    real_cv.write_bytes(real_bytes)
    original_hash = _sha256(real_cv)

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)

    assert real_cv.read_bytes() == real_bytes
    assert _sha256(real_cv) == original_hash


def test_init_copies_sample_cv_as_example_not_master(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)

    assert (target / "MASTER_CV.example.docx").exists()
    # Critical: init must NOT create MASTER_CV.docx — only the user does.
    assert not (target / "MASTER_CV.docx").exists()


# ----- templates --------------------------------------------------------

def test_init_writes_both_templates(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)

    assert (target / "cv_addendum.template.md").exists()
    assert (target / "user_prefs.template.yaml").exists()


def test_init_does_not_overwrite_existing_customization_files(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"
    target.mkdir()
    user_addendum = target / "cv_addendum.md"
    user_addendum.write_text("user's real addendum", encoding="utf-8")
    user_prefs = target / "user_prefs.yaml"
    user_prefs.write_text("user's real prefs", encoding="utf-8")

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)

    assert user_addendum.read_text(encoding="utf-8") == "user's real addendum"
    assert user_prefs.read_text(encoding="utf-8") == "user's real prefs"


# ----- idempotency ------------------------------------------------------

def test_init_is_idempotent(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)
    first = _hashes(target)

    init_mod.init_user_data(user_data_dir=target, samples_dir=samples)
    second = _hashes(target)

    assert first == second


# ----- reporting --------------------------------------------------------

def test_init_returns_report_listing_created_and_skipped(tmp_path):
    samples = _make_samples(tmp_path)
    target = tmp_path / "user_data"

    report = init_mod.init_user_data(user_data_dir=target, samples_dir=samples)

    assert "created" in report and "skipped" in report
    created_names = {Path(p).name for p in report["created"]}
    assert "MASTER_CV.example.docx" in created_names
    assert "cv_addendum.template.md" in created_names
    assert "user_prefs.template.yaml" in created_names

    # Second run: everything is skipped.
    report2 = init_mod.init_user_data(user_data_dir=target, samples_dir=samples)
    assert report2["created"] == []
    assert len(report2["skipped"]) >= 3


# ----- sample CV extraction (integration, enabled once task #2 lands) ---

def test_sample_cv_extracts_cleanly():
    """The real sample CV must parse through python-docx without error.

    This is a lightweight structural check, not a full extractor run: it
    asserts the file exists, opens as a valid docx, and contains the
    section-header styles the extractor keys on. A full Step-2 extraction
    requires a model call and lives outside pytest.
    """
    from scripts.paths import SKILL_ROOT

    sample = SKILL_ROOT / "samples" / "MASTER_CV.example.docx"
    if not sample.exists():
        pytest.skip("Sample CV not built yet (Task #2)")

    from docx import Document

    doc = Document(str(sample))
    style_names = {p.style.name for p in doc.paragraphs if p.style}
    # Styles created by scripts/create_cv_template.py — the same ones the
    # tailored-CV renderer uses. The sample must exercise them so the
    # extractor's style-based heuristics still match.
    assert "NameStyle" in style_names
    assert "SectionStyle" in style_names
    assert "RoleStyle" in style_names
    assert "BulletStyle" in style_names
