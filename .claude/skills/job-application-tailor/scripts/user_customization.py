"""User-owned customization layer for job-application-tailor.

Reads two optional user-controlled files and exposes them as a single
context dict consumed by Step 0 of the skill:

- ``cv_addendum.md`` — per-run enrichment to the fact base: bullets that
  belong on specific existing roles, hidden skills, and off-CV facts the
  user wants the skill to remember. This layer is applied in-memory only;
  it must never mutate the cached ``cv_fact_base.json`` (that file reflects
  the raw docx and is used by ``verify_fact_base.py`` as the ground truth).
- ``user_prefs.yaml`` — tone and labelling preferences: title labels the
  user will/will-not accept, tone directives for the letter generator, and
  companies where the user was part of a team (so letters don't phrase
  their contributions as solo work).

The module also exposes pure-Python invariant checkers that mirror the
pattern used by ``scripts/tailor_invariants.py``: pass in an already
produced tailored_cv / letter text, get back a list of violations.
"""
from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any


DEFAULT_PREFS: dict[str, Any] = {
    "preferred_title_labels": [],
    "forbidden_title_labels": [],
    "tone_directives": [],
    "team_context_companies": [],
    "default_language": "auto",
}


EMPTY_ADDENDUM: dict[str, Any] = {
    "additional_experience": {},
    "hidden_skills": [],
    "off_cv_facts": [],
}


# --- Parsing ---------------------------------------------------------------

def parse_addendum_md(text: str) -> dict[str, Any]:
    """Parse the markdown addendum into a structured dict.

    Recognises three top-level ``## `` sections:

    - ``## Additional experience entries`` — each ``### Company — Dates``
      subsection becomes a key in ``additional_experience`` whose value is
      a list of bullet strings.
    - ``## Hidden skills`` — flat list of bullet strings.
    - ``## Off-CV facts to remember`` — flat list of bullet strings.

    Unknown sections are ignored rather than raising, so the file format is
    forgiving of user notes.
    """
    result: dict[str, Any] = {
        "additional_experience": {},
        "hidden_skills": [],
        "off_cv_facts": [],
    }
    current_section: str | None = None
    current_entry: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("## "):
            heading = stripped[3:].strip().lower()
            if "additional" in heading and "experience" in heading:
                current_section = "additional_experience"
            elif "hidden skill" in heading:
                current_section = "hidden_skills"
            elif "off-cv" in heading or "off cv" in heading:
                current_section = "off_cv_facts"
            else:
                current_section = None
            current_entry = None
            continue
        if stripped.startswith("### ") and current_section == "additional_experience":
            current_entry = stripped[4:].strip()
            result["additional_experience"].setdefault(current_entry, [])
            continue
        if stripped.startswith("- "):
            item = stripped[2:].strip()
            if not item:
                continue
            if current_section == "additional_experience" and current_entry:
                result["additional_experience"][current_entry].append(item)
            elif current_section == "hidden_skills":
                result["hidden_skills"].append(item)
            elif current_section == "off_cv_facts":
                result["off_cv_facts"].append(item)
    return result


# --- Loading ---------------------------------------------------------------

