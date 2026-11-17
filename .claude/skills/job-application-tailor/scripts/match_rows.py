"""The row list of a match analysis, built from the offer analysis.

Why: `overall_fit_pct` = (direct + 0.5 * transferable) / rows. When the model
chose the rows, the same offer gave different scores from run to run - it
merged some offer items, split others, picked "key" responsibilities, and
folded a missing technology into a broader transferable row (half credit
instead of a gap). On the 25 offer packs from 2026-10-21 to 2026-11-16 only
71% of the offer's skill / technology items had a row of their own, and
responsibility rows ranged from 1 of 6 to all of them.

Rule: one row per item of `required_skills`, `preferred_skills`,
`technologies` and `responsibilities`, in that order, with the item's text as
`requirement` and its list as `category`. An item listed twice (e.g. "C#" in
required_skills and technologies) gets one row, under the first list. The
model only judges each row (match_type, evidence, notes); `gate match` blocks
a missing, extra or recategorised row.

A technology a skill item already names gets no row of its own: the offer
asks for it once. Without this, "Jira, Confluence" (a required skill) plus
"Jira" and "Confluence" (technologies) scored one fact three times, and on
the 2026-11-17 comparison runs that alone moved a pack from 67% (medium) to
71% (good). The skill row rates the technology; a missing one keeps that row
off `direct` (scripts/check_match_grounding.py).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

# Offer list -> match row category, in priority order for duplicates.
LISTS: tuple[tuple[str, str], ...] = (
    ("required_skills", "required_skill"),
    ("preferred_skills", "preferred_skill"),
    ("technologies", "technology"),
    ("responsibilities", "responsibility"),
)


def row_key(text: str) -> str:
    """Comparison key for a requirement: case, accents, spacing, spaces around
    a slash and trailing punctuation don't count ("Maîtrise de C# ." == "maitrise de c#")."""
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("’", "'")
    s = re.sub(r"\s*/\s*", "/", s)  # "Claude Cowork / skills" == "Claude Cowork/skills"
    return re.sub(r"\s+", " ", s).strip(" .;:,")


# Lists whose items can name a technology the offer also lists on its own.
SKILL_LISTS = ("required_skills", "preferred_skills")


def _named_in(tech_key: str, text_key: str) -> bool:
    """``tech_key`` appears in ``text_key`` as a whole term, plural allowed:
    "apis" in "api design", "jira" in "jira, confluence", "claude" in
    "claude- and openai-based"; "c" is not in "c#" and "java" not in "javascript"."""
    stem = tech_key[:-1] if tech_key.endswith("s") and len(tech_key) > 3 else tech_key
    pattern = r"(?<![\w#+.])" + re.escape(stem) + r"s?(?![\w#+])"
    return re.search(pattern, text_key) is not None


def absorbed_technologies(offer: dict[str, Any]) -> set[str]:
    """Row keys of the ``technologies`` items a required or preferred skill
    item already names: they get no row of their own."""
    skills = [row_key(i) for key in SKILL_LISTS for i in offer.get(key) or [] if isinstance(i, str)]
    out: set[str] = set()
    for item in offer.get("technologies") or []:
        if not isinstance(item, str):
            continue
        k = row_key(item)
        if k and any(s != k and _named_in(k, s) for s in skills):
            out.add(k)
    return out


def expected_rows(offer: dict[str, Any]) -> list[dict[str, str]]:
    """``[{requirement, category}]`` - the rows a match analysis must have."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set(absorbed_technologies(offer))
    for key, category in LISTS:
        for item in offer.get(key) or []:
            if not isinstance(item, str):
                continue
            k = row_key(item)
            if not k or k in seen:
                continue
            seen.add(k)
            rows.append({"requirement": item.strip(), "category": category})
    return rows


def coverage_problems(offer: dict[str, Any], matches: list[dict[str, Any]]) -> list[str]:
    """Differences between the match rows and ``expected_rows(offer)``."""
    expected = {row_key(r["requirement"]): r for r in expected_rows(offer)}
    problems: list[str] = []
    found: dict[str, int] = {}
    for i, m in enumerate(matches):
        req = m.get("requirement", "")
        k = row_key(req)
        if k not in expected:
            problems.append(f"matches[{i}] '{req}' is not an item of the offer analysis - remove it, or use "
                            f"the item's exact text (rows come from required_skills, preferred_skills, "
                            f"technologies and responsibilities)")
            continue
        if k in found:
            problems.append(f"matches[{i}] '{req}' duplicates matches[{found[k]}] - one row per offer item")
            continue
        found[k] = i
        want = expected[k]["category"]
        if m.get("category") != want:
            problems.append(f"matches[{i}] '{req}' has category '{m.get('category')}', expected '{want}' "
                            f"(the offer list it comes from)")
    for k, r in expected.items():
        if k not in found:
            problems.append(f"no row for offer item '{r['requirement']}' ({r['category']}) - add it")
    return problems
