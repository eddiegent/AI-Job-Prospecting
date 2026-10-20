"""`gate <stage> <folder>` — run every deterministic check for one pipeline
stage in a single call.

Each stage replaces a run of separate invocations the skills used to make
(validate.py, verify_fact_base.py, recount_match_summary.py,
check_match_grounding.py, check_role_grounding.py, check-forbidden-labels,
claims_guard.py check). The logic is imported from those modules — nothing
is re-implemented here, and the standalone scripts keep working.

Output: one `[PASS] <check>` / `[FAIL] <check>` line per check, failures
followed by their indented problems, plus non-blocking `[WARN] <check>`
lines. A failed schema check (or a missing input file) stops the stage —
later checks would be meaningless; otherwise every check runs and all
failures are reported together.

Exit codes: 0 all pass, 1 any failure, 2 bad usage (no such folder / no _prep/).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from scripts.commands import Command
from scripts.commands._shared import SKILL_BASE
from scripts.paths import resolve_user_data_dir

TAILOR_SCHEMAS = SKILL_BASE / "schemas"
# The cold skill is a sibling of this one in both the repo layout
# (.claude/skills/<name>/) and the installed-plugin layout (skills/<name>/).
COLD_SCHEMAS = SKILL_BASE.parent / "job-cold-prospect" / "schemas"

MERGED_FACT_BASE = "cv_fact_base_merged.json"
PLAIN_FACT_BASE = "cv_fact_base.json"


@dataclass
class Result:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Ctx:
    prep: Path
    cv: Path

    def path(self, name: str) -> Path:
        return self.prep / name

    def merged_fact_base(self) -> Path:
        """The merged fact base (CV + addendum) that every grounding check uses."""
        return self.prep / MERGED_FACT_BASE


def _need_merged(ctx: Ctx) -> list[str]:
    """Error when `claims_guard.py merge` has not run: grounding against the
    plain fact base would silently ignore the addendum (hidden skills,
    off-CV facts) and the familiar-only cap."""
    if ctx.merged_fact_base().exists():
        return []
    return [f"{MERGED_FACT_BASE} not found in {ctx.prep} - run "
            f'`python scripts/claims_guard.py merge "{ctx.prep}"` first (Step 3.9), then re-run this gate']


def _clean(lines: list[str]) -> list[str]:
    """Strip the '  - ' prefix some checkers bake into their messages."""
    out = []
    for line in lines:
        s = line.strip()
        out.append(s[2:] if s.startswith("- ") else s)
    return out


def _missing(ctx: Ctx, *names: str) -> list[str]:
    return [f"{n} not found in {ctx.prep}" for n in names if not ctx.path(n).exists()]


# ------------------------------------------------------------------ checks

def _schema(filename: str, schema: Path) -> Callable[[Ctx], Result]:
    def run(ctx: Ctx) -> Result:
        from scripts.validate import validate

        r = Result(f"schema {filename}")
        data = ctx.path(filename)
        if not data.exists():
            r.errors.append(f"{filename} not found in {ctx.prep}")
        elif not schema.exists():
            r.errors.append(f"schema file not found: {schema}")
        else:
            try:
                r.errors.extend(validate(data, schema))
            except json.JSONDecodeError as exc:
                r.errors.append(f"invalid JSON: {exc}")
        return r
    run.label = f"schema {filename}"
    return run


def _verify_fact_base(ctx: Ctx) -> Result:
    from scripts.verify_fact_base import verify

    r = Result("verify fact base vs master CV")
    if not ctx.cv.exists():
        r.errors.append(f"master CV not found: {ctx.cv}")
        return r
    errors, warnings = verify(ctx.cv, ctx.path(PLAIN_FACT_BASE))
    r.errors.extend(errors)
    r.warnings.extend(warnings)
    if any(e.startswith("[metric]") for e in errors):
        r.errors.append("a [metric] item means a figure drifted from the CV - re-extract; "
                        "do not refresh .cv_hash by hand")
    return r


def _recount_match(ctx: Ctx) -> Result:
    from scripts.common import recount_match_summary

    r = Result("recount match_summary")
    target = ctx.path("match_analysis.json")
    if not target.exists():
        r.errors.append(f"match_analysis.json not found in {ctx.prep}")
        return r
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        r.errors.append(f"invalid JSON: {exc}")
        return r
    matches = data.get("matches", [])
    if not isinstance(matches, list):
        r.errors.append("matches must be an array")
        return r
    correct = recount_match_summary(matches)
    current = data.get("match_summary")
    if current == correct:
        r.note = "unchanged"
    else:
        data["match_summary"] = correct
        with target.open("w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        r.note = f"updated {current} -> {correct}"
    return r


def _match_grounding(ctx: Ctx) -> Result:
    from scripts.check_match_grounding import check

    fb = ctx.merged_fact_base()
    r = Result(f"match grounding (vs {fb.name})")
    r.errors = _need_merged(ctx) + _missing(ctx, "job_offer_analysis.json")
    if r.errors:
        return r
    errors, warnings = check(ctx.path("match_analysis.json"), ctx.path("job_offer_analysis.json"), fb)
    r.errors, r.warnings = _clean(errors), _clean(warnings)
    return r


def _forbidden_labels(filename: str) -> Callable[[Ctx], Result]:
    def run(ctx: Ctx) -> Result:
        from scripts.commands.pipeline import forbidden_label_violations

        r = Result(f"forbidden title labels in {filename}")
        data = json.loads(ctx.path(filename).read_text(encoding="utf-8"))
        r.errors = forbidden_label_violations(data)
        return r
    run.label = f"forbidden title labels in {filename}"
    return run


def _claims(*filenames: str) -> Callable[[Ctx], Result]:
    """Claims check scoped to this stage's own files, so a gate never fails on
    another stage's output (the CV and letter subagents run in parallel)."""
    label = f"claims check ({', '.join(filenames)})"

    def run(ctx: Ctx) -> Result:
        from scripts.claims_guard import run_check

        r = Result(label)
        if not ctx.cv.exists():
            r.errors.append(f"master CV not found: {ctx.cv}")
            return r
        r.errors = run_check(ctx.prep, master=ctx.cv, only=filenames)
        return r
    run.label = label
    return run


