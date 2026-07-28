"""Helpers shared across the CLI command modules."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from scripts.job_history_db import normalise_company


SKILL_BASE = Path(__file__).resolve().parents[2]


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


def resolve_occurred_at(value: str) -> str:
    """Normalise a user-supplied `--at` into an ISO timestamp.

    Accepts a plain date ('2026-07-14', taken as midday so week bucketing isn't
    thrown off by timezone drift at the boundaries), a full ISO timestamp, or
    'today'/'yesterday'. Rejects anything else loudly — a silently misparsed
    date would corrupt every duration computed from it, and the whole point of
    backdating is that the date is trustworthy.
    """
    raw = value.strip()
    today = datetime.now()
    if raw == "today":
        return today.isoformat()
    if raw == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    for fmt, midday in (("%Y-%m-%d", True), ("%Y-%m-%dT%H:%M:%S", False),
                        ("%Y-%m-%d %H:%M:%S", False), ("%Y-%m-%dT%H:%M", False)):
        try:
            dt = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return dt.replace(hour=12).isoformat() if midday else dt.isoformat()
    try:                                    # last resort: full ISO with micros/offset
        return datetime.fromisoformat(raw).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"--at: could not read {value!r} as a date. Use 2026-07-14, "
            "2026-07-14T09:30, 'today', or 'yesterday'."
        ) from None


# ---------------------------------------------------------------------------
# Formatters


def _fmt_app(a: dict) -> str:
    fit = a.get("fit_level") or "n/a"
    pct = a.get("fit_pct")
    pct_s = f"{pct:5.1f}%" if pct is not None else "  n/a"
    return f"#{a['id']:<4d} | {a['status']:10s} | {fit:9s} | {pct_s} | {a['company_name']} — {a['job_title']}"


# ---------------------------------------------------------------------------
# Subcommands


def _guard_expected_company(app: dict, expected: str | None) -> None:
    """Refuse an id-based mutation when the row's company doesn't match the
    caller's expectation.

    Application ids are NOT stable across a DB restore/divergence (a lineage
    swap can leave id 105 pointing at a different company — see `doctor`). So a
    remembered id like "set 105 to applied" can silently hit the wrong record.
    When the caller passes --expect-company, this makes that class of mistake a
    hard error instead of a silent corruption.
    """
    if not expected:
        return
    actual = app.get("company_norm") or normalise_company(app.get("company_name", ""))
    if actual != normalise_company(expected):
        print(
            f"Refusing: application #{app['id']} is '{app['company_name']}' — "
            f"'{app['job_title']}', not '{expected}'. Ids can point at a different "
            "company after a DB restore (see `doctor`). Re-resolve with "
            "`list --company \"<name>\"` and retry.",
            file=sys.stderr,
        )
        sys.exit(2)


_ORG_TYPE_CHOICES = ["end_employer", "esn", "staffing_agency", "recruitment_agency", "unknown"]


def _add_segment_filters(p: argparse.ArgumentParser) -> None:
    """Attach the shared pipeline-segmentation filters (roadmap Phase 2.2)."""
    p.add_argument(
        "--source",
        choices=["offer", "cold"],
        help="Only include applications from this flow (offer vs cold/speculative)",
    )
    p.add_argument(
        "--org-type",
        dest="org_type",
        choices=_ORG_TYPE_CHOICES,
        help="Only include cold-flow rows with this organisation type",
    )
