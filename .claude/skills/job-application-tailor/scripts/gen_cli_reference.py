"""Generate references/cli.md from the cli.py argparse parser.

Single source of truth: imports build_parser() from cli.py and walks every
subparser. Output is byte-stable (sorted, no timestamps) so the pre-commit hook
can detect drift by diff alone.

Usage:
    python scripts/gen_cli_reference.py            # write references/cli.md
    python scripts/gen_cli_reference.py --check    # exit 1 if regen would change file
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

SKILL_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_BASE / "scripts"))

from cli import build_parser  # noqa: E402

OUTPUT_PATH = SKILL_BASE / "references" / "cli.md"


def _action_flags(action: argparse.Action) -> list[str]:
    return [s for s in action.option_strings if s.startswith("--")]


def _is_positional(action: argparse.Action) -> bool:
    return not action.option_strings


def _format_signature(name: str, sub: argparse.ArgumentParser) -> str:
    parts = [name]
    for a in sub._actions:
        if isinstance(a, argparse._HelpAction):
            continue
        if _is_positional(a):
            parts.append(f"<{a.dest}>")
        else:
            flag = a.option_strings[0]
            if isinstance(a, argparse._StoreTrueAction) or isinstance(a, argparse._StoreFalseAction):
                parts.append(f"[{flag}]")
            elif a.required:
                parts.append(f"{flag} <{a.dest}>")
            else:
                parts.append(f"[{flag} <{a.dest}>]")
    return " ".join(parts)


def _format_args_table(sub: argparse.ArgumentParser) -> list[str]:
    rows = []
    for a in sub._actions:
        if isinstance(a, argparse._HelpAction):
            continue
        if _is_positional(a):
            label = f"`{a.dest}`"
            kind = "positional"
        else:
            label = "`" + ", ".join(a.option_strings) + "`"
            if isinstance(a, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
                kind = "flag"
            elif a.required:
                kind = "required"
            else:
                kind = "optional"
        choices = ""
        if a.choices:
            choices = " — choices: " + ", ".join(f"`{c}`" for c in a.choices)
        default = ""
        if a.default not in (None, False, argparse.SUPPRESS) and not isinstance(
            a, (argparse._StoreTrueAction, argparse._StoreFalseAction)
        ):
            default = f" (default: `{a.default}`)"
        help_text = (a.help or "").replace("\n", " ").strip()
        rows.append(f"| {label} | {kind} | {help_text}{choices}{default} |")
    if not rows:
        return ["_(no arguments)_", ""]
    return [
        "| Arg | Kind | Description |",
        "| --- | --- | --- |",
        *rows,
        "",
    ]


def render() -> str:
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )

    lines = [
        "# CLI Reference",
        "",
        "**Auto-generated** by `scripts/gen_cli_reference.py` from `scripts/cli.py`.",
        "Do not edit by hand — the pre-commit hook regenerates this file.",
        "",
        "All commands assume `--db <path>` is set against `resources/job_history.db`:",
        "",
        "```bash",
        'cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" <subcommand> [args...]',
        "```",
        "",
        "## Subcommands",
        "",
    ]

    for name in sorted(subparsers_action.choices.keys()):
        sub = subparsers_action.choices[name]
        help_text = (subparsers_action._name_parser_map[name].description or "").strip()
        sub_help = ""
        for choice_action in subparsers_action._choices_actions:
            if choice_action.dest == name:
                sub_help = (choice_action.help or "").strip()
                break

        lines.append(f"### `{name}`")
        lines.append("")
        if sub_help:
            lines.append(sub_help)
            lines.append("")
        lines.append("**Signature:**")
        lines.append("")
        lines.append("```")
        lines.append(_format_signature(name, sub))
        lines.append("```")
        lines.append("")
        lines.extend(_format_args_table(sub))

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="Exit 1 if file is out of date")
    args = ap.parse_args()

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    new_content = render()

    if args.check:
        if not OUTPUT_PATH.exists():
            print(f"MISSING: {OUTPUT_PATH}", file=sys.stderr)
            return 1
        current = OUTPUT_PATH.read_text(encoding="utf-8")
        if current != new_content:
            print(f"DRIFT: {OUTPUT_PATH} is out of date — run gen_cli_reference.py", file=sys.stderr)
            return 1
        print("OK: cli.md is up to date")
        return 0

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(new_content, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
