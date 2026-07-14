"""Declarative registry for the job-history CLI.

Adding a subcommand means appending one Command(...) entry in the right
domain module. The parser, the dispatch table, and the pre-mutation backup
set all derive from this registry, so they cannot drift apart the way the
three hand-maintained structures in the old monolithic cli.py could (a
mutating command missing from the backup set ran without its safety
snapshot, silently). tests/test_command_registry.py pins the invariants.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Command:
    name: str
    help: str
    configure: Callable[[argparse.ArgumentParser], None]
    handler: Callable[..., None]          # (db, args) -> None
    mutating: bool = False                # True => snapshot the DB before running


# Registration order == the order subcommands appear in --help (kept identical
# to the pre-split monolithic parser).
_ORDER = [
    "list", "get", "update-status", "bulk-status", "update-company",
    "update-output-folder", "stats", "skills", "company-list", "company-add",
    "company-remove", "company-check", "check-duplicate", "export-csv",
    "doctor", "count", "regenerate-outputs", "record-application",
    "rename-application",
]


def all_commands() -> list[Command]:
    from scripts.commands import admin, companies, records, reporting, status

    by_name: dict[str, Command] = {}
    for module in (reporting, status, companies, records, admin):
        for cmd in module.COMMANDS:
            if cmd.name in by_name:
                raise RuntimeError(f"duplicate command name: {cmd.name}")
            by_name[cmd.name] = cmd
    mismatch = set(_ORDER) ^ set(by_name)
    if mismatch:
        raise RuntimeError(f"registry/_ORDER mismatch: {sorted(mismatch)}")
    return [by_name[n] for n in _ORDER]
