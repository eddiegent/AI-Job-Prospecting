"""Cold-prospect Step 4 guard: flag company tech_stack_hints that leak into
candidate-side fields (`emphasis_areas`, rationale) without being grounded
in cv_fact_base.

See `_grounding_common.py` for the shared synonym map and tokenizer.

Exit code 0 = clean, exit code 1 = stack-mirroring detected.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

try:
    # Run as module: `python -m scripts.check_role_grounding`
    from scripts._grounding_common import (
        candidate_has,
        canonical,
        extract_candidate_vocab,
        snippet_around,
        split_tokens,
        tech_in_text,
    )
except ImportError:
    # Run as script: `python scripts/check_role_grounding.py`
    from _grounding_common import (  # type: ignore
        candidate_has,
        canonical,
        extract_candidate_vocab,
        snippet_around,
        split_tokens,
        tech_in_text,
    )


def _extract_company_techs(profile: dict) -> set[str]:
    techs: set[str] = set()
    for hint in profile.get("tech_stack_hints", []) or []:
        hint_no_paren = re.sub(r"\([^)]*\)", "", hint)
        for token in split_tokens(hint_no_paren):
            canon = canonical(token)
            if canon and len(canon) >= 2:
                techs.add(canon)
    return techs


def _check_emphasis(
    target: dict, kind: str, company_techs: set[str], vocab: set[str], prose: str
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    items: list[tuple[str, list[str]]] = []
    if kind == "candidates":
        for i, c in enumerate(target.get("candidates", []) or []):
            items.append((f"candidates[{i}].emphasis_areas", c.get("emphasis_areas", []) or []))
    elif kind == "selected":
        items.append(("selected_role.emphasis_areas", target.get("emphasis_areas", []) or []))
    for path, areas in items:
        for area in areas:
            for tok in split_tokens(area):
                canon = canonical(tok)
                if canon in company_techs and not candidate_has(canon, vocab, prose):
                    out.append((path, area, tok))
    return out


def _check_rationale(
    target: dict, kind: str, company_techs: set[str], vocab: set[str], prose: str
) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    rationales: list[tuple[str, str]] = []
    if kind == "candidates":
        for i, c in enumerate(target.get("candidates", []) or []):
            r = c.get("rationale", "")
            if r:
                rationales.append((f"candidates[{i}].rationale", r))
    elif kind == "selected":
        r = target.get("rationale", "")
        if r:
            rationales.append(("selected_role.rationale", r))
    for path, text in rationales:
        text_l = text.lower()
        for canon in company_techs:
            if tech_in_text(canon, text_l) and not candidate_has(canon, vocab, prose):
                out.append((path, snippet_around(text, canon), canon))
    return out


def check(
    role_file: Path,
    kind: str,
    profile_file: Path,
    fact_base_file: Path,
) -> list[str]:
    target = json.loads(role_file.read_text(encoding="utf-8"))
    profile = json.loads(profile_file.read_text(encoding="utf-8"))
    fact_base = json.loads(fact_base_file.read_text(encoding="utf-8"))

    company_techs = _extract_company_techs(profile)
    vocab, prose = extract_candidate_vocab(fact_base)

    issues: list[str] = []
    for path, area, tok in _check_emphasis(target, kind, company_techs, vocab, prose):
        issues.append(
            f"  - [emphasis_areas] {path}: '{tok}' (in '{area}') — listed in company tech_stack_hints, not in cv_fact_base"
        )
    for path, snippet, canon in _check_rationale(target, kind, company_techs, vocab, prose):
        issues.append(
            f"  - [rationale] {path}: '{canon}' mentioned ({snippet}) — listed in company tech_stack_hints, not in cv_fact_base"
        )
    return issues


def main() -> None:
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    parser = argparse.ArgumentParser(
        description=(
            "Cold-prospect grounding check: flag any tech listed in the "
            "company's tech_stack_hints that leaks into the candidate's "
            "emphasis_areas or rationale without being in cv_fact_base."
        )
    )
    parser.add_argument("--target", required=True, help="Path to role_candidates.json or selected_role.json")
    parser.add_argument("--kind", required=True, choices=["candidates", "selected"])
    parser.add_argument("--company-profile", required=True)
    parser.add_argument("--cv-fact-base", required=True, help="Path to cv_fact_base.json (merged form preferred)")
    args = parser.parse_args()

    issues = check(
        role_file=Path(args.target),
        kind=args.kind,
        profile_file=Path(args.company_profile),
        fact_base_file=Path(args.cv_fact_base),
    )

    if issues:
        print(f"STACK-MIRRORING DETECTED — {len(issues)} item(s) listed in company tech_stack_hints but absent from cv_fact_base:")
        for issue in issues:
            print(issue)
        print("\nRemove or replace these claims before continuing.")
        sys.exit(1)
    print("Role grounding OK — no company-stack tech is mirrored into candidate-side fields without grounding in cv_fact_base.")


if __name__ == "__main__":
    main()
