"""Application-record lifecycle: check-duplicate / regenerate-outputs / record-application / rename-application."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts.common import auto_slug, delete_stale_slug_deliverables, matched_aggregator
from scripts.job_history_db import JobHistoryDB, normalise_title
from scripts.paths import load_settings
from scripts.commands import Command
from scripts.commands._shared import SKILL_BASE


def cmd_check_duplicate(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Step 3.5 wrapper — reads job_offer_analysis.json and runs the three
    history checks (duplicate, same-company context, blacklist) in one call.

    Target may be the `_prep/job_offer_analysis.json` path, or a folder
    containing `_prep/job_offer_analysis.json`, or the JSON file directly.

    Exit codes:
      0 — clean (no blacklist, no duplicate)
      1 — needs attention (duplicate or blacklisted company)
    """
    target = Path(args.target)
    if target.is_dir():
        candidate = target / "_prep" / "job_offer_analysis.json"
        if not candidate.exists():
            candidate = target / "job_offer_analysis.json"
        job_path = candidate
    else:
        job_path = target

    if not job_path.exists():
        print(f"Cannot find job_offer_analysis.json at {job_path}", file=sys.stderr)
        sys.exit(2)

    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Could not parse {job_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    company = (job.get("company_name") or "").strip()
    title = (job.get("job_title") or "").strip()
    source_url = args.url or job.get("source_url")
    required_skills = job.get("required_skills") or []

    blacklist_entry = db.check_company_list(company) if company else None

    dupes = db.find_duplicates(
        company_name=company,
        job_title=title,
        source_url=source_url,
        required_skills=required_skills,
    ) if company and title else []

    same_company = db.find_same_company(company) if company else []
    dupe_ids = {d["id"] for d in dupes}
    context = [c for c in same_company if c["id"] not in dupe_ids]

    if args.json:
        payload = {
            "company_name": company,
            "job_title": title,
            "source_url": source_url,
            "blacklist": blacklist_entry,
            "duplicates": dupes,
            "same_company_context": context,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"Checking: {company} — {title}")
        if source_url:
            print(f"URL: {source_url}")

        if blacklist_entry:
            lt = blacklist_entry["list_type"].upper()
            reason = f" — {blacklist_entry['reason']}" if blacklist_entry.get("reason") else ""
            print(f"\n[!] {lt}: {blacklist_entry['company_name']}{reason}")
        else:
            print("\nBlacklist: not listed")

        if dupes:
            print(f"\n[!] {len(dupes)} duplicate(s) found:")
            for d in dupes:
                fit_level = d.get("fit_level") or "n/a"
                fit_pct = d.get("fit_pct")
                fit_pct_s = f"{fit_pct}%" if fit_pct is not None else "n/a"
                print(f"  #{d['id']} [{fit_level} {fit_pct_s}] — {d['company_name']} / {d['job_title']}")
                print(f"    reason: {d['match_reason']}")
                print(f"    date:   {d['created_at']}")
                folder = d.get("output_folder") or "(none)"
                print(f"    folder: {folder}")
        else:
            print("\nDuplicates: none")

        if context:
            print(f"\nOther applications to {company} ({len(context)}):")
            for c in context:
                fit_level = c.get("fit_level") or "n/a"
                fit_pct = c.get("fit_pct")
                fit_pct_s = f"{fit_pct}%" if fit_pct is not None else "n/a"
                print(f"  #{c['id']} [{fit_level} {fit_pct_s}] — {c['job_title']} ({c['created_at']})")

    flagged = bool(dupes) or (
        blacklist_entry is not None and blacklist_entry.get("list_type") == "blacklist"
    )
    sys.exit(1 if flagged else 0)


def _resolve_app_folder(db: JobHistoryDB, target: str) -> Path:
    """Accept either an integer application id (DB lookup) or a filesystem path."""
    if target.isdigit():
        app = db.get_application(int(target))
        if not app:
            print(f"Application #{target} not found.", file=sys.stderr)
            sys.exit(1)
        folder = Path(app["output_folder"])
    else:
        folder = Path(target)
    if not folder.exists():
        print(f"Output folder does not exist: {folder}", file=sys.stderr)
        sys.exit(1)
    return folder


def cmd_regenerate_outputs(db: JobHistoryDB, args: argparse.Namespace) -> None:
    folder = _resolve_app_folder(db, args.target)
    prep = folder / "_prep"

    required = {
        "tailored_cv.json": prep / "tailored_cv.json",
        "letter.json": prep / "letter.json",
        "linkedin.json": prep / "linkedin.json",
        "interview_prep.md": prep / "interview_prep.md",
        "job_offer_analysis.json": prep / "job_offer_analysis.json",
    }
    optional = {
        "short_letter.json": prep / "short_letter.json",
        "match_analysis.json": prep / "match_analysis.json",
        "company_dossier.md": prep / "company_dossier.md",
    }
    missing = [n for n, p in required.items() if not p.exists()]

    if args.check:
        print(f"Target: {folder}")
        print("Required:")
        for name, p in required.items():
            print(f"  [{'OK' if p.exists() else 'MISSING'}] {name}")
        print("Optional:")
        for name, p in optional.items():
            print(f"  [{'OK' if p.exists() else 'absent'}] {name}")
        sys.exit(1 if missing else 0)

    if missing:
        print(f"Cannot regenerate — missing required _prep/ files: {', '.join(missing)}", file=sys.stderr)
        print("Run with --check for details. Re-run the upstream step(s) before retrying.", file=sys.stderr)
        sys.exit(1)

    job = json.loads(required["job_offer_analysis.json"].read_text(encoding="utf-8"))
    job_title = job.get("job_title") or "Role"
    language = job.get("detected_language") or "fr"

    # Reuse the existing folder slug for filenames so a regenerate run
    # doesn't produce a second set of files under a different slug
    # alongside the originals. The folder slug may differ from
    # `slug_for_filename(job_title)` when the initial run built the slug
    # from `{job_title}-{company}` or applied ASCII folding — we can't
    # reconstruct that choice here, so we just reuse whatever the folder
    # already has. `slug_for_filename` is idempotent on its own output,
    # so filename sanitisation downstream stays a no-op.
    _, existing_slug = _split_folder_prefix(folder.name)
    title_for_filenames = existing_slug or job_title

    cmd = [
        sys.executable,
        str(SKILL_BASE / "scripts" / "generate_outputs.py"),
        "--tailored-cv-json", str(required["tailored_cv.json"]),
        "--letter-json", str(required["letter.json"]),
        "--linkedin-json", str(required["linkedin.json"]),
        "--interview-markdown", str(required["interview_prep.md"]),
        "--output-dir", str(folder),
        "--job-title", title_for_filenames,
        "--settings", str(SKILL_BASE / "config" / "settings.default.yaml"),
        "--naming-rules", str(SKILL_BASE / "config" / "naming_rules.yaml"),
        "--language", language,
    ]
    if optional["short_letter.json"].exists():
        cmd.extend(["--short-letter-json", str(optional["short_letter.json"])])
    if optional["match_analysis.json"].exists():
        cmd.extend(["--match-analysis-json", str(optional["match_analysis.json"])])
    if optional["company_dossier.md"].exists():
        cmd.extend(["--dossier-markdown", str(optional["company_dossier.md"])])
    if args.skip_pdf:
        cmd.append("--skip-pdf")

    print(f"Regenerating outputs for: {folder}")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


_FOLDER_PREFIX_RE = re.compile(r"^((?:very_good|good|medium|low)-\d{8}-)(.+)$")
_DATE_PREFIX_RE = re.compile(r"^(\d{8}-)(.+)$")


def _detect_flow_from_folder(folder: Path) -> str:
    """Folder name prefix encodes the flow: `cold-…` for speculative
    applications, anything else for offer-based runs."""
    return "cold" if folder.name.startswith("cold-") else "offer"


def _derive_fit_level(folder_name: str) -> str:
    for prefix in ("very_good", "good", "medium"):
        if folder_name.startswith(prefix + "-"):
            return prefix
    return "low"


def _build_offer_kwargs(folder: Path, prep: Path, url_override: str | None) -> dict:
    job_path = prep / "job_offer_analysis.json"
    if not job_path.exists():
        print(f"Cannot find _prep/job_offer_analysis.json at {job_path}", file=sys.stderr)
        sys.exit(2)
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Could not parse {job_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    match: dict | None = None
    match_path = prep / "match_analysis.json"
    if match_path.exists():
        try:
            match = json.loads(match_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Could not parse {match_path}: {exc}", file=sys.stderr)
            sys.exit(2)
    ms = (match or {}).get("match_summary", {}) or {}

    return {
        "company_name": job.get("company_name", ""),
        "job_title": job.get("job_title", ""),
        "location": job.get("location"),
        "source_url": url_override or job.get("source_url"),
        "domain": job.get("domain"),
        "seniority": job.get("seniority"),
        "fit_level": _derive_fit_level(folder.name),
        "fit_pct": ms.get("overall_fit_pct"),
        "direct_count": ms.get("direct_count"),
        "transferable_count": ms.get("transferable_count"),
        "gap_count": ms.get("gap_count"),
        "output_folder": str(folder),
        "detected_language": job.get("detected_language"),
        "required_skills": job.get("required_skills") or [],
        "preferred_skills": job.get("preferred_skills") or [],
        "source": "offer",
    }


def _build_cold_kwargs(
    folder: Path,
    prep: Path,
    url_override: str | None,
    language_override: str | None,
) -> dict:
    profile_path = prep / "company_profile.json"
    role_path = prep / "selected_role.json"
    for label, path in (("company_profile.json", profile_path), ("selected_role.json", role_path)):
        if not path.exists():
            print(f"Cannot find _prep/{label} at {path}", file=sys.stderr)
            sys.exit(2)
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        role = json.loads(role_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Could not parse cold-flow JSON: {exc}", file=sys.stderr)
        sys.exit(2)

    snapshot = {
        "company_name": profile.get("company_name", ""),
        "canonical_url": profile.get("canonical_url", ""),
        "industry": profile.get("industry", ""),
        "org_type": profile.get("org_type", ""),
        "size_band": profile.get("size_band", "unknown"),
        "headcount_estimate": profile.get("headcount_estimate"),
        "locations": profile.get("locations", []),
        "mission_statement": profile.get("mission_statement", ""),
        "research_gaps_count": len(profile.get("research_gaps", [])),
    }
    locations = profile.get("locations") or []
    location = locations[0] if locations else None

    return {
        "company_name": profile.get("company_name", ""),
        "job_title": role.get("title", ""),
        "location": location,
        "source_url": url_override or (profile.get("canonical_url") or None),
        "domain": profile.get("industry") or None,
        "seniority": role.get("seniority_band") or None,
        "fit_level": None,
        "fit_pct": None,
        "direct_count": None,
        "transferable_count": None,
        "gap_count": None,
        "output_folder": str(folder),
        # Cold flow has no JD to auto-detect from; default to fr (the
        # cold-flow default) unless the caller passes --language.
        "detected_language": language_override or "fr",
        "required_skills": [],
        "preferred_skills": [],
        "source": "cold",
        # NULL for a profile that couldn't classify — never coerce to a value.
        "org_type": profile.get("org_type") or None,
        "company_profile_snapshot": json.dumps(snapshot, ensure_ascii=False),
    }


def cmd_record_application(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Step 10 wrapper — read `_prep/` artefacts and insert one
    `applications` row. Detects offer vs. cold flow from the folder
    prefix; `--source` overrides if needed."""
    folder = _resolve_app_folder(db, args.target)
    prep = folder / "_prep"
    if not prep.exists():
        print(f"No _prep/ directory under {folder}", file=sys.stderr)
        sys.exit(2)

    source = args.source or _detect_flow_from_folder(folder)
    if source not in ("offer", "cold"):
        print(f"--source must be 'offer' or 'cold', got {source!r}", file=sys.stderr)
        sys.exit(2)

    if source == "offer":
        kwargs = _build_offer_kwargs(folder, prep, args.url)
    else:
        kwargs = _build_cold_kwargs(folder, prep, args.url, args.language)

    if args.dry_run:
        print(json.dumps(kwargs, ensure_ascii=False, indent=2, default=str))
        return

    # Supersede mode (roadmap 3.3): when re-prospecting a company that already
    # has a live pack for the SAME role, mark the prior row(s) `dropped` before
    # inserting, so the pipeline shows one active application per role instead
    # of the parallel #41-vs-#100 rows a second run used to leave behind.
    #
    # Match strictly on the natural key (company + title) — NOT on shared URL or
    # skill overlap the way `find_duplicates` does: a cold pack's canonical_url
    # is the company site, identical across every role, so a URL match would
    # wrongly drop a different role at the same company. A distinct role is a
    # distinct application and must survive.
    superseded: list[dict] = []
    if getattr(args, "supersede", False):
        title_norm = normalise_title(kwargs["job_title"])
        for prior in db.find_same_company(kwargs["company_name"]):
            if prior["status"] == "dropped" or prior["job_title_norm"] != title_norm:
                continue
            db.update_status(prior["id"], "dropped")
            superseded.append(prior)

    app_id = db.add_application(**kwargs)
    for s in superseded:
        print(f"Superseded #{s['id']} ({s['company_name']} — {s['job_title']}, "
              f"was {s['status']}) -> dropped")
    print(f"Recorded application #{app_id}")


def _split_folder_prefix(name: str) -> tuple[str, str]:
    """Split a folder name into ('{fit_level}-{date}-' prefix, slug)."""
    m = _FOLDER_PREFIX_RE.match(name) or _DATE_PREFIX_RE.match(name)
    if m:
        return m.group(1), m.group(2)
    return "", name


def cmd_rename_application(db: JobHistoryDB, args: argparse.Namespace) -> None:
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)

    new_company = args.new_company.strip()
    if not new_company:
        print("--new-company must be non-empty.", file=sys.stderr)
        sys.exit(1)

    old_company = app["company_name"]
    old_folder = Path(app["output_folder"])
    parent = old_folder.parent
    prefix_part, _old_slug = _split_folder_prefix(old_folder.name)

    # Resolve job_title from _prep so the auto-slug keeps the role
    job_title = None
    job_analysis_in_old = old_folder / "_prep" / "job_offer_analysis.json"
    if job_analysis_in_old.exists():
        try:
            job_title = json.loads(
                job_analysis_in_old.read_text(encoding="utf-8")
            ).get("job_title")
        except json.JSONDecodeError:
            pass

    new_slug = args.new_slug.strip() if args.new_slug else auto_slug(job_title, new_company)
    new_folder = parent / f"{prefix_part}{new_slug}"

    # Filesystem rename
    if old_folder == new_folder:
        pass
    elif old_folder.exists():
        if new_folder.exists():
            print(
                f"Target folder already exists: {new_folder}\n"
                "Pick a different --new-slug or move/delete the existing target.",
                file=sys.stderr,
            )
            sys.exit(1)
        try:
            os.rename(old_folder, new_folder)
        except PermissionError as exc:
            print(
                "Cannot rename folder — a file inside is locked by another process.\n"
                f"  {exc}\n"
                "Close any DOCX/PDF that Word/Acrobat may have open from this folder, "
                "then re-run the command.",
                file=sys.stderr,
            )
            sys.exit(1)
        except OSError as exc:
            print(f"Folder rename failed: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Renamed: {old_folder.name} -> {new_folder.name}")
    elif new_folder.exists():
        print(f"Folder already at {new_folder.name}; skipping filesystem rename.")
    else:
        print(
            f"WARNING: output folder is missing on disk: {old_folder}\n"
            "Updating DB only — re-create the folder before regenerating outputs.",
            file=sys.stderr,
        )

    # Patch _prep/job_offer_analysis.json
    new_job_analysis = new_folder / "_prep" / "job_offer_analysis.json"
    if new_job_analysis.exists():
        try:
            data = json.loads(new_job_analysis.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Could not parse {new_job_analysis}: {exc}", file=sys.stderr)
        else:
            data["company_name"] = new_company
            try:
                settings = load_settings()
                platforms = settings.get("aggregators", {}).get("known_platforms", []) or []
                aggregator = matched_aggregator(old_company, platforms)
            except Exception:
                aggregator = None
            if aggregator:
                data["source_platform"] = aggregator
                data["company_is_aggregator"] = False
            new_job_analysis.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Patched {new_job_analysis.relative_to(new_folder)}")

    # Patch run_summary.json paths (round-trip JSON so backslash escaping
    # on Windows doesn't defeat a naive string replace)
    run_summary = new_folder / "run_summary.json"
    if run_summary.exists() and old_folder != new_folder:
        try:
            summary = json.loads(run_summary.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Could not patch {run_summary}: {exc}", file=sys.stderr)
        else:
            old_str = str(old_folder)
            new_str = str(new_folder)
            changed = False
            for key, value in list(summary.items()):
                if isinstance(value, str) and old_str in value:
                    summary[key] = value.replace(old_str, new_str)
                    changed = True
            if changed:
                run_summary.write_text(
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"Patched {run_summary.name}")

    # DB updates
    db.update_company(args.id, new_company)
    db.update_output_folder(args.id, str(new_folder))
    print(f"#{args.id}: company '{old_company}' -> '{new_company}'")
    print(f"#{args.id}: output_folder -> {new_folder}")

    if args.no_regenerate:
        print("Skipping regenerate-outputs (--no-regenerate set).")
        return
    if not new_folder.exists():
        print("Skipping regenerate-outputs (folder missing on disk).")
        return

    # Remove stale old-slug deliverables before regenerating so the folder
    # ends up with one copy of each file, not two.
    removed = delete_stale_slug_deliverables(new_folder, _old_slug, new_slug)
    for name in removed:
        print(f"Removed stale: {name}")

    print("Running regenerate-outputs...")
    cmd_regenerate_outputs(
        db,
        SimpleNamespace(target=str(new_folder), check=False, skip_pdf=False),
    )


def _configure_check_duplicate(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "target",
        help="Path to _prep/job_offer_analysis.json, or a folder containing one",
    )
    p.add_argument("--url", help="Override source URL if missing from the offer JSON")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_regenerate_outputs(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Application id (integer) or path to an output folder")
    p.add_argument("--check", action="store_true", help="Only report which _prep/ files are present or missing")
    p.add_argument("--skip-pdf", action="store_true", help="Skip PDF conversion (DOCX only)")


def _configure_record_application(p: argparse.ArgumentParser) -> None:
    p.add_argument("target", help="Application id (integer) or path to an output folder")
    p.add_argument("--url", help="Override source URL when the offer JSON / profile lacks one")
    p.add_argument(
        "--source",
        choices=["offer", "cold"],
        help="Override the auto-detected flow (default: 'cold' for cold-* folders, 'offer' otherwise)",
    )
    p.add_argument(
        "--language",
        help="Detected language for cold flow (default: 'fr'). Ignored for offer flow — that one reads detected_language from job_offer_analysis.json.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the kwargs that would be inserted, then exit (no DB write)",
    )
    p.add_argument(
        "--supersede",
        action="store_true",
        help="Mark any prior live application to the same company+role as 'dropped' "
        "before recording this one, so a re-prospect doesn't leave a parallel active row",
    )


def _configure_rename_application(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("--new-company", required=True, help="New company name")
    p.add_argument(
        "--new-slug",
        help="Override the auto-derived folder slug (defaults to '{job_title}-{new_company}')",
    )
    p.add_argument(
        "--no-regenerate",
        action="store_true",
        help="Skip the regenerate-outputs step at the end (rename + DB + JSON only)",
    )


COMMANDS = [
    Command('check-duplicate',
            help='Step 3.5 — check duplicate / same-company / blacklist against a job_offer_analysis.json',
            configure=_configure_check_duplicate, handler=cmd_check_duplicate),
    Command('regenerate-outputs',
            help='Rebuild DOCX/PDF/TXT/MD from existing _prep/ JSONs (Step 9 only)',
            configure=_configure_regenerate_outputs, handler=cmd_regenerate_outputs),
    Command('record-application',
            help='Step 10 — read _prep/ artefacts and insert the history row',
            configure=_configure_record_application, handler=cmd_record_application, mutating=True),
    Command('rename-application',
            help='Atomically rename folder + DB + _prep JSON + run_summary; optionally regenerate outputs',
            configure=_configure_rename_application, handler=cmd_rename_application, mutating=True),
]
