"""Invariants of the declarative command registry (scripts/commands/).

The registry exists so the parser, the dispatch table, and the pre-mutation
backup set cannot drift apart. In the old monolithic cli.py those were three
hand-maintained structures, and a mutating command missing from the backup
set ran without its safety snapshot — silently. These tests make that class
of drift loud.
"""
from __future__ import annotations

import argparse

from scripts.cli import build_parser
from scripts.commands import _ORDER, Command, all_commands

# The commands that write to the DB and therefore MUST take a pre-mutation
# snapshot. Adding a mutating command means updating this set consciously —
# that is the point: forgetting mutating=True on the Command entry, or
# forgetting to extend this set, fails here instead of silently skipping
# the backup.
EXPECTED_MUTATING = {
    "update-status", "bulk-status", "update-company", "update-output-folder",
    "record-application", "rename-application",
    "company-add", "company-remove",
}


def test_registry_is_complete_and_ordered() -> None:
    cmds = all_commands()
    names = [c.name for c in cmds]
    assert names == _ORDER
    assert len(names) == len(set(names))


def test_every_command_is_wellformed() -> None:
    for cmd in all_commands():
        assert isinstance(cmd, Command)
        assert cmd.help, cmd.name
        assert callable(cmd.handler), cmd.name
        # configure must run cleanly against a fresh parser
        cmd.configure(argparse.ArgumentParser(prog=cmd.name))


def test_mutating_set_matches_expectation() -> None:
    actual = {c.name for c in all_commands() if c.mutating}
    assert actual == EXPECTED_MUTATING


def test_parser_covers_exactly_the_registry() -> None:
    parser = build_parser()
    sub_actions = [
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    ]
    assert len(sub_actions) == 1
    parser_names = list(sub_actions[0].choices)
    assert parser_names == [c.name for c in all_commands()]
