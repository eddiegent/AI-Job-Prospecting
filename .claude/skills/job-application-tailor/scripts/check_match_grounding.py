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
import sys
from pathlib import Path

try:
    from scripts._grounding_common import (
        candidate_has,
        canonical,
        extract_candidate_vocab,
        is_tech_shaped,
        split_tokens,
    )
except ImportError:
    from _grounding_common import (  # type: ignore
        candidate_has,
        canonical,
        extract_candidate_vocab,
        is_tech_shaped,
        split_tokens,
    )


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
        for token in split_tokens(item):
            canon = canonical(token)
            if canon and len(canon) >= 2:
                tech_only.add(canon)

    wider: set[str] = set(tech_only)
    for field in ("required_skills", "preferred_skills", "ats_keywords"):
        for item in offer.get(field, []) or []:
            for token in split_tokens(item):
                canon = canonical(token)
                if canon and len(canon) >= 2:
                    wider.add(canon)
    return tech_only, wider


def _check_direct_matches(
    matches: list[dict],
    tech_only: set[str],
    wider: set[str],
    vocab: set[str],
    prose: str,
) -> tuple[list[tuple[int, str, list[str]]], list[tuple[int, str, list[str]]]]:
    """Split direct-match issues into (errors, warnings).

    - **Errors**: tech-shaped tokens (e.g. C#, .NET, Kubernetes, MongoDB) that
      are in the JD and absent from fact base — block the pipeline.
    - **Warnings**: non-tech-shaped tokens (soft skills, French/English phrases
      like "Maintenance applicative") — surface for review, do not block.
      Cross-language matching of soft skills against the fact base is too
      unreliable to use as a blocking gate.
    """
    errors: list[tuple[int, str, list[str]]] = []
    warns: list[tuple[int, str, list[str]]] = []
    for i, m in enumerate(matches):
        if m.get("match_type") != "direct":
            continue
        requirement = m.get("requirement", "")
        ungrounded_tech: list[str] = []
        ungrounded_soft: list[str] = []
        for tok in split_tokens(requirement):
            canon = canonical(tok)
            if canon not in wider:
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


def check(
    match_file: Path,
    offer_file: Path,
    fact_base_file: Path,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    match_analysis = json.loads(match_file.read_text(encoding="utf-8"))
    offer = json.loads(offer_file.read_text(encoding="utf-8"))
    fact_base = json.loads(fact_base_file.read_text(encoding="utf-8"))

    tech_only, wider = _extract_universes(offer)
    vocab, prose = extract_candidate_vocab(fact_base)
    matches = match_analysis.get("matches", []) or []

    direct_errors, direct_warns = _check_direct_matches(matches, tech_only, wider, vocab, prose)

    errors: list[str] = []
    for i, requirement, ungrounded in direct_errors:
        joined = ", ".join(repr(t) for t in ungrounded)
        errors.append(
            f"  - matches[{i}] '{requirement}' marked direct but tech token(s) {joined} "
            "are listed in the job offer and absent from cv_fact_base"
        )

    warnings: list[str] = []
    for i, requirement, ungrounded in direct_warns:
        joined = ", ".join(repr(t) for t in ungrounded)
        warnings.append(
            f"  - matches[{i}] '{requirement}' marked direct — soft-skill token(s) {joined} "
            "not literally found in cv_fact_base; review evidence or downgrade to transferable"
        )
    for i, requirement in _check_transferable_notes(matches):
        warnings.append(
            f"  - matches[{i}] '{requirement}' marked transferable but has empty `notes` and `evidence` "
            "— transferable claims must be explained"
        )

    return errors, warnings


def main() -> None:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

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
