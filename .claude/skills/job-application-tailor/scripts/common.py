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


def recount_match_summary(matches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compute match_summary deterministically from a matches[] array.

    The LLM is asked to author both ``matches[]`` and ``match_summary`` in
    the match analysis step, and the two regularly drift — the model
    miscounts, or edits matches without updating the summary. The summary
    is a pure function of the matches, so we let a script enforce it
    rather than trusting the LLM's arithmetic.

    ``overall_fit_pct`` formula matches ``prompts/match_analysis.md`` §
    ``overall_fit_pct``: ``(direct + transferable * 0.5) / total * 100``,
    rounded to the nearest integer. Empty matches array returns 0.
    """
    counts = {"direct": 0, "transferable": 0, "gap": 0}
    for m in matches:
        match_type = m.get("match_type") if isinstance(m, dict) else None
        if match_type in counts:
            counts[match_type] += 1
    total = counts["direct"] + counts["transferable"] + counts["gap"]
    if total == 0:
        fit_pct = 0
    else:
        fit_pct = round(
            (counts["direct"] + counts["transferable"] * 0.5) / total * 100
        )
    return {
        "direct_count": counts["direct"],
        "transferable_count": counts["transferable"],
        "gap_count": counts["gap"],
        "overall_fit_pct": fit_pct,
    }


def delete_stale_slug_deliverables(
    folder: Path, old_slug: str, new_slug: str
) -> list[str]:
    """Delete top-level deliverables matching the old slug after a rename.

    ``regenerate-outputs`` writes new-slug filenames but does not remove the
    pre-rename ones, so without this cleanup the folder ends up with two
    copies of every deliverable. Matches files of the form
    ``<anything>_<old_slug>.<ext>`` at the folder root only — files inside
    ``_prep/`` are not slug-named and are left alone. No-op when the slug is
    unchanged or empty.
    """
    if not old_slug or old_slug == new_slug:
        return []
    deleted: list[str] = []
    for stale in folder.glob(f"*_{old_slug}.*"):
        if stale.is_file():
            try:
                stale.unlink()
                deleted.append(stale.name)
            except OSError:
                pass
    return deleted


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
    # Drop characters that are ATS-legal but look ugly / inconsistent in filenames
    # (parentheses, brackets, dots). Dots inside titles like ".Net Core" survive in
    # the CV body and other outputs — we only strip them from the filename slug.
    value = re.sub(r"[()\[\]{}.]+", "", value)
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


def auto_slug(job_title: str | None, company: str | None) -> str:
    """Build a folder slug from job title and company, dash-separated.

    Used both at folder rename time (after job offer analysis surfaces a
    real title) and by ``rename-application`` when a real client is
    identified post-fact. Returns ``"untitled"`` rather than empty so the
    folder name is always well-formed.
    """
    raw = " ".join(part for part in (job_title, company) if part)
    cleaned = sanitize_component(raw)
    dashed = re.sub(r"\s+", "-", cleaned)
    dashed = re.sub(r"-+", "-", dashed)
    return dashed.strip("-") or "untitled"


def rename_cold_folder_with_canonical_name(folder: Path, canonical_name: str) -> Path:
    """Rebuild a ``cold-DDMMYYYY-<placeholder>/`` slug from the canonical
    company name surfaced by Step 3 research. Mirrors the offer flow's
    Step-4 rename: the slug created at preflight is a placeholder (built
    from the raw user input, often a URL), and this call replaces it with
    a clean ``cold-DDMMYYYY-<company-slug>/`` once research has resolved
    what the company actually is. No-op when the slug already matches.
    Raises ``FileExistsError`` if the target path is already taken.
    """
    current_name = folder.name
    date_match = re.match(r"^cold-(\d{8})-(.+)$", current_name)
    if not date_match:
        return folder
    date_prefix = date_match.group(1)
    new_slug = auto_slug(None, canonical_name)
    new_name = f"cold-{date_prefix}-{new_slug}"
    new_path = folder.parent / new_name
    if new_path == folder:
        return folder
    if new_path.exists():
        raise FileExistsError(
            f"Cannot rename {folder} -> {new_path}: target already exists"
        )
    folder.rename(new_path)
    return new_path


def rename_folder_with_fit(
    folder: Path,
    pct: int,
    *,
    job_title: str | None = None,
    company: str | None = None,
) -> Path:
    """Rename an output folder to include the fit-level prefix.

    By default the existing slug after the date prefix is preserved, so
    this is a pure ``[date]-[slug]/`` -> ``[fit_level]-[date]-[slug]/``
    operation. When ``job_title`` and/or ``company`` are supplied, the
    slug is recomputed via ``auto_slug``. This collapses the pipeline's
    historical two-step rename (placeholder slug at folder creation, then
    fit prefix at Step 4) into a single rename to the final
    ``[fit_level]-[date]-[job_title-company]/`` path.

    Returns the new path. No-op when the destination already matches.
    """
    level = fit_level(pct)
    current_name = folder.name
    # Avoid double-prefixing
    for prefix in ("very_good-", "good-", "medium-", "low-"):
        if current_name.startswith(prefix):
            current_name = current_name[len(prefix):]
    # Detect the date prefix (DDMMYYYY-) so we can rebuild the trailing slug
    # when caller passes job_title/company. Falls back to preserving whatever
    # is there when the date prefix is missing or the caller didn't override.
    if job_title or company:
        date_match = re.match(r"^(\d{8}-)(.+)$", current_name)
        if date_match:
            date_prefix = date_match.group(1)
            new_slug = auto_slug(job_title, company)
            current_name = f"{date_prefix}{new_slug}"
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


def matched_aggregator(name: str, platforms: Iterable[str]) -> str | None:
    """Return the platform-list entry that matches ``name``, or None.

    Matches on a case-insensitive word boundary so "Free-Work SA" resolves
    to "Free-Work" but "LinkedInSoft" does not collide with "LinkedIn".
    The human-in-the-loop Step 3 prompt catches any residual false positives.
    """
    if not name:
        return None
    for platform in platforms:
        if not platform:
            continue
        pattern = re.compile(r"\b" + re.escape(platform) + r"\b", re.IGNORECASE)
        if pattern.search(name):
            return platform
    return None


def is_aggregator(name: str, platforms: Iterable[str]) -> bool:
    """Return True if ``name`` matches any known-platform entry."""
    return matched_aggregator(name, platforms) is not None
