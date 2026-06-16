"""Shared helpers for grounding checks in both flows.

Used by:
- check_role_grounding.py (cold flow — guards Step 4 emphasis_areas / rationale)
- check_match_grounding.py (offer flow — guards Step 4 match_analysis direct claims)

The synonym map and tokenizer live here so the two checks can never drift —
adding a synonym to one must benefit the other.
"""
from __future__ import annotations

import re

# Canonical form -> list of accepted forms (all lowercase). Keep narrow;
# extend on real violations rather than front-loading speculative aliases.
SYNONYMS: dict[str, list[str]] = {
    ".net": [".net", "dotnet", ".net framework"],
    ".net core": [".net core", "dotnetcore", "dotnet core", "netcore"],
    "c#": ["c#", "csharp", "c sharp", "c-sharp"],
    "asp.net": ["asp.net", "asp .net", "asp-net"],
    "asp.net mvc": ["asp.net mvc", "asp .net mvc", "aspnet mvc"],
    "winforms": ["winforms", "windows forms", "win forms"],
    "entity framework": ["entity framework", "ef core", "entityframework"],
    "sql server": ["sql server", "mssql", "ms sql server", "ms-sql"],
    "javascript": ["javascript"],
    "typescript": ["typescript"],
}


_SEPARATORS = re.compile(
    r"[/,;&|·]|\s+et\s+|\s+and\s+|\s+à\s+|→|\bvs\b|\s+[–-]\s+",
    re.IGNORECASE,
)
# Brackets are treated as separators so parenthetical sub-lists / version
# ranges become their own tokens, e.g. "SQL avancé (PostgreSQL, SQL Server)"
# -> "SQL avancé", "PostgreSQL", "SQL Server".
_BRACKETS = re.compile(r"[()\[\]{}]")
# A token that is purely a version / number (e.g. "3.5", "v4", "2022", "3.5 4.8")
# carries no tech identity on its own and must not be flagged.
_PURE_VERSION = re.compile(r"^v?\d+(?:\.\d+)*(?:\s+v?\d+(?:\.\d+)*)*$")


def canonical(token: str) -> str:
    """Return canonical form of a token. Lowercase, trimmed, with synonyms collapsed."""
    n = token.strip().lower().strip(".,;:()[]{}'\"«»“”")
    n = re.sub(r"\s+", " ", n)
    for canon, aliases in SYNONYMS.items():
        if n in aliases:
            return canon
    return n


def _alias_boundary(alias: str) -> re.Pattern:
    """Word-bounded matcher for a synonym alias, tolerant of tech chars (#, ., +)."""
    return re.compile(r"(?<![\w#.+])" + re.escape(alias) + r"(?![\w#.+])", re.IGNORECASE)


def _explode_compound(token: str) -> list[str]:
    """If a multi-word token CONTAINS one or more known synonym aliases as
    word-bounded substrings (but is not itself a known tech), return those
    aliases so each grounds independently. Otherwise return [] (keep as-is)."""
    if canonical(token) in SYNONYMS:        # token IS a known tech — keep whole
        return []
    if len(token.split()) < 2:              # single word — nothing to explode
        return []
    found: list[str] = []
    for canon, aliases in SYNONYMS.items():
        for alias in aliases:
            if _alias_boundary(alias).search(token):
                found.append(canon)
                break
    return found


def split_tokens(text: str) -> list[str]:
    """Split a phrase like 'C# / .NET / WPF' into individual tokens.

    Beyond the coarse separators, this also: turns brackets into separators so
    parenthetical sub-lists split out; drops pure version/number tokens; and
    explodes space-joined compounds that embed a known synonym alias (e.g.
    'C# .NET Framework' -> 'c#', '.net framework') so each grounds on its own.
    """
    coarse = _SEPARATORS.split(_BRACKETS.sub(",", text))
    out: list[str] = []
    for part in coarse:
        tok = part.strip()
        if not tok or _PURE_VERSION.fullmatch(tok):
            continue
        exploded = _explode_compound(tok)
        out.extend(exploded if exploded else [tok])
    # de-duplicate, preserving order (case-insensitive)
    seen: set[str] = set()
    result: list[str] = []
    for tok in out:
        key = tok.lower()
        if key not in seen:
            seen.add(key)
            result.append(tok)
    return result


