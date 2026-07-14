"""Pipeline-support commands that replace the inline `python -c` blobs the
SKILL.md / commands.md docs used to carry: URL probing, raw-offer caching,
platform detection, the two folder renames, the forbidden-title-label check,
and the CV fact-base cache save.

None of these touch the history DB (needs_db=False), so `main()` never opens
or creates a DB file for them.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from scripts.commands import Command
from scripts.common import (
    matched_aggregator,
    rename_cold_folder_with_canonical_name,
    rename_folder_with_fit,
    save_cv_fact_base,
)
from scripts.paths import load_settings, resolve_user_data_dir
from scripts.user_customization import (
    find_forbidden_title_label_violations,
    load_customization_context,
)


def _prep_dir(target: str) -> Path:
    """Accept an output folder or its _prep/ subfolder; return the _prep dir."""
    p = Path(target)
    if p.name != "_prep":
        p = p / "_prep"
    if not p.is_dir():
        print(f"No _prep/ directory at {p}", file=sys.stderr)
        sys.exit(2)
    return p


def _load_prep_json(prep: Path, name: str) -> dict:
    path = prep / name
    if not path.exists():
        print(f"Missing {path} — run the step that produces it first", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------- probe-url

def cmd_probe_url(db, args: argparse.Namespace) -> None:
    """HEAD-probe an offer URL so a blocked aggregator fails fast.

    Prints exactly one line: OK, BLOCKED <code>, OTHER_HTTP <code>, or
    OTHER_ERROR <type>: <msg>. Always exits 0 — the caller branches on the
    printed verdict, and an unreachable host is information, not an error.
    """
    req = urllib.request.Request(
        args.url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        print("OK")
    except urllib.error.HTTPError as e:
        print(f"BLOCKED {e.code}" if e.code in (401, 403, 429, 451) else f"OTHER_HTTP {e.code}")
    except Exception as e:  # DNS, TLS, proxy, timeout — inconclusive
        print(f"OTHER_ERROR {type(e).__name__}: {e}")


def _configure_probe_url(p: argparse.ArgumentParser) -> None:
    p.add_argument("url", help="Job-offer URL to probe with a HEAD request")


# ----------------------------------------------------------- cache-raw-offer

def cmd_cache_raw_offer(db, args: argparse.Namespace) -> None:
    """Write stdin verbatim to <prep>/raw_offer.md (audit snapshot)."""
    prep = _prep_dir(args.target)
    text = sys.stdin.read()
    if not text.strip():
        print("stdin was empty — nothing cached", file=sys.stderr)
        sys.exit(2)
    out = prep / "raw_offer.md"
    out.write_text(text, encoding="utf-8")
    print(f"Cached raw offer -> {out}")


def _configure_cache_raw_offer(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Output folder for this run (or its _prep/ subfolder)")


# ----------------------------------------------------------- detect-platform

def cmd_detect_platform(db, args: argparse.Namespace) -> None:
    """Print the aggregator platform matching the offer's company_name, or nothing."""
    prep = _prep_dir(args.target)
    job = _load_prep_json(prep, "job_offer_analysis.json")
    platforms = load_settings().get("aggregators", {}).get("known_platforms", [])
    hit = matched_aggregator(job.get("company_name", ""), platforms)
    print(hit or "")


