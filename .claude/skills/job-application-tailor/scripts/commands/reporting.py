"""Read-only reporting commands: list / get / stats / skills / export-csv / count."""
from __future__ import annotations

import argparse
import json
import sys

from scripts.job_history_db import JobHistoryDB
from scripts.commands import Command
from scripts.commands._shared import _add_segment_filters, _fmt_app, resolve_since


def cmd_list(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    apps = db.list_applications(
        status=args.status,
        company=args.company,
        limit=args.limit,
        since=since,
        source=getattr(args, "source", None),
        org_type=getattr(args, "org_type", None),
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


def cmd_stats(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    report_type = args.type
    seg = {"source": getattr(args, "source", None), "org_type": getattr(args, "org_type", None)}

    if args.json:
        result = {}
        if report_type in ("all", "status"):
            result["by_status"] = db.stats_by_status(since=since, **seg)
        if report_type in ("all", "fit"):
            result["by_fit_level"] = db.stats_by_fit_level(since=since, **seg)
        if report_type in ("all", "company"):
            result["by_company"] = db.stats_by_company(since=since, **seg)
        if report_type in ("all", "domain"):
            result["by_domain"] = db.stats_by_domain(since=since, **seg)
        if report_type in ("all", "org"):
            result["by_org_type"] = db.stats_by_org_type(since=since, **seg)
        if report_type in ("all", "skills"):
            result["skill_trends"] = db.skill_gap_trends(limit=15, since=since, **seg)
        result["total"] = db.total_count(since=since, **seg)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    period = f" (since {since})" if since else ""
    seg_note = "".join(
        f" [{k.replace('org_type', 'org-type')}={v}]" for k, v in seg.items() if v
    )
    print(f"Total applications: {db.total_count(since=since, **seg)}{period}{seg_note}")

    if report_type in ("all", "status"):
        print("\n--- By Status ---")
        for r in db.stats_by_status(since=since, **seg):
            print(f"  {r['status']:12s} {r['count']}")

    if report_type in ("all", "fit"):
        print("\n--- By Fit Level ---")
        for r in db.stats_by_fit_level(since=since, **seg):
            lvl = r["fit_level"] or "n/a"
            print(f"  {lvl:12s} {r['count']}")

    if report_type in ("all", "company"):
        print("\n--- By Company ---")
        for r in db.stats_by_company(since=since, **seg):
            print(f"  {r['company_name']:30s} {r['count']}")

    if report_type in ("all", "domain"):
        print("\n--- By Domain ---")
        for r in db.stats_by_domain(since=since, **seg):
            print(f"  {r['domain']:40s} {r['count']}")

    if report_type in ("all", "org"):
        print("\n--- By Org Type (cold flow; offer/legacy rows are '(unset)') ---")
        for r in db.stats_by_org_type(since=since, **seg):
            print(f"  {r['org_type']:20s} {r['count']}")

    if report_type in ("all", "skills"):
        print("\n--- Most Requested Skills ---")
        for r in db.skill_gap_trends(limit=15, since=since, **seg):
            print(f"  {r['skill']:40s} {r['appearances']} apps (avg fit: {r['avg_fit_pct']}%)")


def cmd_skills(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    trends = db.skill_gap_trends(
        limit=args.limit,
        since=since,
        source=getattr(args, "source", None),
        org_type=getattr(args, "org_type", None),
    )
    if args.json:
        print(json.dumps(trends, ensure_ascii=False, indent=2))
        return
    if not trends:
        print("No skill data found.")
        return
    print("Skills most frequently required across applications:")
    for r in trends:
        print(f"  {r['skill']:40s} {r['appearances']} apps, avg fit {r['avg_fit_pct']}%")


def cmd_export_csv(db: JobHistoryDB, args: argparse.Namespace) -> None:
    content = db.export_csv(output_path=args.output)
    if args.output:
        count = db.total_count()
        print(f"Exported {count} applications to {args.output}")
    else:
        print(content)


def cmd_count(db: JobHistoryDB, args: argparse.Namespace) -> None:
    since = resolve_since(args.since) if args.since else None
    print(db.total_count(
        since=since,
        source=getattr(args, "source", None),
        org_type=getattr(args, "org_type", None),
    ))


def _configure_list(p: argparse.ArgumentParser) -> None:
    p.add_argument("--status", help="Filter by status (generated/applied/rejected/interview/offer/dropped)")
    p.add_argument("--company", help="Filter by company name")
    p.add_argument("--limit", type=int, default=50, help="Max results (default: 50)")
    p.add_argument("--since", help="Only include apps since date (7d/30d/this-week/this-month/ISO)")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_get(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_stats(p: argparse.ArgumentParser) -> None:
    p.add_argument("--type", default="all", choices=["all", "status", "fit", "company", "domain", "org", "skills"])
    p.add_argument("--since", help="Only include apps since date")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_skills(p: argparse.ArgumentParser) -> None:
    p.add_argument("--limit", type=int, default=20, help="Max skills to show")
    p.add_argument("--since", help="Only include apps since date")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_export_csv(p: argparse.ArgumentParser) -> None:
    p.add_argument("--output", help="Output file path (prints to stdout if omitted)")


def _configure_count(p: argparse.ArgumentParser) -> None:
    p.add_argument("--since", help="Only count apps since date")
    _add_segment_filters(p)


def cmd_timeline(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Per-week / per-month trend table: volume, average fit, status counts."""
    since = resolve_since(args.since) if args.since else None
    rows = db.timeline(
        group_by=args.group_by, since=since, source=args.source, org_type=args.org_type,
        basis=getattr(args, "basis", "generated"),
    )
    if args.json:
        print(json.dumps({"group_by": args.group_by, "periods": rows},
                         ensure_ascii=False, indent=2))
        return
    if not rows:
        print("No applications in the selected window.")
        return
    print(f"{'Period':<10} | {'Apps':>4} | {'Avg fit':>7} | "
          f"{'Gen':>3} {'App':>3} {'Int':>3} {'Rej':>3} {'Off':>3} {'Drp':>3}")
    print("-" * 62)
    for r in rows:
        fit = f"{r['avg_fit_pct']:.0f}%" if r["avg_fit_pct"] is not None else "—"
        print(f"{r['period']:<10} | {r['applications']:>4} | {fit:>7} | "
              f"{r['generated']:>3} {r['applied']:>3} {r['interview']:>3} "
              f"{r['rejected']:>3} {r['offer']:>3} {r['dropped']:>3}")


def _configure_timeline(p: argparse.ArgumentParser) -> None:
    p.add_argument("--group-by", dest="group_by", default="week", choices=["week", "month"],
                   help="Bucket size for the trend (default: week)")
    p.add_argument("--basis", default="generated", choices=["generated", "applied"],
                   help="Bucket by pack generation date (default) or by when the "
                        "application was actually sent")
    p.add_argument("--since", help="Only include apps since date")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


# ---------------------------------------------------------------------------
# Event-sourced reports (schema v4)


def cmd_history(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """One application's status history, oldest first."""
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)
    events = db.application_events(args.id)
    if args.json:
        print(json.dumps({"application": app, "events": events}, ensure_ascii=False, indent=2))
        return
    print(f"#{app['id']} {app['company_name']} — {app['job_title']}  [now: {app['status']}]")
    if not events:
        print("  (no history recorded)")
        return
    for e in events:
        note = f"  {e['note']}" if e["note"] else ""
        print(f"  {e['occurred_at'][:16]}  {e['status']:10s}{note}".rstrip())


def cmd_response_time(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """How long employers take to respond after you apply."""
    since = resolve_since(args.since) if args.since else None
    rows = db.response_times(
        since=since, source=getattr(args, "source", None),
        org_type=getattr(args, "org_type", None),
    )
    answered = [r for r in rows if r["days"] is not None]
    waiting = [r for r in rows if r["days"] is None]
    if args.json:
        print(json.dumps({"measured": rows, "answered": len(answered),
                          "waiting": len(waiting)}, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("No measurable applications yet.\n"
              "Response time is computed from recorded status changes, and events "
              "reconstructed by the v4 migration are excluded — their dates were "
              "inferred, not observed. This fills in as you record new changes.")
        return
    if answered:
        ds = sorted(r["days"] for r in answered)
        median = ds[len(ds) // 2]
        print(f"Responses: {len(answered)} | median {median:.0f}d | "
              f"fastest {ds[0]:.0f}d | slowest {ds[-1]:.0f}d")
        print("-" * 72)
        for r in sorted(answered, key=lambda r: r["days"]):
            print(f"  {r['days']:5.0f}d  -> {r['next_status']:10s} "
                  f"{r['company_name']} — {r['job_title'][:38]}")
    else:
        print("No completed responses yet.")
    if waiting:
        print(f"\nStill waiting: {len(waiting)}")


def cmd_funnel(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Applications that ever reached each stage, with conversion rates."""
    since = resolve_since(args.since) if args.since else None
    data = db.funnel(
        since=since, source=getattr(args, "source", None),
        org_type=getattr(args, "org_type", None),
    )
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"{'Stage':<12} | {'Count':>5} | Conversion")
    print("-" * 40)
    for s in data["stages"]:
        conv = f"{s['pct_of_previous']:.0f}% of previous" if s["pct_of_previous"] is not None else "—"
        print(f"{s['stage']:<12} | {s['count']:>5} | {conv}")
    print("-" * 40)
    print(f"{'rejected':<12} | {data['exits']['rejected']:>5} | exit")
    print(f"{'dropped':<12} | {data['exits']['dropped']:>5} | exit")


def cmd_follow_up(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Applications that have gone quiet since you applied."""
    rows = db.follow_ups(
        days=args.days, source=getattr(args, "source", None),
        org_type=getattr(args, "org_type", None),
    )
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print(f"Nothing waiting longer than {args.days} days.")
        return
    print(f"{len(rows)} application(s) with no movement for {args.days}+ days:")
    print("-" * 72)
    for r in rows:
        print(f"  #{r['id']:<4d} {r['days_waiting']:>4d}d  applied {r['applied_at'][:10]}  "
              f"{r['company_name']} — {r['job_title'][:34]}")


def _configure_history(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_response_time(p: argparse.ArgumentParser) -> None:
    p.add_argument("--since", help="Only include apps since date")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_funnel(p: argparse.ArgumentParser) -> None:
    p.add_argument("--since", help="Only include apps since date")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


def _configure_follow_up(p: argparse.ArgumentParser) -> None:
    p.add_argument("--days", type=int, default=21,
                   help="Minimum days of silence to flag (default: 21)")
    _add_segment_filters(p)
    p.add_argument("--json", action="store_true", help="Output as JSON")


COMMANDS = [
    Command('list',
            help='List applications',
            configure=_configure_list, handler=cmd_list),
    Command('get',
            help='Get a single application',
            configure=_configure_get, handler=cmd_get),
    Command('stats',
            help='Show statistics',
            configure=_configure_stats, handler=cmd_stats),
    Command('skills',
            help='Show skill gap trends',
            configure=_configure_skills, handler=cmd_skills),
    Command('export-csv',
            help='Export applications to CSV',
            configure=_configure_export_csv, handler=cmd_export_csv),
    Command('count',
            help='Show total application count',
            configure=_configure_count, handler=cmd_count),
    Command('timeline',
            help='Per-week / per-month application trend (volume, avg fit, status counts)',
            configure=_configure_timeline, handler=cmd_timeline),
    Command('history',
            help="Show one application's status history",
            configure=_configure_history, handler=cmd_history),
    Command('response-time',
            help='Days between applying and the first employer response',
            configure=_configure_response_time, handler=cmd_response_time),
    Command('funnel',
            help='Applications that ever reached each stage, with conversion rates',
            configure=_configure_funnel, handler=cmd_funnel),
    Command('follow-up',
            help='Applications with no movement since you applied',
            configure=_configure_follow_up, handler=cmd_follow_up),
]
