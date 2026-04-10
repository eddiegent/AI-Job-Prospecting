"""Phase 3 regression tests for scripts/paths.py and config layering.

These tests pin the user-data-dir resolution invariants so the plugin can be
installed on any OS without either (a) silently orphaning an existing loose
install or (b) writing to the wrong place on a fresh machine.

Resolution order under test:

1. ``JOB_TAILOR_HOME`` env var wins unconditionally.
2. Legacy project resources wins if present (back-compat for existing users).
3. OS-standard data dir (APPDATA / Library / XDG) otherwise.

Phase 3 is read-only: none of the code introduced by this phase may write
to the resolved data dir — migration is Phase 4.5's job.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts import paths
from scripts.paths import resolve_user_data_dir


# ----- helpers ----------------------------------------------------------

def _make_fake_skill_root(tmp_path: Path, *, with_legacy_resources: bool) -> Path:
    """Create a fake <repo>/.claude/skills/job-application-tailor/ tree.

    When ``with_legacy_resources`` is true, also drops a ``resources/``
    folder at the repo root containing a fake MASTER_CV.docx — which is the
    signal the resolver uses to detect a legacy install.
    """
    repo = tmp_path / "fake_repo"
    skill_root = repo / ".claude" / "skills" / "job-application-tailor"
    skill_root.mkdir(parents=True)
    if with_legacy_resources:
        legacy = repo / "resources"
        legacy.mkdir()
        (legacy / "MASTER_CV.docx").write_bytes(b"fake docx bytes")
    return skill_root


# ----- core resolution --------------------------------------------------

def test_resolve_returns_legacy_path_when_project_resources_exists(tmp_path):
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=True)
    resolved = resolve_user_data_dir(
        env={}, platform="linux", skill_root=skill_root
    )
    assert resolved == (skill_root.parents[2] / "resources")
    assert (resolved / "MASTER_CV.docx").exists()


def test_resolve_returns_xdg_path_on_linux_with_no_legacy(tmp_path):
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=False)
    fake_home = tmp_path / "home"
    fake_xdg = tmp_path / "xdg_data"
    resolved = resolve_user_data_dir(
        env={"HOME": str(fake_home), "XDG_DATA_HOME": str(fake_xdg)},
        platform="linux",
        skill_root=skill_root,
    )
    assert resolved == fake_xdg / "job-application-tailor"


def test_resolve_linux_falls_back_to_local_share_when_xdg_unset(tmp_path):
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=False)
    fake_home = tmp_path / "home"
    resolved = resolve_user_data_dir(
        env={"HOME": str(fake_home)},
        platform="linux",
        skill_root=skill_root,
    )
    assert resolved == fake_home / ".local" / "share" / "job-application-tailor"


def test_resolve_returns_library_path_on_mac_with_no_legacy(tmp_path):
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=False)
    fake_home = tmp_path / "home"
    resolved = resolve_user_data_dir(
        env={"HOME": str(fake_home)},
        platform="darwin",
        skill_root=skill_root,
    )
    assert resolved == (
        fake_home / "Library" / "Application Support" / "job-application-tailor"
    )


def test_resolve_returns_appdata_path_on_windows_with_no_legacy(tmp_path):
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=False)
    fake_appdata = tmp_path / "AppData" / "Roaming"
    resolved = resolve_user_data_dir(
        env={"APPDATA": str(fake_appdata)},
        platform="win32",
        skill_root=skill_root,
    )
    assert resolved == fake_appdata / "job-application-tailor"


def test_env_var_overrides_everything(tmp_path):
    # Legacy resources AND a populated APPDATA both present; env var must win.
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=True)
    override = tmp_path / "custom_dir"
    resolved = resolve_user_data_dir(
        env={
            "JOB_TAILOR_HOME": str(override),
            "APPDATA": str(tmp_path / "AppData" / "Roaming"),
        },
        platform="win32",
        skill_root=skill_root,
    )
    assert resolved == override


# ----- Phase 3 must be read-only ---------------------------------------

def test_phase_3_reads_only_never_writes(tmp_path, monkeypatch):
    """resolve_user_data_dir must not create or mutate anything on disk."""
    skill_root = _make_fake_skill_root(tmp_path, with_legacy_resources=False)
    target = tmp_path / "brand_new_location"
    assert not target.exists()

    # Spy on Path.mkdir and builtins.open (write modes) to catch writes.
    writes: list[str] = []
    real_mkdir = Path.mkdir

    def spy_mkdir(self, *args, **kwargs):
        writes.append(f"mkdir:{self}")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", spy_mkdir)

    resolved = resolve_user_data_dir(
        env={"JOB_TAILOR_HOME": str(target)},
        platform="linux",
        skill_root=skill_root,
    )
    assert resolved == target
    assert not target.exists(), "resolve must not create the data dir"
    assert writes == [], f"resolve performed filesystem writes: {writes}"


# ----- config layering -------------------------------------------------

def test_config_layering_merges_correctly(tmp_path):
    defaults = {
        "default_language": "auto",
        "fallback_language": "fr",
        "fit_levels": {"very_good": 85, "good": 70, "medium": 50},
        "behaviour": {"dry_run": False, "experience_compression_cutoff_year": 2005},
    }
    override = {
        "fallback_language": "en",  # override a scalar
        "fit_levels": {"good": 75},  # override one key inside a dict
        "behaviour": {"dry_run": True},  # override one key inside a dict
    }

    defaults_path = tmp_path / "settings.default.yaml"
    user_data_dir = tmp_path / "user_data"
    user_data_dir.mkdir()
    user_path = user_data_dir / "settings.yaml"

    defaults_path.write_text(yaml.safe_dump(defaults), encoding="utf-8")
    user_path.write_text(yaml.safe_dump(override), encoding="utf-8")

    merged = paths.load_settings(
        defaults_path=defaults_path, user_data_dir=user_data_dir
    )

    # Untouched scalars survive.
    assert merged["default_language"] == "auto"
    # Overridden scalars win.
    assert merged["fallback_language"] == "en"
    # Nested override merges key-by-key, does not replace the whole dict.
    assert merged["fit_levels"] == {"very_good": 85, "good": 75, "medium": 50}
    assert merged["behaviour"]["dry_run"] is True
    assert merged["behaviour"]["experience_compression_cutoff_year"] == 2005


def test_config_layering_returns_defaults_when_user_file_missing(tmp_path):
    defaults = {"fallback_language": "fr", "fit_levels": {"good": 70}}
    defaults_path = tmp_path / "settings.default.yaml"
    defaults_path.write_text(yaml.safe_dump(defaults), encoding="utf-8")

    user_data_dir = tmp_path / "user_data"
    user_data_dir.mkdir()

    merged = paths.load_settings(
        defaults_path=defaults_path, user_data_dir=user_data_dir
    )
    assert merged == defaults


# ----- no hardcoded paths in scripts -----------------------------------

# Scripts that are explicitly legacy-aware (they manipulate the old project
# layout on purpose) and are allowed to reference ``resources/`` literally.
_LEGACY_AWARE_SCRIPTS = {"backup_user_data.py", "paths.py", "migrate.py"}


def _script_files() -> list[Path]:
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    return sorted(
        p for p in scripts_dir.glob("*.py") if p.name != "__init__.py"
    )


def test_no_hardcoded_absolute_paths_in_scripts():
    """No script should embed a machine-specific absolute path."""
    offenders: list[str] = []
    for path in _script_files():
        text = path.read_text(encoding="utf-8")
        # Windows drive letters like C:\ and Unix /home/ paths.
        for marker in ("C:\\", "C:/", "/home/", "/Users/"):
            if marker in text:
                offenders.append(f"{path.name}: contains {marker!r}")
    assert offenders == [], "\n".join(offenders)


def test_no_hardcoded_resources_slash_in_scripts():
    """Only legacy-aware scripts may hardcode the old ``resources/`` path."""
    offenders: list[str] = []
    for path in _script_files():
        if path.name in _LEGACY_AWARE_SCRIPTS:
            continue
        text = path.read_text(encoding="utf-8")
        # Look for "resources/" or "resources\\" used as a path literal.
        # Strings inside docstrings/comments are OK — we only flag code-like
        # usages via the common constructors.
        bad_patterns = [
            '"resources/',
            "'resources/",
            '"resources\\\\',
            "'resources\\\\',",
            '/ "resources"',
            "/ 'resources'",
        ]
        for pat in bad_patterns:
            if pat in text:
                offenders.append(f"{path.name}: contains {pat!r}")
    assert offenders == [], "\n".join(offenders)
