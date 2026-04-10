"""Phase 5 tests for scripts/package.py and .claude-plugin/plugin.json.

The packaging pipeline is the last line of defence before a plugin ships.
If it leaks user data, a user on a fresh machine inherits Eddie's job
history; if it drops the sample CV, the onboarding flow breaks; if the
plugin manifest is malformed, the install command fails with a parse
error. Each of those is a release blocker, so they get pinned here.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.package import (
    PACKAGE_EXCLUDE_DIR_NAMES,
    build_plugin_tree,
    package_plugin,
)


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
SKILLS = ("job-application-tailor", "job-stats", "job-status")


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def test_plugin_manifest_is_valid_json() -> None:
    assert PLUGIN_MANIFEST.exists(), (
        f"plugin manifest not found at {PLUGIN_MANIFEST}"
    )
    data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("name"), "plugin manifest must declare a name"
    assert data.get("version"), "plugin manifest must declare a version"
    assert data.get("description"), "plugin manifest must declare a description"


# ---------------------------------------------------------------------------
# Fixtures — synthetic project root so tests never depend on Eddie's data.
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_project(tmp_path: Path) -> Path:
    """Build a minimal repo layout the packager can operate on.

    We replicate the shape of the real repo: ``.claude/skills/<name>/``
    trees with a SKILL.md and a few decoy files the packager must exclude,
    plus top-level user data directories that must not leak into the
    archive.
    """
    project = tmp_path / "fake_repo"

    # Plugin manifest
    (project / ".claude-plugin").mkdir(parents=True)
    (project / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({
            "name": "job-prospecting",
            "version": "0.0.0-test",
            "description": "test manifest",
        }),
        encoding="utf-8",
    )

    # Three skills with a mix of kept and excluded content
    for skill in SKILLS:
        base = project / ".claude" / "skills" / skill
        (base / "scripts").mkdir(parents=True)
        (base / "prompts").mkdir()
        (base / "tests").mkdir()
        (base / "__pycache__").mkdir()
        (base / "SKILL.md").write_text("# " + skill, encoding="utf-8")
        (base / "scripts" / "thing.py").write_text("x = 1\n", encoding="utf-8")
        (base / "scripts" / "thing.pyc").write_bytes(b"\x00")
        (base / "prompts" / "p.md").write_text("prompt", encoding="utf-8")
        (base / "tests" / "test_nope.py").write_text(
            "assert False\n", encoding="utf-8"
        )
        (base / "__pycache__" / "thing.cpython-311.pyc").write_bytes(b"\x00")

    # Sample CV that must be included
    samples = project / ".claude" / "skills" / "job-application-tailor" / "samples"
    samples.mkdir()
    (samples / "MASTER_CV.example.docx").write_bytes(b"DOCX")

    # User data at the skill level that must be excluded
    resources = (
        project / ".claude" / "skills" / "job-application-tailor" / "resources"
    )
    resources.mkdir()
    (resources / "MASTER_CV.docx").write_bytes(b"REAL-CV-SECRET")
    (resources / "job_history.db").write_bytes(b"SQLITE")
    (resources / "cv_fact_base.json").write_text("{}", encoding="utf-8")

    # Top-level user data that must be excluded
    (project / "resources").mkdir()
    (project / "resources" / "MASTER_CV.docx").write_bytes(b"REAL-CV-SECRET")
    (project / "output").mkdir()
    (project / "output" / "very_good-2026-01-01-foo").mkdir()
    (project / "output" / "very_good-2026-01-01-foo" / "cv.docx").write_bytes(
        b"USER-OUTPUT"
    )
    (project / "backups").mkdir()
    (project / "backups" / "pre-plugin-migration-2026-04-10-1553").mkdir()
    (project / "backups" / "pre-plugin-migration-2026-04-10-1553" / "x.txt").write_text(
        "backup", encoding="utf-8"
    )

    return project


# ---------------------------------------------------------------------------
# build_plugin_tree
# ---------------------------------------------------------------------------

def test_build_plugin_tree_copies_manifest_and_skills(fake_project: Path) -> None:
    target = fake_project.parent / "dist" / "job-prospecting"
    build_plugin_tree(fake_project, target, SKILLS)

    assert (target / ".claude-plugin" / "plugin.json").exists()
    for skill in SKILLS:
        assert (target / "skills" / skill / "SKILL.md").exists(), skill


def test_build_plugin_tree_uses_top_level_skills_dir(fake_project: Path) -> None:
    """Plugin layout requires ``skills/<name>/``, not ``.claude/skills/<name>/``.

    This is the key structural transformation the packager performs and
    the reason a plain ``cp -r`` won't work.
    """
    target = fake_project.parent / "dist" / "job-prospecting"
    build_plugin_tree(fake_project, target, SKILLS)

    assert (target / "skills").is_dir()
    assert not (target / ".claude" / "skills").exists()


def test_build_plugin_tree_excludes_user_data(fake_project: Path) -> None:
    target = fake_project.parent / "dist" / "job-prospecting"
    build_plugin_tree(fake_project, target, SKILLS)

    leaked: list[Path] = []
    for path in target.rglob("*"):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        if b"REAL-CV-SECRET" in blob or b"USER-OUTPUT" in blob or b"SQLITE" in blob:
            leaked.append(path)
    assert leaked == [], f"user data leaked into plugin tree: {leaked}"

    # And the specific directories are absent
    for skill in SKILLS:
        skill_root = target / "skills" / skill
        assert not (skill_root / "resources").exists()
        assert not (skill_root / "output").exists()


def test_build_plugin_tree_excludes_backups(fake_project: Path) -> None:
    target = fake_project.parent / "dist" / "job-prospecting"
    build_plugin_tree(fake_project, target, SKILLS)

    # Packager operates on the skills directory; backups/ is top-level
    # and has no path into the dist tree. This test asserts nothing in
    # the dist tree resembles a backup folder.
    hits = list(target.rglob("pre-plugin-migration-*"))
    assert hits == []


def test_build_plugin_tree_excludes_tests_and_pycache(fake_project: Path) -> None:
    target = fake_project.parent / "dist" / "job-prospecting"
    build_plugin_tree(fake_project, target, SKILLS)

    for excluded in PACKAGE_EXCLUDE_DIR_NAMES:
        hits = list(target.rglob(excluded))
        assert hits == [], f"{excluded} leaked: {hits}"

    # And no .pyc files
    assert list(target.rglob("*.pyc")) == []


def test_build_plugin_tree_includes_sample_cv(fake_project: Path) -> None:
    target = fake_project.parent / "dist" / "job-prospecting"
    build_plugin_tree(fake_project, target, SKILLS)

    sample = (
        target
        / "skills"
        / "job-application-tailor"
        / "samples"
        / "MASTER_CV.example.docx"
    )
    assert sample.exists(), "sample CV must ship with the plugin"
    assert sample.read_bytes() == b"DOCX"


def test_build_plugin_tree_refuses_existing_target(fake_project: Path) -> None:
    target = fake_project.parent / "dist" / "job-prospecting"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("leftover", encoding="utf-8")

    with pytest.raises(FileExistsError):
        build_plugin_tree(fake_project, target, SKILLS)


# ---------------------------------------------------------------------------
# package_plugin (tree + zip)
# ---------------------------------------------------------------------------

def test_package_plugin_produces_archive(fake_project: Path) -> None:
    dist = fake_project.parent / "dist"
    archive = package_plugin(fake_project, dist, SKILLS)

    assert archive.exists()
    assert archive.suffix == ".zip"
    assert zipfile.is_zipfile(archive)


def test_package_plugin_archive_excludes_user_data(fake_project: Path) -> None:
    dist = fake_project.parent / "dist"
    archive = package_plugin(fake_project, dist, SKILLS)

    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            with zf.open(info) as fh:
                blob = fh.read()
            assert b"REAL-CV-SECRET" not in blob, info.filename
            assert b"USER-OUTPUT" not in blob, info.filename
            assert b"SQLITE" not in blob, info.filename

        names = zf.namelist()

    # Specific paths that must not appear
    forbidden = (
        "resources/MASTER_CV.docx",
        "resources/job_history.db",
        "resources/cv_fact_base.json",
        "output/",
        "backups/",
    )
    for needle in forbidden:
        assert not any(needle in n for n in names), needle


def test_package_plugin_archive_includes_sample_cv(fake_project: Path) -> None:
    dist = fake_project.parent / "dist"
    archive = package_plugin(fake_project, dist, SKILLS)

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()

    assert any(
        n.endswith("skills/job-application-tailor/samples/MASTER_CV.example.docx")
        for n in names
    ), names


def test_package_plugin_archive_includes_manifest(fake_project: Path) -> None:
    dist = fake_project.parent / "dist"
    archive = package_plugin(fake_project, dist, SKILLS)

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()

    assert any(n.endswith(".claude-plugin/plugin.json") for n in names), names


# ---------------------------------------------------------------------------
# Top-level gate — intentionally skipped.
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "Top-level CI gate: running pytest from the repo root must pass all "
        "phase tests before packaging is allowed. Implementing this inside "
        "pytest is circular (the test that asserts pytest passes would itself "
        "need pytest to have passed). The roadmap's intent is covered by the "
        "package script refusing to run when any phase test fails; that gate "
        "lives in scripts/package.py::main, not here. See Decision log "
        "2026-04-10 for rationale."
    )
)
def test_all_phase_tests_pass_in_ci() -> None:
    pass
