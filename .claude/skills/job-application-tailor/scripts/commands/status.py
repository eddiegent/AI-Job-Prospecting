"""Status/metadata mutations: update-status / bulk-status / update-company / update-output-folder."""
from __future__ import annotations

import argparse
import sys

from scripts.job_history_db import JobHistoryDB
from scripts.commands import Command
from scripts.commands._shared import _guard_expected_company


def cmd_update_status(db: JobHistoryDB, args: argparse.Namespace) -> None:
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)
    _guard_expected_company(app, getattr(args, "expect_company", None))
    ok = db.update_status(args.id, args.status)
    if ok:
        print(f"#{args.id} {app['company_name']} — {app['job_title']}: {app['status']} -> {args.status}")
    else:
        print("Update failed.", file=sys.stderr)
        sys.exit(1)


def cmd_bulk_status(db: JobHistoryDB, args: argparse.Namespace) -> None:
    """Set the same status on several applications in one call (roadmap 3.2).

    The single-id `update-status` carries an `--expect-company` guard; bulk is
    inherently multi-company, so instead of a guard it prints each row's
    company/title as it changes, letting the caller eyeball that the ids resolved
    to what they meant. A single pre-mutation backup (roadmap 1.2) covers the
    whole batch. Missing ids are reported and skipped; the command exits non-zero
    if any id was missing, so a typo in a batch doesn't pass silently."""
    seen: set[int] = set()
    missing: list[int] = []
    for app_id in args.ids:
        if app_id in seen:
            continue
        seen.add(app_id)
        app = db.get_application(app_id)
        if not app:
            missing.append(app_id)
            print(f"#{app_id}: not found — skipped.", file=sys.stderr)
            continue
        if db.update_status(app_id, args.status):
            print(f"#{app_id} {app['company_name']} — {app['job_title']}: "
                  f"{app['status']} -> {args.status}")
        else:
            missing.append(app_id)
            print(f"#{app_id}: update failed.", file=sys.stderr)
    if missing:
        sys.exit(1)


def cmd_update_company(db: JobHistoryDB, args: argparse.Namespace) -> None:
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)
    _guard_expected_company(app, getattr(args, "expect_company", None))
    ok = db.update_company(args.id, args.name)
    if ok:
        print(f"#{args.id}: company '{app['company_name']}' -> '{args.name}'")
    else:
        print("Update failed.", file=sys.stderr)
        sys.exit(1)


def cmd_update_output_folder(db: JobHistoryDB, args: argparse.Namespace) -> None:
    app = db.get_application(args.id)
    if not app:
        print(f"Application #{args.id} not found.", file=sys.stderr)
        sys.exit(1)
    ok = db.update_output_folder(args.id, args.path)
    if ok:
        print(f"#{args.id}: output_folder '{app['output_folder']}' -> '{args.path}'")
    else:
        print("Update failed.", file=sys.stderr)
        sys.exit(1)


def _configure_update_status(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("status", choices=["generated", "applied", "rejected", "interview", "offer", "dropped"])
    p.add_argument(
        "--expect-company",
        help="Safety guard: refuse if application <id> is not this company "
        "(ids can point elsewhere after a DB restore — see `doctor`)",
    )


def _configure_bulk_status(p: argparse.ArgumentParser) -> None:
    p.add_argument("ids", type=int, nargs="+", help="One or more application IDs")
    p.add_argument(
        "--status",
        required=True,
        choices=["generated", "applied", "rejected", "interview", "offer", "dropped"],
    )


def _configure_update_company(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("name", help="New company name")
    p.add_argument(
        "--expect-company",
        help="Safety guard: refuse if application <id> is not currently this company",
    )


def _configure_update_output_folder(p: argparse.ArgumentParser) -> None:
    p.add_argument("id", type=int, help="Application ID")
    p.add_argument("path", help="New output folder path")


COMMANDS = [
    Command('update-status',
            help='Update application status',
            configure=_configure_update_status, handler=cmd_update_status, mutating=True),
    Command('bulk-status',
            help='Set the same status on several applications at once (one backup covers the batch)',
            configure=_configure_bulk_status, handler=cmd_bulk_status, mutating=True),
    Command('update-company',
            help='Rename the company on an application',
            configure=_configure_update_company, handler=cmd_update_company, mutating=True),
    Command('update-output-folder',
            help='Update the output_folder path on an application',
            configure=_configure_update_output_folder, handler=cmd_update_output_folder, mutating=True),
]