def tech_in_text(canon: str, text_lower: str) -> bool:
    """Word-bounded search of any synonym alias in lowercased text."""
    aliases = SYNONYMS.get(canon, [canon])
    for alias in aliases:
        pattern = r"(?<![\w])" + re.escape(alias) + r"(?![\w])"
        if re.search(pattern, text_lower):
            return True
    return False


def extract_candidate_vocab(fact_base: dict) -> tuple[set[str], str]:
    """Build candidate's grounded vocabulary from the fact base.

    Returns (canonical-form set, lowercased prose blob).

    The set covers explicit array fields (technologies / skills / methodologies
    / addendum_hidden_skills); the prose blob covers what's only mentioned
    inside experience details, summary, and addendum off-CV facts. A claim is
    grounded if it's in either.
    """
    vocab: set[str] = set()
    for field in ("technologies", "skills", "methodologies"):
        for item in fact_base.get(field, []) or []:
            vocab.add(canonical(item))
    for item in fact_base.get("addendum_hidden_skills", []) or []:
        vocab.add(canonical(item))

    prose_parts: list[str] = []
    if fact_base.get("summary"):
        prose_parts.append(fact_base["summary"])
    for exp in fact_base.get("experience", []) or []:
        for detail in exp.get("details", []) or []:
            prose_parts.append(detail)
    for item in fact_base.get("addendum_off_cv_facts", []) or []:
        prose_parts.append(item)
    for item in fact_base.get("addendum_hidden_skills", []) or []:
        prose_parts.append(item)
    prose = " | ".join(prose_parts).lower()
    return vocab, prose


# Trailing version suffixes: " 4.8", " 2022", " v3", " 8.0" — strip so a tech
# claimed at version X is grounded by the same tech (any version) in fact base.
_VERSION_SUFFIX = re.compile(r"\s+v?\d+(\.\d+)*$|\s+\d{4}$")


def strip_version(canon: str) -> str:
    return _VERSION_SUFFIX.sub("", canon).strip()


def candidate_has(canon: str, vocab: set[str], prose: str) -> bool:
    """True iff the canonical token (or its version-stripped form) appears
    in the vocab set or in the prose blob."""
    if canon in vocab or tech_in_text(canon, prose):
        return True
    base = strip_version(canon)
    if base != canon and (base in vocab or tech_in_text(base, prose)):
        return True
    return False


# Tech-shape detection: distinguish "C# / .NET / Kubernetes" from
# "Maintenance applicative / Amélioration continue". Used only by the
# offer-flow check; cold-prospect's `tech_stack_hints` is curated by the
# research step and is already tech-only, so no shape gate is needed there.
_ALL_CAPS_ACRONYM = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")
_CAMEL_CASE = re.compile(r"[a-z][A-Z]")


def is_tech_shaped(token: str) -> bool:
    """Heuristic: does this token look like a technology, framework, or library name?

    Returns True when:
    - The token (after canonicalisation) is in the SYNONYMS map.
    - The token contains a tech-typical character: '.', '#', '/', '+'.
    - The token is an all-caps acronym of 2–8 chars (e.g. WPF, REST, SQL).
    - The token is CamelCase (e.g. MongoDB, TypeScript).

    Intentionally returns False for plain-word phrases ("Maintenance applicative",
    "Debugging", "Amélioration continue"). The offer flow uses this to scope
    its blocking check to tech tokens — soft-skill direct-match issues become
    warnings, not blockers.
    """
    s = token.strip()
    if not s:
        return False
    if canonical(s) in SYNONYMS:
        return True
    if any(c in s for c in ".#/+"):
        return True
    if _ALL_CAPS_ACRONYM.fullmatch(s):
        return True
    if _CAMEL_CASE.search(s):
        return True
    return False


def snippet_around(text: str, canon: str, span: int = 30) -> str:
    """Return a short context excerpt around the first match of `canon` in `text`."""
    text_l = text.lower()
    for alias in SYNONYMS.get(canon, [canon]):
        m = re.search(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", text_l)
        if m:
            start = max(0, m.start() - span)
            end = min(len(text), m.end() + span)
            return "…" + text[start:end] + "…"
    return ""
