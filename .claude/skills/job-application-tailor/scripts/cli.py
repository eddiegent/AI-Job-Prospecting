"""CLI entry point for the job history database.

Usage:
    python scripts/cli.py --db <path> <subcommand> [options]
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from job_history_db import JobHistoryDB


# ---------------------------------------------------------------------------
# Date resolution
# ---------------------------------------------------------------------------

def resolve_since(value: str) -> str:
    """Convert relative date expressions to ISO date strings.

    Accepts: '7d', '30d', 'this-week', 'this-month', or ISO date (2026-03-01).
    """
    today = datetime.now()
    if value.endswith("d") and value[:-1].isdigit():
        dt = today - timedelta(days=int(value[:-1]))
        return dt.strftime("%Y-%m-%d")
    if value == "this-week":
        dt = today - timedelta(days=today.weekday())
        return dt.strftime("%Y-%m-%d")
    if value == "this-month":
        return today.strftime("%Y-%m-01")
    # Assume ISO date
    return value


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _fmt_app(a: dict) -> str:
    fit = a.get("fit_level") or "n/a"
    pct = a.get("fit_pct")
    pct_s = f"{pct:5.1f}%" if pct is not None else "  n/a"
    return f"#{a['id']:<4d} | {a['status']:10s} | {fit:9s} | {pct_s} | {a['company_name']} — {a['job_title']}"


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_list(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    apps = db.list_applications(
        status=args.status,
        company=args.company,
        limit=args.limit,
        since=since,
    )
    if args.json:
        print(json.dumps(apps, ensure_ascii=False, indent=2))
        return
    if not apps:
        print("No applications found.")
        return
    for a in apps:
        print(_fmt_app(a))


def cmd_get(db: JobHistoryDB, args: argparse.Namespace) -> None:
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps(app, ensure_ascii=False, indent=2))
        return
    print(_fmt_app(app))
    skills = db.get_skills(args.id)
    if skills:
        print("\nSkills:")
        for s in skills:
            print(f"  [{s['skill_type']}] {s['skill']}")


def cmd_update_status(db: JobHistoryDB, args: argparse.Namespace) -> None:
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)
    ok = db.update_status(args.id, args.status)
    if ok:
        print(f"#{args.id} {app['company_name']} — {app['job_title']}: {app['status']} -> {args.status}")
    else:
        print("Update failed.", file=sys.stderr)
        sys.exit(1)


def cmd_stats(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    report_type = args.type

    if args.json:
        result = {}
        if report_type in ("all", "status"):
            result["by_status"] = db.stats_by_status(since=since)
        if report_type in ("all", "fit"):
            result["by_fit_level"] = db.stats_by_fit_level(since=since)
        if report_type in ("all", "company"):
            result["by_company"] = db.stats_by_company(since=since)
        if report_type in ("all", "domain"):
            result["by_domain"] = db.stats_by_domain(since=since)
        if report_type in ("all", "skills"):
            result["skill_trends"] = db.skill_gap_trends(limit=15, since=since)
        result["total"] = db.total_count(since=since)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    period = f" (since {since})" if since else ""
    print(f"Total applications: {db.total_count(since=since)}{period}")

    if report_type in ("all", "status"):
        print("\n--- By Status ---")
        for r in db.stats_by_status(since=since):
            print(f"  {r['status']:12s} {r['count']}")

    if report_type in ("all", "fit"):
        print("\n--- By Fit Level ---")
        for r in db.stats_by_fit_level(since=since):
            lvl = r["fit_level"] or "n/a"
            print(f"  {lvl:12s} {r['count']}")

    if report_type in ("all", "company"):
        print("\n--- By Company ---")
        for r in db.stats_by_company(since=since):
            print(f"  {r['company_name']:30s} {r['count']}")

    if report_type in ("all", "domain"):
        print("\n--- By Domain ---")
        for r in db.stats_by_domain(since=since):
            print(f"  {r['domain']:40s} {r['count']}")

    if report_type in ("all", "skills"):
        print("\n--- Most Requested Skills ---")
        for r in db.skill_gap_trends(limit=15, since=since):
            print(f"  {r['skill']:40s} {r['appearances']} apps (avg fit: {r['avg_fit_pct']}%)")


def cmd_skills(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    trends = db.skill_gap_trends(limit=args.limit, since=since)
    if args.json:
        print(json.dumps(trends, ensure_ascii=False, indent=2))
        return
    if not trends:
        print("No skill data found.")
        return
    print("Skills most frequently required across applications:")
    for r in trends:
        print(f"  {r['skill']:40s} {r['appearances']} apps, avg fit {r['avg_fit_pct']}%")


def cmd_company_list(db: JobHistoryDB, args: argparse.Namespace) -> None:
    types = ["blacklist", "whitelist"] if args.type == "all" else [args.type]
    for lt in types:
        entries = db.get_company_list(lt)
        if entries:
            print(f"\n{lt.upper()}:")
            for e in entries:
                reason = f" — {e['reason']}" if e.get("reason") else ""
                print(f"  {e['company_name']}{reason}")


def cmd_company_add(db: JobHistoryDB, args: argparse.Namespace) -> None:
    db.add_company_to_list(args.name, args.list_type, reason=args.reason)
    print(f"Added {args.name} to {args.list_type}")


def cmd_company_remove(db: JobHistoryDB, args: argparse.Namespace) -> None:
    ok = db.remove_company_from_list(args.name)
    if ok:
        print(f"Removed {args.name}")
    else:
        print(f"{args.name} not found in any list.", file=sys.stderr)
        sys.exit(1)


def cmd_company_check(db: JobHistoryDB, args: argparse.Namespace) -> None:
    entry = db.check_company_list(args.name)
    if entry:
        reason = f" — {entry['reason']}" if entry.get("reason") else ""
        print(f"{entry['company_name']}: {entry['list_type']}{reason}")
    else:
        print(f"{args.name}: not on any list")


def cmd_export_csv(db: JobHistoryDB, args: argparse.Namespace) -> None:
    content = db.export_csv(output_path=args.output)
    if args.output:
        count = db.total_count()
        print(f"Exported {count} applications to {args.output}")
    else:
        print(content)


def cmd_count(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    print(db.total_count(since=since))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="Job history database CLI")
    parser.add_argument("--db", required=True, help="Path to SQLite database")

    sub = parser.add_subparsers(dest="command")

    # list
    p = sub.add_parser("list", help="List applications")
    p.add_argument("--status", help="Filter by status (generated/applied/rejected/interview/offer)")
    p.add_argument("--company", help="Filter by company name")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--since", help="Only include apps since date (7d/30d/this-week/this-month/ISO)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # get
    p = sub.add_parser("get", help="Get a single application")
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # update-status
    p = sub.add_parser("update-status", help="Update application status")
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("status", choices=["generated", "applied", "rejected", "interview", "offer"])

    # stats
    p = sub.add_parser("stats", help="Show statistics")
    p.add_argument("--type", default="all", choices=["all", "status", "fit", "company", "domain", "skills"])
    p.add_argument("--since", help="Only include apps since date")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # skills
    p = sub.add_parser("skills", help="Show skill gap trends")
    p.add_argument("--limit", type=int, default=20, help="Max skills to show")
    p.add_argument("--since", help="Only include apps since date")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # company-list
    p = sub.add_parser("company-list", help="Show blacklist/whitelist")
    p.add_argument("--type", default="all", choices=["all", "blacklist", "whitelist"])

    # company-add
    p = sub.add_parser("company-add", help="Add company to list")
    p.add_argument("name", help="Company name")
    p.add_argument("--list-type", required=True, choices=["blacklist", "whitelist"])
    p.add_argument("--reason", help="Reason for listing")

    # company-remove
    p = sub.add_parser("company-remove", help="Remove company from list")
    p.add_argument("name", help="Company name")

    # company-check
    p = sub.add_parser("company-check", help="Check if company is on a list")
    p.add_argument("name", help="Company name")

    # export-csv
    p = sub.add_parser("export-csv", help="Export applications to CSV")
    p.add_argument("--output", help="Output file path (prints to stdout if omitted)")

    # count
    p = sub.add_parser("count", help="Show total application count")
    p.add_argument("--since", help="Only count apps since date")

    return parser


def main() -> None:
    # Handle UTF-8 on Windows
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(2)

    db = JobHistoryDB(args.db)
    try:
        handlers = {
            "list": cmd_list,
            "get": cmd_get,
            "update-status": cmd_update_status,
            "stats": cmd_stats,
            "skills": cmd_skills,
            "company-list": cmd_company_list,
            "company-add": cmd_company_add,
            "company-remove": cmd_company_remove,
            "company-check": cmd_company_check,
            "export-csv": cmd_export_csv,
            "count": cmd_count,
        }
        handlers[args.command](db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
