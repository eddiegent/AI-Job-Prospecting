"""Pure-Python validators for the rules documented in prompts/cv_rules.md (shared by both CV-tailoring prompts).

The tailoring step itself is model-driven (the prompts in cv_rules.md / tailor_cv.md are
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


def _is_consolidated(item: dict[str, Any]) -> bool:
    return any(h in item.get("role_line", "") for h in CONSOLIDATED_HEADINGS.values())


_PARENTHETICAL = re.compile(r"\([^)]*\)")
# How far after an ambiguous company mention its years may sit:
# "JFC Informatique & Média, Asnières (1994–2001)".
_YEAR_WINDOW = 40
_LEGAL_FORM = re.compile(r"\s+(?:sas|sa|sarl|ltd|limited|inc|gmbh|llc|plc)\.?$")


def _company_core(name: str) -> str:
    """Company name without a parenthetical or a trailing legal form, so
    ``JFC Informatique & Média (Kantar)`` and ``Oodrive SAS`` still match a CV
    line that writes ``JFC Informatique & Média`` or ``Oodrive SA``."""
    s = " ".join(_PARENTHETICAL.sub(" ", name.lower()).split())
    return _LEGAL_FORM.sub("", s).strip(" ,.")


def _shows_role(item: dict[str, Any], entry: dict[str, Any]) -> bool:
    """True when a tailored experience item is this fact-base role: it names
    the company and the role's end year. The year tells apart roles whose
    company names overlap (``Peaktime SAS`` / ``Telmar Peaktime SAS``, the
    two JFC roles)."""
    core = _company_core(entry.get("company", ""))
    line = " ".join(_combined_line(item).lower().split())
    if not core or core not in line:
        return False
    end_year = _end_year_from_dates(entry.get("dates", ""))
    return end_year is None or str(end_year) in line


def role_tags(entry: dict[str, Any], entries: list[dict[str, Any]]) -> tuple[str, ...]:
    """Words that tell this role apart from another role at a company of the
    same name: its bracketed name ("Kantar" in "JFC Informatique & Média
    (Kantar)") and its location when no other role shares it ("Asnières")."""
    tags = [t.strip() for t in re.findall(r"\(([^)]+)\)", entry.get("company", ""))]
    loc = (entry.get("location") or "").strip()
    if loc and sum(1 for e in entries if (e.get("location") or "").strip().lower() == loc.lower()) == 1:
        tags.append(loc)
    return tuple(t.lower() for t in tags if t)


def _role_is_load_bearing(
    company: str,
    dates: str,
    match_analysis: dict[str, Any],
    companies: list[str] | tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> bool:
    """Criterion A only: match analysis evidence names the company or date.

    Criteria B and C (technology overlap, unique responsibility coverage)
    require the job offer analysis and are not modelled here — the tests
    in this phase construct fixtures that only exercise criterion A, which
    is the criterion the prompt relies on most heavily in practice.

    ``companies`` lists every fact-base company. Longer names that contain
    this one are blanked out of the evidence first ("Telmar Peaktime" is not
    "Peaktime"). When another role's name still overlaps (the two JFC roles),
    a mention only counts with one of this role's years or ``tags`` (see
    ``role_tags``) next to it: "JFC Informatique & Média (2002–2005)" and
    "JFC (Kantar)" are the Kantar role, "JFC Asnières" the 1994–2001 one.

    The company's first word counts as a mention too ("JFC", "ROCC"): evidence
    rarely spells the full legal name, and a 2026-11-17 rerun folded a role its
    own evidence cited as "JFC (Asnières)" because only the full name counted.
    """
    core = _company_core(company)
    cores = [c for c in map(_company_core, companies) if c]
    longer = [c for c in cores if core and core in c and c != core]
    ambiguous = sum(1 for c in cores if core and (c == core or c in core)) > 1
    years = {str(y) for y in re.findall(r"(19\d{2}|20\d{2})", dates or "")}
    marks = years | set(tags)
    first = core.split()[0] if core else ""
    names = [core] + ([first] if len(first) >= 3 and first != core else [])
    # The first word is ambiguous when another company starts with it ("JFC" x2):
    # then it needs one of this role's marks next to it, like an ambiguous full name.
    first_shared = sum(1 for c in cores if c.split()[:1] == [first]) > 1
    for match in match_analysis.get("matches", []):
        if match.get("match_type") not in {"direct", "transferable"}:
            continue
        evidence = (match.get("evidence") or "").lower()
        for name in longer:
            evidence = evidence.replace(name, " ")
        for name in names:
            needs_mark = ambiguous or (name == first and first_shared)
            for m in re.finditer(r"(?<![\w])" + re.escape(name) + r"(?![\w])", evidence):
                near = evidence[max(0, m.start() - _YEAR_WINDOW):m.end() + _YEAR_WINDOW]
                if not needs_mark or any(k in near for k in marks):
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
    # the consolidated "Earlier experience" line, so that line is excluded.
    standalone = [i for i in tailored_cv.get("experience", []) if not _is_consolidated(i)]
    companies = [e.get("company", "") for e in fact_base.get("experience", [])]

    violations: list[str] = []
    for entry in fact_base.get("experience", []):
        if entry.get("type") == "training":
            continue
        end_year = _end_year_from_dates(entry.get("dates", ""))
        if end_year is None or end_year >= cutoff_year:
            continue
        company = entry.get("company", "")
        tags = role_tags(entry, fact_base.get("experience", []))
        if not _role_is_load_bearing(company, entry.get("dates", ""), match_analysis, companies, tags):
            continue
        if not any(_shows_role(item, entry) for item in standalone):
            violations.append(
                f"Load-bearing pre-cutoff role {company!r} ({entry.get('dates')}) "
                f"is missing from tailored experience"
            )
    return violations


def find_missing_recent_roles(
    tailored_cv: dict[str, Any],
    fact_base: dict[str, Any],
    cutoff_year: int | None,
) -> list[str]:
    """Return violations for roles ending in or after ``cutoff_year`` that are
    not a full experience entry — dropped, or folded into the consolidated
    "Earlier experience" line. Only pre-cutoff roles may be folded, so with
    ``cutoff_year`` None (compression disabled) every role must appear.
    """
    standalone = [i for i in tailored_cv.get("experience", []) if not _is_consolidated(i)]
    violations: list[str] = []
    for entry in fact_base.get("experience", []):
        if entry.get("type") == "training":
            continue
        if cutoff_year is not None:
            end_year = _end_year_from_dates(entry.get("dates", ""))
            if end_year is None or end_year < cutoff_year:
                continue
        if any(_shows_role(item, entry) for item in standalone):
            continue
        rule = (f"it ends in or after the {cutoff_year} cutoff" if cutoff_year is not None
                else "compression is off")
        violations.append(
            f"Role {entry.get('company')!r} ({entry.get('dates')}) is not a full experience "
            f"entry - {rule}, so it must not be dropped or folded into the earlier-experience line"
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

    companies = [e.get("company", "") for e in fact_base.get("experience", [])]
    violations: list[str] = []
    for entry in fact_base.get("experience", []):
        if entry.get("type") == "training":
            continue
        end_year = _end_year_from_dates(entry.get("dates", ""))
        if end_year is None or end_year >= cutoff_year:
            continue
        company = entry.get("company", "")
        tags = role_tags(entry, fact_base.get("experience", []))
        if _role_is_load_bearing(company, entry.get("dates", ""), match_analysis, companies, tags):
            continue
        for item in tailored_cv.get("experience", []):
            if _is_consolidated(item):
                continue
            line = _combined_line(item)
            if _shows_role(item, entry):
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
        if not _is_consolidated(item):
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