def load_addendum(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(EMPTY_ADDENDUM)
    return parse_addendum_md(path.read_text(encoding="utf-8"))


def load_user_prefs(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(DEFAULT_PREFS)
    import yaml  # lazy import so tests that never touch prefs don't need pyyaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = copy.deepcopy(DEFAULT_PREFS)
    for key, value in data.items():
        if key in DEFAULT_PREFS:
            merged[key] = value
    return merged


def load_customization_context(user_data_dir: Path) -> dict[str, Any]:
    """Return the merged customization context for Step 0.

    Both files are optional. Missing files return the typed empty defaults
    so downstream code can call into the context without any ``if present``
    gymnastics.
    """
    user_data_dir = Path(user_data_dir)
    return {
        "addendum": load_addendum(user_data_dir / "cv_addendum.md"),
        "prefs": load_user_prefs(user_data_dir / "user_prefs.yaml"),
    }


# --- Merging into the in-memory fact base ---------------------------------

_ENTRY_KEY_SPLIT = re.compile(r"\s+[\u2014\u2013-]\s+")


def _normalize_dashes(text: str) -> str:
    """Collapse em/en dashes and the ASCII hyphen to a single form so that
    date strings like ``Octobre 1994 \u2013 Mai 2001`` (en dash, as emitted
    by the fact base extractor) match an addendum key written with a plain
    ASCII hyphen."""
    return text.replace("\u2014", "-").replace("\u2013", "-")


def merge_addendum_into_fact_base(
    fact_base: dict[str, Any],
    addendum: dict[str, Any],
) -> dict[str, Any]:
    """Return a NEW fact base dict with addendum content merged in.

    Invariants this function pins:

    1. The input ``fact_base`` is never mutated (deep-copied before merge).
    2. Addendum bullets attach to ``experience[*].details`` only. They do
       NOT enter ``technologies`` or ``methodologies``, which remain the
       exclusive province of the raw-docx extractor. This keeps
       ``verify_fact_base.py`` honest.
    3. Hidden skills and off-CV facts land in dedicated buckets
       (``addendum_hidden_skills``, ``addendum_off_cv_facts``) so prompts
       that want them can pull them, and prompts that don't want them
       (e.g. the extractor's self-check) are unaffected.
    """
    merged = copy.deepcopy(fact_base)
    additional = addendum.get("additional_experience", {}) or {}

    for entry_key, extra_bullets in additional.items():
        parts = _ENTRY_KEY_SPLIT.split(entry_key, maxsplit=1)
        if len(parts) != 2:
            continue
        company, dates = parts[0].strip(), parts[1].strip()
        dates_normalized = _normalize_dashes(dates)
        for entry in merged.get("experience", []):
            if entry.get("type") == "training":
                continue
            if entry.get("company", "").strip().lower() != company.lower():
                continue
            entry_dates = _normalize_dashes(entry.get("dates", ""))
            if dates_normalized and dates_normalized not in entry_dates:
                continue
            entry.setdefault("details", []).extend(extra_bullets)
            break

    hidden = list(addendum.get("hidden_skills", []) or [])
    if hidden:
        merged["addendum_hidden_skills"] = hidden
    facts = list(addendum.get("off_cv_facts", []) or [])
    if facts:
        merged["addendum_off_cv_facts"] = facts
    return merged


# --- Invariant checkers ----------------------------------------------------

def find_forbidden_title_label_violations(
    tailored_cv: dict[str, Any],
    user_prefs: dict[str, Any],
) -> list[str]:
    """Return violation messages for any forbidden label appearing in the
    tailored CV's ``title`` field (case-insensitive whole-word match)."""
    forbidden = [
        str(label).strip()
        for label in user_prefs.get("forbidden_title_labels", []) or []
        if str(label).strip()
    ]
    title = str(tailored_cv.get("title", ""))
    lowered = title.lower()
    violations: list[str] = []
    for label in forbidden:
        pattern = r"\b" + re.escape(label.lower()) + r"\b"
        if re.search(pattern, lowered):
            violations.append(
                f"Forbidden title label {label!r} present in tailored_cv.title: {title!r}"
            )
    return violations


_SOLO_PATTERNS = [
    r"\bseul\s+d[ée]veloppeur\b",
    r"\bseule\s+d[ée]veloppeuse\b",
    r"\ben\s+tant\s+que\s+seul\b",
    r"\bsolo\b",
    r"\bsingle[\s-]handedly\b",
    r"\bas\s+the\s+only\s+developer\b",
    r"\bby\s+myself\b",
    r"\bj[’']?ai\s+d[ée]velopp[ée]\s+seul\b",
]


def find_team_context_solo_phrasing(
    letter_text: str,
    user_prefs: dict[str, Any],
) -> list[str]:
    """Return violation messages when the letter uses solo-work phrasing in
    the vicinity of a company the user listed under ``team_context_companies``.

    Proximity heuristic: look within a 200-character window on either side
    of each company mention. Fuzzy on purpose — the letter generator is a
    model, so we are pattern-matching its prose, not parsing an AST.
    """
    companies = [
        str(c).strip()
        for c in user_prefs.get("team_context_companies", []) or []
        if str(c).strip()
    ]
    lowered = letter_text.lower()
    violations: list[str] = []
    for company in companies:
        needle = company.lower()
        for match in re.finditer(re.escape(needle), lowered):
            window_start = max(0, match.start() - 200)
            window_end = min(len(lowered), match.end() + 200)
            window = lowered[window_start:window_end]
            for pattern in _SOLO_PATTERNS:
                if re.search(pattern, window):
                    violations.append(
                        f"Solo-work phrasing near team-context company {company!r}: "
                        f"pattern /{pattern}/ matched in window {window!r}"
                    )
                    break
    return violations
