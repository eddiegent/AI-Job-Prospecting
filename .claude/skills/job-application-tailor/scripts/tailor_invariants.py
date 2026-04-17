"""Pure-Python validators for the rules documented in prompts/tailor_cv.md.

The tailoring step itself is model-driven (the prompt in tailor_cv.md is
executed by Claude, not a Python function). These validators exist so that
a produced tailored_cv.json can be checked against the rules *after* the
model has written it, and so that those rules can be pinned in regression
tests that run without invoking a model.

Each function takes already-parsed dicts/lists and returns a list of
violation messages. An empty list means the invariant holds.
"""
from __future__ import annotations

import re
from typing import Any


# --- Training-in-Education rule --------------------------------------------

def _combined_line(item: dict[str, Any]) -> str:
    """Return ``role_line`` and ``metadata_line`` joined by a separator so a
    single substring scan can find text from either field."""
    return f"{item.get('role_line', '')} || {item.get('metadata_line', '')}"


def find_training_entries_in_experience(
    tailored_cv: dict[str, Any],
    fact_base: dict[str, Any],
) -> list[str]:
    """Return a list of violation messages for training entries that leaked
    into the tailored CV's experience array.

    Matching is done on company name (case-insensitive, substring) against
    the combined ``role_line`` + ``metadata_line`` text so the check works
    regardless of which field the company name ended up in.
    """
    training_companies = [
        entry.get("company", "").strip()
        for entry in fact_base.get("experience", [])
        if entry.get("type") == "training"
    ]
    training_companies = [c for c in training_companies if c]

    violations: list[str] = []
    for item in tailored_cv.get("experience", []):
        line = _combined_line(item)
        for company in training_companies:
            if company.lower() in line.lower():
                violations.append(
                    f"Training entry '{company}' found in tailored experience: {line!r}"
                )
    return violations


# --- Earlier-experience compression rule ----------------------------------

CONSOLIDATED_HEADINGS = {
    "fr": "Expériences antérieures",
    "en": "Earlier experience",
}


def _end_year_from_dates(dates: str) -> int | None:
    """Best-effort end-year extraction from free-form date strings used in
    the master CV (e.g. ``'2003 – 2008'``, ``'Janvier 2010 – Mars 2025'``,
    ``'1994 - 2001'``). Returns the latest 4-digit year in the string, which
    is a good enough proxy for the role's end date for invariant checking.
    """
    years = [int(y) for y in re.findall(r"(19\d{2}|20\d{2})", dates or "")]
    return max(years) if years else None


def _role_is_load_bearing(
    company: str,
    dates: str,
    match_analysis: dict[str, Any],
) -> bool:
    """Criterion A only: match analysis evidence names the company or date.

    Criteria B and C (technology overlap, unique responsibility coverage)
    require the job offer analysis and are not modelled here — the tests
    in this phase construct fixtures that only exercise criterion A, which
    is the criterion the prompt relies on most heavily in practice.
    """
    company_l = company.strip().lower()
    for match in match_analysis.get("matches", []):
        if match.get("match_type") not in {"direct", "transferable"}:
            continue
        evidence = (match.get("evidence") or "").lower()
        if company_l and company_l in evidence:
            return True
        if dates and dates.lower() in evidence:
            return True
    return False


def find_missing_load_bearing_roles(
    tailored_cv: dict[str, Any],
    fact_base: dict[str, Any],
    match_analysis: dict[str, Any],
    cutoff_year: int | None,
) -> list[str]:
    """Return violations for pre-cutoff roles that were load-bearing per the
    match analysis but are absent from the tailored CV's experience array.

    A pre-cutoff role is one whose end year is strictly less than
    ``cutoff_year``. When ``cutoff_year`` is None, compression is disabled
    and no pre-cutoff distinction is made.
    """
    if cutoff_year is None:
        return []

    # Load-bearing roles must appear as standalone entries, not folded into
    # the consolidated "Earlier experience" line. Exclude that line from the
    # haystack so a folded role registers as missing.
    tailored_lines = " \n ".join(
        _combined_line(item)
        for item in tailored_cv.get("experience", [])
        if not any(
            h in item.get("role_line", "")
            for h in CONSOLIDATED_HEADINGS.values()
        )
    ).lower()

    violations: list[str] = []
    for entry in fact_base.get("experience", []):
        if entry.get("type") == "training":
            continue
        end_year = _end_year_from_dates(entry.get("dates", ""))
        if end_year is None or end_year >= cutoff_year:
            continue
        company = entry.get("company", "")
        if not _role_is_load_bearing(company, entry.get("dates", ""), match_analysis):
            continue
        if company.lower() not in tailored_lines:
            violations.append(
                f"Load-bearing pre-cutoff role {company!r} ({entry.get('dates')}) "
                f"is missing from tailored experience"
            )
    return violations


def find_non_consolidated_non_load_bearing_roles(
    tailored_cv: dict[str, Any],
    fact_base: dict[str, Any],
    match_analysis: dict[str, Any],
    cutoff_year: int | None,
) -> list[str]:
    """Return violations for non-load-bearing pre-cutoff roles that still
    appear as standalone entries in the tailored CV (they should be folded
    into the consolidated line).
    """
    if cutoff_year is None:
        return []

    violations: list[str] = []
    for entry in fact_base.get("experience", []):
        if entry.get("type") == "training":
            continue
        end_year = _end_year_from_dates(entry.get("dates", ""))
        if end_year is None or end_year >= cutoff_year:
            continue
        company = entry.get("company", "")
        if _role_is_load_bearing(company, entry.get("dates", ""), match_analysis):
            continue
        for item in tailored_cv.get("experience", []):
            if any(h in item.get("role_line", "") for h in CONSOLIDATED_HEADINGS.values()):
                continue
            line = _combined_line(item)
            if company.lower() in line.lower():
                violations.append(
                    f"Non-load-bearing pre-cutoff role {company!r} should be "
                    f"consolidated but appears as a standalone entry: {line!r}"
                )
    return violations


def find_consolidated_line_issues(
    tailored_cv: dict[str, Any],
    expected_language: str,
) -> list[str]:
    """Return violations about the consolidated 'Earlier experience' line:
    it must be dateless (no year in the metadata line) and use the heading in
    the expected language.
    """
    year_re = re.compile(r"\b(19|20)\d{2}\b")
    violations: list[str] = []
    expected_heading = CONSOLIDATED_HEADINGS.get(expected_language)
    for item in tailored_cv.get("experience", []):
        role_line = item.get("role_line", "")
        if not any(h in role_line for h in CONSOLIDATED_HEADINGS.values()):
            continue
        meta = item.get("metadata_line", "")
        if year_re.search(meta):
            violations.append(
                f"Consolidated line must be dateless, metadata_line contains a year: {meta!r}"
            )
        if expected_heading and expected_heading not in role_line:
            violations.append(
                f"Consolidated line heading for language {expected_language!r} "
                f"should contain {expected_heading!r}, got: {role_line!r}"
            )
    return violations
