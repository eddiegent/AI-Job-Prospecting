"""User data directory resolution and layered config loading.

Phase 3 of the plugin roadmap: keep plugin code (prompts, schemas, scripts)
separate from user data (master CV, history DB, output folders). This
module is the single source of truth for *where* user data lives.

Resolution order used by :func:`resolve_user_data_dir`:

1. ``JOB_TAILOR_HOME`` env var — explicit override, wins unconditionally.
2. Legacy project resources — if a ``resources/MASTER_CV.docx`` exists at
   the repo root relative to the skill install, the loose install is
   still authoritative. This is the back-compat invariant: existing users
   must keep working without migration until they opt in (Phase 4.5).
3. OS-standard user data dir:
    * Windows — ``%APPDATA%\\job-application-tailor``
    * macOS   — ``~/Library/Application Support/job-application-tailor``
    * Linux   — ``$XDG_DATA_HOME/job-application-tailor`` or
                ``~/.local/share/job-application-tailor``
4. Fallback — ``~/.job-application-tailor``.

This module is *read-only*. It never creates, copies, or mutates anything
on disk. Migration to the new location is Phase 4.5's job and is opt-in.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

import yaml


APP_NAME = "job-application-tailor"
ENV_VAR = "JOB_TAILOR_HOME"

# <repo>/.claude/skills/job-application-tailor — computed once at import.
SKILL_ROOT = Path(__file__).resolve().parent.parent


def _legacy_project_resources(skill_root: Path) -> Path | None:
    """Return the legacy ``<repo>/resources`` dir if it looks populated.

    The skill install sits at ``<repo>/.claude/skills/job-application-tailor``,
    so the repo root is ``skill_root.parents[2]``. We only consider the
    legacy location authoritative when it actually contains a master CV —
    an empty or missing folder must fall through to the OS-standard path.
    """
    try:
        repo_root = skill_root.parents[2]
    except IndexError:
        return None
    legacy = repo_root / "resources"
    if (legacy / "MASTER_CV.docx").exists():
        return legacy
    return None


def resolve_user_data_dir(
    *,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    skill_root: Path | None = None,
) -> Path:
    """Return the directory where user data (CV, DB, output/) lives.

    The env/platform/skill_root arguments are dependency-injection hooks so
    tests can exercise each branch without monkeypatching os.environ or
    sys.platform. Production callers should pass nothing.

    This function never touches the filesystem except to probe for the
    legacy install — it does not create the resolved directory.
    """
    env = env if env is not None else os.environ
    platform = platform or sys.platform
    skill_root = skill_root or SKILL_ROOT

    override = env.get(ENV_VAR)
    if override:
        return Path(override)

    legacy = _legacy_project_resources(skill_root)
    if legacy is not None:
        return legacy

    if platform == "win32":
        base = env.get("APPDATA")
        if not base:
            home = env.get("USERPROFILE") or env.get("HOME") or str(Path.home())
            base = str(Path(home) / "AppData" / "Roaming")
        return Path(base) / APP_NAME

    if platform == "darwin":
        home = env.get("HOME") or str(Path.home())
        return Path(home) / "Library" / "Application Support" / APP_NAME

    if platform.startswith("linux"):
        xdg = env.get("XDG_DATA_HOME")
        if xdg:
            return Path(xdg) / APP_NAME
        home = env.get("HOME") or str(Path.home())
        return Path(home) / ".local" / "share" / APP_NAME

    home = env.get("HOME") or str(Path.home())
    return Path(home) / f".{APP_NAME}"


# ----- config layering --------------------------------------------------

_DEFAULT_SETTINGS_FILENAME = "settings.default.yaml"
_USER_SETTINGS_FILENAME = "settings.yaml"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into a copy of ``base``.

    Dict values are merged key-by-key; every other type is replaced wholesale.
    This is what the roadmap's ``test_config_layering_merges_correctly``
    invariant pins: overriding one key inside a nested dict must not wipe
    the other keys at that level.
    """
    merged: dict[str, Any] = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(existing, value)
        else:
            merged[key] = value
    return merged


def _load_yaml_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_settings(
    *,
    defaults_path: Path | None = None,
    user_data_dir: Path | None = None,
) -> dict[str, Any]:
    """Load plugin settings, applying the user override on top of defaults.

    The defaults live inside the plugin install at
    ``config/settings.default.yaml`` and ship with the skill. The override
    lives at ``<user_data_dir>/settings.yaml`` and is optional — missing
    means "defaults only, no error".
    """
    if defaults_path is None:
        defaults_path = SKILL_ROOT / "config" / _DEFAULT_SETTINGS_FILENAME
    if user_data_dir is None:
        user_data_dir = resolve_user_data_dir()

    defaults = _load_yaml_or_empty(defaults_path)
    user_override = _load_yaml_or_empty(user_data_dir / _USER_SETTINGS_FILENAME)
    return _deep_merge(defaults, user_override)
