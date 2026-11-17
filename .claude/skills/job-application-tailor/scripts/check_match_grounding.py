"""Offer-flow Step 4 guard: flag `match_analysis.matches` entries marked
`direct` whose tech tokens aren't actually in cv_fact_base.

Failure mode this guards against:
  job_offer_analysis.required_skills lists "Kubernetes" → match_analysis
  marks it `match_type: "direct"` even though the candidate's fact base has
  no Kubernetes evidence → the false-direct count inflates `overall_fit_pct`,
  passes the fit gate, and the tailored CV / letter inherit the unfounded
  claim.

Scope:
- Build a `tech_universe` from `job_offer_analysis.{required_skills,
  preferred_skills, technologies}`. These are the tokens we know are
  technology-shaped — soft-skill phrases like "team leadership" stay out
  of the check because cross-language matching on prose is fragile and
  produces noise.
- For each match where `match_type == "direct"`, tokenize `requirement`
  and find tokens that are in `tech_universe` but not in the candidate's
  vocab/prose. Each is a violation.
- `transferable` matches without explanatory `notes` are warned (not
  blocked) — the prompt already requires the explanation but we surface
  cases where it slipped.

Exit code 0 = clean (or warnings only), exit code 1 = false-direct claims.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct run: make `scripts.*` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._grounding_common import (  # noqa: E402
    candidate_has,
    canonical,
    extract_candidate_vocab,
    is_tech_shaped,
    split_tokens,
    tech_in_text,
)
from scripts.common import force_utf8_stdio  # noqa: E402


def _extract_universes(offer: dict) -> tuple[set[str], set[str]]:
    """Build two token sets from the JD analysis.

    - `tech_only` — tokens drawn solely from `job_offer.technologies`. The
      offer-analysis prompt separates pure tech terms from skills, so any
      token in this field is treated as tech regardless of shape (this is
      how plain-word techs like Kubernetes, Docker, or Redis get caught
      even though they don't have a dot, acronym, or CamelCase signal).
    - `wider` — also includes `required_skills`, `preferred_skills`, and
      `ats_keywords`. Used to scope the check to JD-relevant tokens.
    """
    tech_only: set[str] = set()
    for item in offer.get("technologies", []) or []:
        for token in _tokens(item):
            canon = canonical(token)
            if canon and len(canon) >= 2:
                tech_only.add(canon)

    wider: set[str] = set(tech_only)
    for field in ("required_skills", "preferred_skills", "ats_keywords"):
        for item in offer.get(field, []) or []:
            for token in _tokens(item):
                canon = canonical(token)
                if canon and len(canon) >= 2:
                    wider.add(canon)
    return tech_only, wider


# An alternatives clause: "Make, Zapier, n8n ou équivalents", "PostgreSQL or
# MySQL", "Supabase ou alternatives". Clauses are split on "et" / "and" / ";"
# first, so "C# ou Java, et Kubernetes" still requires Kubernetes.
_CLAUSE = re.compile(r";|\s+et\s+|\s+and\s+", re.IGNORECASE)
_ALTERNATIVES = re.compile(r"\s(?:ou|or)\s|[ée]quivalent", re.IGNORECASE)
_OR = re.compile(r"\s+(?:ou|or)\s+", re.IGNORECASE)
# An explicit marker accepts tools the offer does not name.
_EQUIVALENTS = re.compile(r"[ée]quivalent|alternative|similaire|similar", re.IGNORECASE)
# "équivalents" / "alternatives" name no skill: never a token to ground.
_ALTERNATIVES_MARKER = re.compile(
    r"^(?:d'|des |other |autres? )?(?:[ée]quivalents?|similaires?|similar|alternatives?|autres?|outils similaires)$",
    re.IGNORECASE,
)


# Wording that introduces a skill without being part of its name. Splitting
# "Experience or strong interest in SaaS, cloud platforms" on "or" leaves
# "strong interest in SaaS" as one token; with the lead-in glued on it is
# never found in the fact base, so a well-evidenced row was blocked as a
# false direct (both runs of the 2026-11-17 reproducibility test hit it).
_LEAD_IN = re.compile(
    r"^(?:(?:a|an|une?|very|tres|très|strong|solid|good|deep|bonne|solide|forte?)\s+)*"
    r"(?:interest\s+(?:in|for)|experience\s+(?:in|with|of)|knowledge\s+of|understanding\s+of|"
    r"familiarity\s+with|exposure\s+to|expertise\s+in|"
    r"int[ée]r[êe]t\s+pour|exp[ée]rience\s+(?:en|de|du|des|avec|dans|sur)|"
    r"connaissances?\s+(?:en|de|du|des)|ma[îi]trise\s+(?:de|du|des)|app[ée]tence\s+pour)\s+",
    re.IGNORECASE,
)


def _tokens(text: str) -> list[str]:
    """split_tokens, also splitting on "ou" / "or", without alternatives markers
    or a lead-in ("strong interest in", "maîtrise de") glued to the skill."""
    out = []
    for part in _OR.split(text):
        for t in split_tokens(part):
            if _ALTERNATIVES_MARKER.fullmatch(t.strip()):
                continue
            t = _LEAD_IN.sub("", t.strip())
            if t:
                out.append(t)
    return out


def _is_familiar(canon: str, familiar: list[str]) -> bool:
    text = _dot_norm(canon)
    return any(f and tech_in_text(f, text) for f in familiar)


def _alternatives(
    requirement: str,
    wider: set[str],
    vocab: set[str],
    prose: str,
    familiar: list[str],
) -> tuple[set[str], set[str]]:
    """Canonical tokens of a requirement's alternatives clauses, as
    (covered, open_ended).

    covered: clauses that one member satisfies. "Make, Zapier, n8n ou
    équivalents" asks for one of them, so a grounded Make covers Zapier and
    n8n. The satisfying member must be grounded and not familiar-only - a
    familiar-only skill stays capped at transferable even inside a list.

    open_ended: clauses no named member satisfies but that accept unnamed
    equivalents ("Supabase ou alternatives"). The candidate's equivalent
    cannot be checked by token, so these warn instead of blocking.
    """
    covered: set[str] = set()
    open_ended: set[str] = set()
    for clause in _CLAUSE.split(requirement):
        if not _ALTERNATIVES.search(clause):
            continue
        members = [canonical(t) for t in _tokens(clause)]
        if any(m in wider and candidate_has(m, vocab, prose) and not _is_familiar(m, familiar)
               for m in members):
            covered.update(members)
        elif _EQUIVALENTS.search(clause):
            open_ended.update(members)
    return covered, open_ended


def _check_direct_matches(
    matches: list[dict],
    tech_only: set[str],
    wider: set[str],
    vocab: set[str],
    prose: str,
    covered: list[set[str]] | None = None,
) -> tuple[list[tuple[int, str, list[str]]], list[tuple[int, str, list[str]]]]:
    """Split direct-match issues into (errors, warnings).

    - **Errors**: tech-shaped tokens (e.g. C#, .NET, Kubernetes, MongoDB) that
      are in the JD and absent from fact base — block the pipeline.
    - **Warnings**: non-tech-shaped tokens (soft skills, French/English phrases
      like "Maintenance applicative") — surface for review, do not block.
      Cross-language matching of soft skills against the fact base is too
      unreliable to use as a blocking gate.

    ``covered[i]`` holds match i's tokens that an alternatives clause makes
    optional (see ``_alternatives``).
    """
    errors: list[tuple[int, str, list[str]]] = []
    warns: list[tuple[int, str, list[str]]] = []
    for i, m in enumerate(matches):
        if m.get("match_type") != "direct":
            continue
        requirement = m.get("requirement", "")
        optional = covered[i] if covered else set()
        ungrounded_tech: list[str] = []
        ungrounded_soft: list[str] = []
        for tok in _tokens(requirement):
            canon = canonical(tok)
            if canon not in wider or canon in optional:
                continue
            if candidate_has(canon, vocab, prose):
                continue
            if canon in tech_only or is_tech_shaped(tok):
                ungrounded_tech.append(canon)
            else:
                ungrounded_soft.append(canon)
        if ungrounded_tech:
            errors.append((i, requirement, ungrounded_tech))
        if ungrounded_soft:
            warns.append((i, requirement, ungrounded_soft))
    return errors, warns


def _check_transferable_notes(matches: list[dict]) -> list[tuple[int, str]]:
    """Return (index, requirement) for transferable matches without a `notes` explanation."""
    out: list[tuple[int, str]] = []
    for i, m in enumerate(matches):
        if m.get("match_type") != "transferable":
            continue
        if not (m.get("notes") or "").strip() and not (m.get("evidence") or "").strip():
            out.append((i, m.get("requirement", "")))
    return out


def _dot_norm(text: str) -> str:
    """Lowercase and glue a space before a dot ("ASP .Net Core" == "ASP.NET Core")."""
    return re.sub(r"\s+\.", ".", text.lower())


def _familiar_canon(familiar: list[str]) -> list[str]:
    return [canonical(_dot_norm(f)) for f in familiar if len(f.strip()) > 1]


def _check_familiar_directs(
    matches: list[dict],
    familiar: list[str],
    covered: list[set[str]] | None = None,
) -> list[tuple[int, str, list[str]]]:
    """Directs that name a skill the master CV lists as familiar-only.

    Only active for a merged fact base (``claims_guard merge`` adds
    ``familiar_only_skills``). Those skills often also sit in
    ``technologies`` (the extractor reads the whole skills table), so plain
    vocab grounding would accept them — but a "Familier / à approfondir"
    skill is at most ``transferable``, never ``direct``. A familiar-only
    member of an alternatives list that another member satisfies is not the
    skill the match relies on, so it is not flagged.
    """
    fam = _familiar_canon(familiar)
    out: list[tuple[int, str, list[str]]] = []
    for i, m in enumerate(matches):
        if m.get("match_type") != "direct":
            continue
        requirement = m.get("requirement", "")
        req = _dot_norm(requirement)
        optional = covered[i] if covered else set()
        hits = [f for f in fam if f and tech_in_text(f, req)
                and not any(_is_familiar(c, [f]) for c in optional)]
        if hits:
            out.append((i, requirement, hits))
    return out


def _check_unrowed_tech_gaps(
    offer: dict,
    matches: list[dict],
    alternatives: list[tuple[set[str], set[str]]],
    vocab: set[str],
    prose: str,
    familiar: list[str],
) -> list[tuple[str, list[int]]]:
    """Offer technologies the candidate lacks that no `gap` row counts.

    A missing technology folded into a broader `transferable` row ("PostgreSQL,
    Edge Functions, modélisation de données") earns half credit instead of
    counting as a gap, which inflates the fit score. Returns (technology, rows
    that mention it) - an empty list means no row assesses it at all. Skipped:
    technologies the fact base has, familiar-only ones (those are at most
    transferable, not gaps), and members of an alternatives list ("N8N, Make
    ou Zapier") - another member stands in for them.
    """
    out: list[tuple[str, list[int]]] = []
    seen: set[str] = set()
    for tok in (t for item in offer.get("technologies", []) or [] for t in _tokens(item)):
        canon = canonical(tok)
        if len(canon) < 2 or canon in seen:
            continue
        seen.add(canon)
        # "REST" is held when the fact base lists "REST APIs"; "Claude" when it lists "Claude Code".
        held = candidate_has(canon, vocab, prose) or any(tech_in_text(canon, v) for v in vocab)
        if held or _is_familiar(canon, familiar):
            continue
        rows = [i for i, m in enumerate(matches) if tech_in_text(canon, _dot_norm(m.get("requirement", "")))]
        if any(canon in c | o for i in rows for c, o in [alternatives[i]]):
            continue
        if any(matches[i].get("match_type") == "gap" for i in rows):
            continue
        out.append((tok.strip(), rows))
    return out


def check(
    match_file: Path,
    offer_file: Path,
    fact_base_file: Path,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings).

    ``fact_base_file`` may be the plain ``cv_fact_base.json`` or the merged
    ``cv_fact_base_merged.json``; with the merged form, addendum hidden skills
    and off-CV facts ground claims, and ``familiar_only_skills`` block directs.
    """
    match_analysis = json.loads(match_file.read_text(encoding="utf-8"))
    offer = json.loads(offer_file.read_text(encoding="utf-8"))
    fact_base = json.loads(fact_base_file.read_text(encoding="utf-8"))

    tech_only, wider = _extract_universes(offer)
    vocab, prose = extract_candidate_vocab(fact_base)
    matches = match_analysis.get("matches", []) or []
    familiar = fact_base.get("familiar_only_skills") or []
    alternatives = [_alternatives(m.get("requirement", ""), wider, vocab, prose, _familiar_canon(familiar))
                    for m in matches]
    covered = [c for c, _ in alternatives]

    direct_errors, direct_warns = _check_direct_matches(
        matches, tech_only, wider, vocab, prose, [c | o for c, o in alternatives])

    errors: list[str] = []
    for i, requirement, ungrounded in direct_errors:
        joined = ", ".join(repr(t) for t in ungrounded)
        errors.append(
            f"  - matches[{i}] '{requirement}' marked direct but tech token(s) {joined} "
            "are listed in the job offer and absent from cv_fact_base"
        )
    for i, requirement, hits in _check_familiar_directs(matches, familiar, covered):
        joined = ", ".join(repr(t) for t in hits)
        errors.append(
            f"  - matches[{i}] '{requirement}' marked direct but {joined} is familiar-only "
            "in the master CV ('Familier / a approfondir') - at most transferable"
        )

    warnings: list[str] = []
    for i, requirement, ungrounded in direct_warns:
        joined = ", ".join(repr(t) for t in ungrounded)
        warnings.append(
            f"  - matches[{i}] '{requirement}' marked direct — soft-skill token(s) {joined} "
            "not literally found in cv_fact_base; review evidence or downgrade to transferable"
        )
    for i, (m, (_, open_ended)) in enumerate(zip(matches, alternatives)):
        named = sorted(t for t in open_ended if t in wider and not candidate_has(t, vocab, prose))
        if m.get("match_type") == "direct" and named:
            warnings.append(
                f"  - matches[{i}] '{m.get('requirement', '')}' marked direct but none of "
                f"{', '.join(repr(t) for t in named)} is in cv_fact_base - the offer accepts "
                "equivalents, so check the evidence names a genuine one"
            )
    # Blocking since 2026-11-17 (was a warning): with one row per offer item
    # (scripts/match_rows.py) the technology always has its own row, so a
    # missing technology rated anything but `gap` is the half-credit inflation
    # this check exists for.
    for tech, rows in _check_unrowed_tech_gaps(offer, matches, alternatives, vocab, prose,
                                                _familiar_canon(familiar)):
        if rows:
            where = ", ".join(f"matches[{i}] ({matches[i].get('match_type')})" for i in rows)
            errors.append(
                f"  - offer technology '{tech}' is not in cv_fact_base but is rated in {where} with no "
                "`gap` row - rate its own row `gap`"
            )
        else:
            errors.append(
                f"  - offer technology '{tech}' is not in cv_fact_base and no row assesses it - add a `gap` row"
            )
    for i, requirement in _check_transferable_notes(matches):
        warnings.append(
            f"  - matches[{i}] '{requirement}' marked transferable but has empty `notes` and `evidence` "
            "— transferable claims must be explained"
        )

    return errors, warnings


def main() -> None:
    force_utf8_stdio()

    parser = argparse.ArgumentParser(
        description=(
            "Offer-flow grounding check: flag `direct` matches whose tech "
            "tokens come from the job offer but aren't in cv_fact_base."
        )
    )
    parser.add_argument("--match-analysis", required=True)
    parser.add_argument("--job-offer", required=True)
    parser.add_argument("--cv-fact-base", required=True, help="Path to cv_fact_base.json (merged form preferred)")
    args = parser.parse_args()

    errors, warnings = check(
        match_file=Path(args.match_analysis),
        offer_file=Path(args.job_offer),
        fact_base_file=Path(args.cv_fact_base),
    )

    if warnings:
        print(f"WARNING — {len(warnings)} match(es) need review (soft-skill directs without literal grounding, or transferable claims without explanation):")
        for w in warnings:
            print(w)
        print()

    if errors:
        print(f"FALSE-DIRECT MATCHES DETECTED — {len(errors)} match(es) marked direct without grounding in cv_fact_base:")
        for e in errors:
            print(e)
        print(
            "\nDowngrade these to `transferable` (with a concrete explanation in `notes`) "
            "or `gap`, then re-run match analysis. Do not proceed to CV tailoring with false directs."
        )
        sys.exit(1)
    print("Match grounding OK — every `direct` match is grounded in cv_fact_base.")


if __name__ == "__main__":
    main()