# LinkedIn limits. A connection note over 300 characters is silently truncated
# by LinkedIn; the cold prompt caps the post-acceptance message at 700. Offer-
# flow messages have no template type, so only the prompt's soft 500 applies.
CONNECTION_REQUEST_MAX = 300
DIRECT_MESSAGE_MAX = 700
SOFT_MESSAGE_MAX = 500


def _linkedin_lengths(ctx: Ctx) -> Result:
    r = Result("linkedin message lengths")
    data = json.loads(ctx.path("linkedin.json").read_text(encoding="utf-8"))
    for i, v in enumerate(data.get("variants", [])):
        msg = v.get("message", "")
        hint = (v.get("subject_hint") or "").strip().lower()
        who = v.get("contact_name") or v.get("target", "?")
        if hint.startswith("connection request"):
            limit, kind = CONNECTION_REQUEST_MAX, "connection request"
        elif hint.startswith("direct message"):
            limit, kind = DIRECT_MESSAGE_MAX, "direct message"
        else:
            if len(msg) > SOFT_MESSAGE_MAX:
                r.warnings.append(f"variants[{i}] ({who}): {len(msg)} characters - "
                                  f"the prompt prefers at most {SOFT_MESSAGE_MAX}")
            continue
        if len(msg) > limit:
            r.errors.append(f"variants[{i}] ({who}, {kind}): {len(msg)} characters, limit {limit} - "
                            f"cut {len(msg) - limit}")
    return r


def _role_grounding(filename: str, kind: str) -> Callable[[Ctx], Result]:
    def run(ctx: Ctx) -> Result:
        from scripts.check_role_grounding import check

        fb = ctx.merged_fact_base()
        r = Result(f"role grounding --kind {kind} (vs {fb.name})")
        r.errors = _need_merged(ctx) + _missing(ctx, "company_profile.json")
        if r.errors:
            return r
        r.errors = _clean(check(ctx.path(filename), kind, ctx.path("company_profile.json"), fb))
        return r
    run.label = f"role grounding --kind {kind}"
    return run


# A stage is a list of (check, stop_on_failure). Schema checks stop the stage.
Step = tuple[Callable[[Ctx], Result], bool]