def _configure_detect_platform(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Output folder for this run (or its _prep/ subfolder)")


# ------------------------------------------------------------ rename-with-fit

def cmd_rename_with_fit(db, args: argparse.Namespace) -> None:
    """Offer-flow Step 4 rename: add the fit prefix and rebuild the slug.

    Reads overall_fit_pct from _prep/match_analysis.json and job_title /
    company_name from _prep/job_offer_analysis.json, then prints the new
    folder path (the caller reassigns $OUTPUT_DIR / $PREP_DIR from it).
    """
    folder = Path(args.target)
    prep = _prep_dir(args.target)
    match = _load_prep_json(prep, "match_analysis.json")
    job = _load_prep_json(prep, "job_offer_analysis.json")
    try:
        pct = match["match_summary"]["overall_fit_pct"]
    except KeyError:
        print("match_analysis.json has no match_summary.overall_fit_pct", file=sys.stderr)
        sys.exit(2)
    if folder.name == "_prep":
        folder = folder.parent
    new_path = rename_folder_with_fit(
        folder, pct, job_title=job.get("job_title"), company=job.get("company_name")
    )
    print(new_path)


def _configure_rename_with_fit(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Output folder for this run")


# --------------------------------------------------------- rename-cold-folder

def cmd_rename_cold_folder(db, args: argparse.Namespace) -> None:
    """Cold-flow Step 3 rename: rebuild the slug from the canonical company name.

    Idempotent — prints the same path back when the slug already matches.
    Exits 1 if the target folder already exists (a previous pack for the same
    company); the caller surfaces that to the user.
    """
    folder = Path(args.target)
    if folder.name == "_prep":
        folder = folder.parent
    prep = _prep_dir(args.target)
    profile = _load_prep_json(prep, "company_profile.json")
    name = profile.get("company_name", "")
    if not name:
        print("company_profile.json has no company_name", file=sys.stderr)
        sys.exit(2)
    try:
        new_path = rename_cold_folder_with_canonical_name(folder, name)
    except FileExistsError as exc:
        print(f"Target folder already exists: {exc}", file=sys.stderr)
        sys.exit(1)
    print(new_path)


def _configure_rename_cold_folder(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Cold-flow output folder for this run")


# ----------------------------------------------------- check-forbidden-labels

def cmd_check_forbidden_labels(db, args: argparse.Namespace) -> None:
    """Check a generated JSON against user_prefs.forbidden_title_labels.

    Accepts a tailored_cv.json, role_candidates.json, or selected_role.json
    and checks every title in it. Exits 1 with one line per violation, 0 when
    clean. Prefs load from the resolved user data dir — no label list is
    spliced in from the conversation (this replaces the fragile
    $FORBIDDEN_LABELS_PYTHON_LIST templating in the cold flow).
    """
    path = Path(args.json_file)
    if not path.exists():
        print(f"No such file: {path}", file=sys.stderr)
        sys.exit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    prefs = load_customization_context(resolve_user_data_dir())["prefs"]

    violations: list[str] = []
    if "candidates" in data:  # role_candidates.json
        for i, cand in enumerate(data.get("candidates", [])):
            hits = find_forbidden_title_label_violations({"title": cand.get("title", "")}, prefs)
            violations.extend(f"candidates[{i}]: {v}" for v in hits)
    else:  # tailored_cv.json or selected_role.json — both carry a title field
        violations.extend(find_forbidden_title_label_violations(data, prefs))

    if violations:
        for v in violations:
            print(f"VIOLATION: {v}")
        sys.exit(1)
    print("OK — no forbidden title labels")


def _configure_check_forbidden_labels(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "json_file",
        help="tailored_cv.json, role_candidates.json, or selected_role.json to check",
    )


# --------------------------------------------------------------- save-cv-cache

def cmd_save_cv_cache(db, args: argparse.Namespace) -> None:
    """Save <prep>/cv_fact_base.json as the shared cache + refresh .cv_hash.

    Runs the metric-drift consistency guard first (save_cv_fact_base raises on
    drift), so a stale fact base can never be re-blessed. Exits 1 on drift.
    """
    cv = Path(args.cv) if args.cv else resolve_user_data_dir() / "MASTER_CV.docx"
    if not cv.exists():
        print(f"Master CV not found: {cv}", file=sys.stderr)
        sys.exit(2)
    prep = _prep_dir(args.target)
    try:
        save_cv_fact_base(cv, prep)
    except RuntimeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Saved fact-base cache from {prep / 'cv_fact_base.json'}")


def _configure_save_cv_cache(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Output folder (or _prep/) holding the freshly extracted cv_fact_base.json")
    p.add_argument("--cv", help="Master CV path (default: <user-data-dir>/MASTER_CV.docx)")


COMMANDS = [
    Command("probe-url",
            help="HEAD-probe an offer URL before WebFetch (prints OK / BLOCKED <code> / OTHER_*)",
            configure=_configure_probe_url, handler=cmd_probe_url, needs_db=False),
    Command("cache-raw-offer",
            help="Write stdin verbatim to <run>/_prep/raw_offer.md as the audit snapshot",
            configure=_configure_cache_raw_offer, handler=cmd_cache_raw_offer, needs_db=False),
    Command("detect-platform",
            help="Print the known aggregator matching the offer's company_name (empty if none)",
            configure=_configure_detect_platform, handler=cmd_detect_platform, needs_db=False),
    Command("rename-with-fit",
            help="Offer Step 4 — rename the run folder with the fit prefix + rebuilt slug; prints the new path",
            configure=_configure_rename_with_fit, handler=cmd_rename_with_fit, needs_db=False),
    Command("rename-cold-folder",
            help="Cold Step 3 — rename the run folder from company_profile.company_name; prints the new path",
            configure=_configure_rename_cold_folder, handler=cmd_rename_cold_folder, needs_db=False),
    Command("check-forbidden-labels",
            help="Check titles in a generated JSON against user_prefs.forbidden_title_labels (exit 1 on violation)",
            configure=_configure_check_forbidden_labels, handler=cmd_check_forbidden_labels, needs_db=False),
    Command("save-cv-cache",
            help="Save _prep/cv_fact_base.json as the shared cache (+ .cv_hash) after the drift guard passes",
            configure=_configure_save_cv_cache, handler=cmd_save_cv_cache, needs_db=False),
]
