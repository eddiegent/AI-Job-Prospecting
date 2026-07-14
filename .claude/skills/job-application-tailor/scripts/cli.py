"""CLI entry point for the job history database.

Usage:
    python scripts/cli.py --db <path> <subcommand> [options]

Subcommands are defined declaratively in scripts/commands/ — the parser, the
dispatch table, and the pre-mutation backup set all derive from that registry.

Exit-code conventions (enforced per-handler):
    0  success
    1  domain failure (not found, validation failure, duplicate/blacklist flag)
    2  bad input or guard refusal (missing artefacts, --expect-company
       mismatch, no subcommand given)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):  # direct run: make `scripts.*` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.commands import all_commands  # noqa: E402
from scripts.common import force_utf8_stdio  # noqa: E402
from scripts.job_history_db import JobHistoryDB  # noqa: E402
from scripts.paths import resolve_user_data_dir  # noqa: E402

SKILL_BASE = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cli.py", description="Job history database CLI")
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database (default: <user-data-dir>/job_history.db, "
        "resolved via JOB_TAILOR_HOME, then the legacy repo resources/ layout, "
        "then the OS app-data dir)",
    )
    sub = parser.add_subparsers(dest="command")
    for cmd in all_commands():
        cmd.configure(sub.add_parser(cmd.name, help=cmd.help))
    return parser


def main() -> None:
    force_utf8_stdio()

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(2)

    command = {c.name: c for c in all_commands()}[args.command]

    if not command.needs_db:
        command.handler(None, args)
        return

    db_path = args.db or str(resolve_user_data_dir() / "job_history.db")
    db = JobHistoryDB(db_path)
    try:
        # Auto-backup before any command that writes (roadmap 1.2). Best-effort:
        # snapshot_before_mutation never raises, so a backup hiccup can't block
        # the mutation. Gives a cheap undo if a write goes wrong or a stale
        # mirror clobbers newer rows.
        if command.mutating:
            db.snapshot_before_mutation()
        command.handler(db, args)
    finally:
        db.close()


if __name__ == "__main__":
    main()
