"""Recount match_summary in a match_analysis.json file.

The LLM authors both ``matches[]`` and ``match_summary`` and the two
regularly drift. ``match_summary`` is a pure function of the matches, so
this script overwrites it with the deterministically computed value
before validation. Idempotent.

Usage:
    python scripts/recount_match_summary.py <path-to-match_analysis.json>

Exits 0 on success, prints "before -> after" when the summary changed,
prints "OK (already correct)" when it was already in sync, exits 1 on
JSON / IO errors. Designed to be a one-shot pipeline step run between
``match_analysis.json`` write and schema validation.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

# When invoked as a script, scripts/ is on sys.path so the bare import works.
from common import recount_match_summary


def main(argv: list[str]) -> int:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    if len(argv) != 2:
        print("Usage: recount_match_summary.py <path-to-match_analysis.json>", file=sys.stderr)
        return 1

    target = Path(argv[1])
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read {target}: {exc}", file=sys.stderr)
        return 1

    matches = data.get("matches", [])
    if not isinstance(matches, list):
        print("matches must be an array", file=sys.stderr)
        return 1

    correct = recount_match_summary(matches)
    current = data.get("match_summary")

    if current == correct:
        print("OK (already correct)")
        return 0

    data["match_summary"] = correct
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Updated match_summary: {current} -> {correct}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
