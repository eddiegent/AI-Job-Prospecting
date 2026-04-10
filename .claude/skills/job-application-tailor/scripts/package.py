"""Phase 5: build a distributable Claude Code plugin bundle.

This is the last step before v1.0.0 ships. It transforms the repo's
dev-time layout (``.claude/skills/<name>/`` for in-place `/slash` use)
into the plugin-install layout (``skills/<name>/`` under a plugin root
with ``.claude-plugin/plugin.json``), then zips it.

The hard rule: **user data must never leak into the bundle.** The repo
contains a real master CV, a real SQLite history DB, and ~30 generated
application packs. Any of them would be a privacy disaster if shipped.
Exclusions are enforced by name at copy time and verified by the
Phase 5 test suite.

Layout transformation:

    <repo>/
    ├── .claude-plugin/plugin.json
    └── .claude/skills/<name>/...

    becomes

    <dist>/job-prospecting/
    ├── .claude-plugin/plugin.json
    └── skills/<name>/...

Usage:
    python -m scripts.package <project-root> [<dist-root>]

``dist-root`` defaults to ``<project-root>/dist``. The script refuses
to overwrite an existing bundle directory — delete it yourself first.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Iterable


PLUGIN_NAME = "job-prospecting"
DEFAULT_SKILLS = ("job-application-tailor", "job-stats", "job-status")

# Directories that must never appear anywhere under a packaged skill.
# Matched by basename at every depth.
PACKAGE_EXCLUDE_DIR_NAMES = frozenset({
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "tests",
    "resources",        # user data: master CV, fact base, history DB
    "output",           # user data: generated application packs
    "backups",          # Phase 0 backup folders
    "job-application-tailor-workspace",  # transient scratch dir
})

# Individual file basenames that must never be bundled.
PACKAGE_EXCLUDE_FILE_NAMES = frozenset({
    ".cv_hash",
    "cv_fact_base.json",
    "cv_addendum.md",          # user's personal addendum (the template.md ships)
    "user_prefs.yaml",         # user's personal prefs (the template.yaml ships)
    "settings.yaml",           # user's settings override (settings.default.yaml ships)
    "job_history.db",
    "MASTER_CV.docx",          # the user's real CV (MASTER_CV.example.docx ships)
})

PACKAGE_EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".sqlite", ".sqlite3", ".db")


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def _should_skip(path: Path) -> bool:
    name = path.name
    if path.is_dir() and name in PACKAGE_EXCLUDE_DIR_NAMES:
        return True
    if path.is_file() and name in PACKAGE_EXCLUDE_FILE_NAMES:
        return True
    if path.is_file() and path.suffix.lower() in PACKAGE_EXCLUDE_SUFFIXES:
        return True
    return False


def _copy_skill(src: Path, dst: Path) -> None:
    """Copy one skill tree, excluding everything in the blocklists."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in sorted(src.iterdir()):
        if _should_skip(entry):
            continue
        target = dst / entry.name
        if entry.is_dir():
            _copy_skill(entry, target)
        else:
            shutil.copy2(entry, target)


def build_plugin_tree(
    project_root: Path,
    target: Path,
    skills: Iterable[str] = DEFAULT_SKILLS,
) -> Path:
    """Materialise the plugin layout at ``target``.

    Returns ``target``. Raises ``FileExistsError`` if ``target`` already
    exists — the caller must clean up first so a stale bundle never
    silently shadows a fresh build.
    """
    project_root = project_root.resolve()
    target = target.resolve()

    if target.exists():
        raise FileExistsError(
            f"plugin tree target already exists: {target}. "
            "Remove it first or pass a different path."
        )

    manifest_src = project_root / ".claude-plugin" / "plugin.json"
    if not manifest_src.exists():
        raise FileNotFoundError(
            f"plugin manifest not found at {manifest_src}. "
            "Phase 5 requires .claude-plugin/plugin.json at the repo root."
        )

    target.mkdir(parents=True)

    # Manifest
    manifest_dst = target / ".claude-plugin"
    manifest_dst.mkdir()
    shutil.copy2(manifest_src, manifest_dst / "plugin.json")

    # Skills — transform .claude/skills/<name>/ → skills/<name>/
    for skill in skills:
        src = project_root / ".claude" / "skills" / skill
        if not src.exists():
            raise FileNotFoundError(f"skill source not found: {src}")
        _copy_skill(src, target / "skills" / skill)

    return target


def _make_archive(tree_root: Path, archive_path: Path) -> Path:
    """Zip ``tree_root`` under its own basename so the zip extracts cleanly.

    Files inside the archive are prefixed with ``tree_root.name/`` so an
    unzip produces ``job-prospecting/.claude-plugin/...`` rather than
    dumping files into the current directory.
    """
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as zf:
        for path in sorted(tree_root.rglob("*")):
            if path.is_dir():
                continue
            arcname = Path(tree_root.name) / path.relative_to(tree_root)
            zf.write(path, arcname.as_posix())
    return archive_path


def package_plugin(
    project_root: Path,
    dist_root: Path,
    skills: Iterable[str] = DEFAULT_SKILLS,
) -> Path:
    """Build the plugin tree and zip it.

    Returns the path to the produced ``.zip`` archive. A stale bundle
    directory from a prior run is removed automatically so the user
    doesn't have to clean up between iterations; the tests exercise
    the refusal path against :func:`build_plugin_tree` directly.
    """
    project_root = project_root.resolve()
    dist_root = dist_root.resolve()
    tree_root = dist_root / PLUGIN_NAME

    if tree_root.exists():
        shutil.rmtree(tree_root)

    build_plugin_tree(project_root, tree_root, skills)

    archive_path = dist_root / f"{PLUGIN_NAME}.zip"
    if archive_path.exists():
        archive_path.unlink()
    return _make_archive(tree_root, archive_path)


# ---------------------------------------------------------------------------
# Release gate — refuse to package if the phase tests are broken.
# ---------------------------------------------------------------------------

def run_phase_tests(skill_root: Path) -> int:
    """Run pytest inside the primary skill and return its exit code.

    Packaging is allowed only when every phase test passes. This closes
    the roadmap's "test_all_phase_tests_pass_in_ci" intent without the
    circular-dependency that a pytest-level self-check would create.
    """
    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=str(skill_root),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    run_tests = True
    if "--skip-tests" in argv:
        run_tests = False
        argv.remove("--skip-tests")

    if not argv:
        print("usage: python -m scripts.package <project-root> [<dist-root>] [--skip-tests]")
        return 2

    project_root = Path(argv[0]).resolve()
    dist_root = Path(argv[1]).resolve() if len(argv) > 1 else project_root / "dist"

    if run_tests:
        skill_root = project_root / ".claude" / "skills" / "job-application-tailor"
        print(f"running phase tests in {skill_root} ...")
        rc = run_phase_tests(skill_root)
        if rc != 0:
            print(f"phase tests failed with exit code {rc}; refusing to package")
            return rc

    archive = package_plugin(project_root, dist_root)
    tree = dist_root / PLUGIN_NAME
    print(f"plugin tree:  {tree}")
    print(f"archive:      {archive}")
    print(f"size:         {archive.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
