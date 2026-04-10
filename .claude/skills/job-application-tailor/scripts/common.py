from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import yaml


FORBIDDEN_DEFAULT = set('/\\:*?"<>|')


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def sanitize_component(text: str, replacement: str = "-", trim_chars: str = " .-_") -> str:
    if not text:
        return "untitled"
    value = text
    for ch in FORBIDDEN_DEFAULT:
        value = value.replace(ch, replacement)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"-{2,}", "-", value)
    value = value.strip(trim_chars)
    return value or "untitled"


def slug_for_filename(text: str) -> str:
    value = sanitize_component(text, replacement="-")
    value = re.sub(r"\s+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("._-")


def current_date_ddmmyyyy() -> str:
    return datetime.now().strftime("%d%m%Y")


def build_output_folder_name(date_str: str, job_title: str) -> str:
    return f"{date_str}-{sanitize_component(job_title)}"


_DEFAULT_FIT_LEVELS = {"very_good": 85, "good": 70, "medium": 50}


def _load_fit_levels() -> dict[str, int]:
    """Load fit level thresholds from layered settings, falling back to defaults."""
    # Local import to avoid a circular dependency: paths.py imports yaml but
    # never touches common.py, and common.py only needs this one function.
    from scripts.paths import load_settings

    try:
        settings = load_settings()
    except Exception:
        return _DEFAULT_FIT_LEVELS
    return settings.get("fit_levels", _DEFAULT_FIT_LEVELS)


def fit_level(pct: int) -> str:
    """Return a fit-level label for the given percentage."""
    levels = _load_fit_levels()
    if pct >= levels.get("very_good", 85):
        return "very_good"
    if pct >= levels.get("good", 70):
        return "good"
    if pct >= levels.get("medium", 50):
        return "medium"
    return "low"


def rename_folder_with_fit(folder: Path, pct: int) -> Path:
    """Rename an output folder to include the fit-level prefix. Returns the new path."""
    level = fit_level(pct)
    current_name = folder.name
    # Avoid double-prefixing
    for prefix in ("very_good-", "good-", "medium-", "low-"):
        if current_name.startswith(prefix):
            current_name = current_name[len(prefix):]
    new_name = f"{level}-{current_name}"
    new_path = folder.parent / new_name
    if new_path != folder:
        folder.rename(new_path)
    return new_path


def choose_cv_file(resource_folder: Path, preferred_filename: str | None = None) -> Path:
    if preferred_filename:
        preferred = resource_folder / preferred_filename
        if preferred.exists() and preferred.suffix.lower() == ".docx":
            return preferred

    docx_files = [p for p in resource_folder.iterdir() if p.is_file() and p.suffix.lower() == ".docx"]
    if not docx_files:
        raise FileNotFoundError("No DOCX CV file found in resource folder.")

    cv_named = [p for p in docx_files if "cv" in p.name.lower()]
    if cv_named:
        return sorted(cv_named, key=lambda p: p.stat().st_mtime, reverse=True)[0]

    return sorted(docx_files, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def safe_filename(pattern: str, candidate_name: str, job_title: str) -> str:
    return pattern.format(
        candidate_name=slug_for_filename(candidate_name),
        job_title=slug_for_filename(job_title),
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def cv_cache_is_valid(cv_path: Path, prep_dir: Path = None) -> bool:
    """Check if the cached CV fact base is still valid.

    Both .cv_hash and cv_fact_base.json are stored next to the CV file
    (e.g. resources/) so they persist across runs.
    """
    resources_dir = cv_path.parent
    cache_file = resources_dir / "cv_fact_base.json"
    hash_file = resources_dir / ".cv_hash"
    if not cache_file.exists() or not hash_file.exists():
        return False
    stored_hash = hash_file.read_text(encoding="utf-8").strip()
    return stored_hash == file_hash(cv_path)


def save_cv_fact_base(cv_path: Path, prep_dir: Path) -> None:
    """Save cv_fact_base.json and .cv_hash next to the CV, and copy to prep_dir."""
    import shutil
    resources_dir = cv_path.parent
    hash_file = resources_dir / ".cv_hash"
    ensure_dir(resources_dir)
    hash_file.write_text(file_hash(cv_path), encoding="utf-8")
    # Copy fact base from prep_dir to resources for future runs
    src = prep_dir / "cv_fact_base.json"
    dst = resources_dir / "cv_fact_base.json"
    if src.exists() and src != dst:
        shutil.copy2(str(src), str(dst))


def copy_cached_cv_fact_base(cv_path: Path, prep_dir: Path) -> None:
    """Copy the cached cv_fact_base.json from resources/ into the current prep_dir."""
    import shutil
    src = cv_path.parent / "cv_fact_base.json"
    dst = prep_dir / "cv_fact_base.json"
    ensure_dir(prep_dir)
    if src.exists() and src != dst:
        shutil.copy2(str(src), str(dst))
