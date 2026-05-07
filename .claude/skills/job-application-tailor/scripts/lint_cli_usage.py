"""Lint markdown files for stale cli.py invocations.

For every line containing `python ... cli.py ... <subcommand> ...` (in code blocks
or prose), verify that:
  - the subcommand exists
  - every `--flag` token used actually exists on that subcommand

This catches the failure mode where docs reference flags that were renamed,
removed, or never existed (e.g. `update-status --id 50 --status applied` when
the real signature is `update-status <id> <status>`).

Usage:
    python scripts/lint_cli_usage.py [path1.md path2.md ...]

If no paths are given, scans all *.md under the repo root (excluding the
auto-generated references/cli.md).

Exit code 0 if clean, 1 if any drift detected.
"""
from __future__ import annotations

import argparse
import io
import re
import subprocess
import sys
from pathlib import Path

SKILL_BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_BASE / "scripts"))

from cli import build_parser  # noqa: E402

# Flags that belong to the top-level parser, valid in every invocation
TOP_LEVEL_FLAGS = {"--db", "--help", "-h"}

# Match a real invocation: `python ... cli.py [--global-flags] <subcommand>`.
# Requires the literal `python` token on the same (joined) line — this filters
# out prose mentions of cli.py.
INVOCATION_RE = re.compile(
    r"\bpython\b[^\n]*?\bcli\.py\b\s+"
    r"(?:--\S+(?:\s+(?!-)\S+)?\s+)*"  # optional --flag [value] pairs (e.g. --db DB)
    r"(?P<sub>[a-z][a-z0-9-]+)\b"
)
FLAG_RE = re.compile(r"(--[a-zA-Z][a-zA-Z0-9-]*)")


def _build_subcommand_index() -> dict[str, set[str]]:
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    index: dict[str, set[str]] = {}
    for name, sub in subparsers_action.choices.items():
        flags: set[str] = set()
        for action in sub._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            for opt in action.option_strings:
                flags.add(opt)
        index[name] = flags
    return index


def _list_default_files() -> list[Path]:
    """Discover *.md files via git ls-files, fallback to glob."""
    repo_root = SKILL_BASE.parent.parent.parent  # skill -> .claude/skills -> .claude -> repo
    while not (repo_root / ".git").exists() and repo_root != repo_root.parent:
        repo_root = repo_root.parent
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "*.md"], cwd=repo_root, text=True, encoding="utf-8"
        )
        files = [repo_root / line.strip() for line in out.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        files = list(repo_root.rglob("*.md"))
    # Exclude auto-generated reference
    auto_gen = SKILL_BASE / "references" / "cli.md"
    return [f for f in files if f.exists() and f.resolve() != auto_gen.resolve()]


def _join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """Stitch backslash-continued shell lines inside fenced code blocks.

    Returns (origin_lineno, joined_line) only for lines that live inside a
    ```bash / ```shell / ``` fenced block. Prose mentions of cli.py outside
    code blocks are excluded — they're descriptions, not invocations.
    """
    out: list[tuple[int, str]] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        if not in_fence:
            i += 1
            continue
        origin = i + 1
        joined = line
        while joined.rstrip().endswith("\\") and i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt.lstrip().startswith("```"):
                break
            joined = joined.rstrip()[:-1] + " " + nxt.lstrip()
            i += 1
        out.append((origin, joined))
        i += 1
    return out


def lint_file(path: Path, index: dict[str, set[str]]) -> list[tuple[int, str]]:
    issues: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return issues
    for lineno, line in _join_continuations(text.splitlines()):
        m = INVOCATION_RE.search(line)
        if not m:
            continue
        subcmd = m.group("sub")
        if subcmd not in index:
            issues.append(
                (lineno, f"unknown subcommand `{subcmd}` (line: {line.strip()[:100]})")
            )
            continue
        valid_flags = index[subcmd] | TOP_LEVEL_FLAGS
        # Only validate flags AFTER the subcommand — `--db` before it is global.
        tail = line[m.end() :]
        for flag in FLAG_RE.findall(tail):
            if flag not in valid_flags:
                issues.append(
                    (lineno, f"`{subcmd}` has no flag `{flag}` (line: {line.strip()[:100]})")
                )
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="Markdown files to lint (default: all *.md)")
    args = ap.parse_args()

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

    index = _build_subcommand_index()
    if args.paths:
        files = [Path(p) for p in args.paths]
    else:
        files = _list_default_files()

    total_issues = 0
    for f in files:
        issues = lint_file(f, index)
        if issues:
            print(f"\n{f}")
            for lineno, msg in issues:
                print(f"  line {lineno}: {msg}")
            total_issues += len(issues)

    if total_issues:
        print(f"\nFAIL: {total_issues} issue(s) found across {len(files)} file(s)", file=sys.stderr)
        return 1
    print(f"OK: linted {len(files)} file(s), no drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