STAGES: dict[str, list[Step]] = {
    "factbase": [
        (_schema(PLAIN_FACT_BASE, TAILOR_SCHEMAS / "cv_fact_base.schema.json"), True),
        (_verify_fact_base, False),
    ],
    "offer": [
        (_schema("job_offer_analysis.json", TAILOR_SCHEMAS / "job_offer_analysis.schema.json"), True),
    ],
    "match": [
        (_recount_match, True),
        (_schema("match_analysis.json", TAILOR_SCHEMAS / "match_analysis.schema.json"), True),
        (_match_grounding, False),
    ],
    "cv": [
        (_schema("tailored_cv.json", TAILOR_SCHEMAS / "tailored_cv.schema.json"), True),
        (_forbidden_labels("tailored_cv.json"), False),
        (_claims("tailored_cv.json"), False),
    ],
    "letters": [
        (_schema("letter.json", TAILOR_SCHEMAS / "letter.schema.json"), True),
        (_schema("short_letter.json", TAILOR_SCHEMAS / "letter.schema.json"), True),
        (_claims("letter.json", "short_letter.json"), False),
    ],
    "linkedin": [
        (_schema("linkedin.json", TAILOR_SCHEMAS / "linkedin.schema.json"), True),
        (_linkedin_lengths, False),
        (_claims("linkedin.json"), False),
    ],
    "profile": [
        (_schema("company_profile.json", COLD_SCHEMAS / "company_profile.schema.json"), True),
    ],
    "roles": [
        (_schema("role_candidates.json", COLD_SCHEMAS / "role_candidates.schema.json"), True),
        (_forbidden_labels("role_candidates.json"), False),
        (_role_grounding("role_candidates.json", "candidates"), False),
    ],
    "selected-role": [
        (_schema("selected_role.json", COLD_SCHEMAS / "selected_role.schema.json"), True),
        (_role_grounding("selected_role.json", "selected"), False),
    ],
}


def run_stage(stage: str, ctx: Ctx) -> int:
    """Run one stage, print the report, return the exit code (0 pass / 1 fail)."""
    print(f"gate {stage}: {ctx.prep}")
    failed = 0
    ran = 0
    for check, stop_on_failure in STAGES[stage]:
        ran += 1
        try:
            r = check(ctx)
        except Exception as exc:  # a crashing checker is a failed check, not a traceback
            label = getattr(check, "label", check.__name__.strip("_").replace("_", " "))
            r = Result(label, errors=[f"{type(exc).__name__}: {exc}"])
        if r.errors:
            failed += 1
            print(f"[FAIL] {r.name}")
            for e in r.errors:
                print(f"    - {e}")
        else:
            print(f"[PASS] {r.name}" + (f": {r.note}" if r.note else ""))
        if r.warnings:
            print(f"[WARN] {r.name} (non-blocking)")
            for w in r.warnings:
                print(f"    - {w}")
        if r.errors and stop_on_failure:
            skipped = len(STAGES[stage]) - ran
            if skipped:
                print(f"(stopped: {skipped} later check(s) skipped until this passes)")
            break
    if failed:
        print(f"gate {stage}: FAIL ({failed} check(s) failed)")
        return 1
    print(f"gate {stage}: PASS")
    return 0


def cmd_gate(db, args: argparse.Namespace) -> None:
    from scripts.commands.pipeline import _prep_dir

    prep = _prep_dir(args.folder)  # exits 2 when there is no _prep/
    cv = Path(args.cv) if args.cv else resolve_user_data_dir() / "MASTER_CV.docx"
    sys.exit(run_stage(args.stage, Ctx(prep=prep, cv=cv)))


def _configure_gate(p: argparse.ArgumentParser) -> None:
    p.description = (
        "Run every deterministic check for one pipeline stage. Stages: "
        "factbase (schema + verify vs master CV), offer (schema), "
        "match (recount in place + schema + grounding), "
        "cv (schema + forbidden labels + claims on tailored_cv.json), letters "
        "(letter + short_letter schemas + claims on those two), linkedin (schema + "
        "message lengths: connection request <= 300, direct message <= 700 + "
        "claims on linkedin.json), profile (cold schema), "
        "roles (cold schema + forbidden labels + role grounding), "
        "selected-role (cold schema + role grounding). Grounding (match, roles, "
        "selected-role) requires cv_fact_base_merged.json - run "
        "`claims_guard.py merge` first. "
        "Exit 0 = all pass, 1 = a check failed, 2 = bad usage."
    )
    p.add_argument("stage", choices=list(STAGES), help="Pipeline stage to check")
    p.add_argument("folder", help="Run output folder (or its _prep/ subfolder)")
    p.add_argument("--cv", help="Master CV path (default: <user-data-dir>/MASTER_CV.docx)")


COMMANDS = [
    Command("gate",
            help="Run all checks for one pipeline stage (schema, grounding, labels, claims) in one call",
            configure=_configure_gate, handler=cmd_gate, needs_db=False),
]
