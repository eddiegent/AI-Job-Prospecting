"""Blacklist/whitelist management: company-list / company-add / company-remove / company-check."""
from __future__ import annotations

import argparse
import sys

from scripts.job_history_db import JobHistoryDB
from scripts.commands import Command


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


def _configure_company_list(p: argparse.ArgumentParser) -> None:
    p.add_argument("--type", default="all", choices=["all", "blacklist", "whitelist"])


def _configure_company_add(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", help="Company name")
    p.add_argument("--list-type", required=True, choices=["blacklist", "whitelist"])
    p.add_argument("--reason", help="Reason for listing")


def _configure_company_remove(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", help="Company name")


def _configure_company_check(p: argparse.ArgumentParser) -> None:
    p.add_argument("name", help="Company name")


COMMANDS = [
    Command('company-list',
            help='Show blacklist/whitelist',
            configure=_configure_company_list, handler=cmd_company_list),
    Command('company-add',
            help='Add company to list',
            configure=_configure_company_add, handler=cmd_company_add, mutating=True),
    Command('company-remove',
            help='Remove company from list',
            configure=_configure_company_remove, handler=cmd_company_remove, mutating=True),
    Command('company-check',
            help='Check if company is on a list',
            configure=_configure_company_check, handler=cmd_company_check),
]
