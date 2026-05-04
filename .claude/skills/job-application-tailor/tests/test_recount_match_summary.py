"""Tests for the deterministic match_summary recount.

The LLM authors both ``matches[]`` and ``match_summary`` and the two
regularly drift. This helper enforces consistency from the matches array.
"""
from __future__ import annotations

from scripts.common import recount_match_summary


def _matches(direct: int, transferable: int, gap: int) -> list[dict]:
    return (
        [{"match_type": "direct"}] * direct
        + [{"match_type": "transferable"}] * transferable
        + [{"match_type": "gap"}] * gap
    )


def test_basic_counts() -> None:
    out = recount_match_summary(_matches(10, 4, 6))
    assert out == {
        "direct_count": 10,
        "transferable_count": 4,
        "gap_count": 6,
        "overall_fit_pct": 60,  # (10 + 4*0.5)/20 = 0.6
    }


def test_only_direct() -> None:
    out = recount_match_summary(_matches(5, 0, 0))
    assert out["overall_fit_pct"] == 100
    assert out["direct_count"] == 5


def test_only_gaps() -> None:
    out = recount_match_summary(_matches(0, 0, 7))
    assert out["overall_fit_pct"] == 0
    assert out["gap_count"] == 7


def test_empty_matches_returns_zero_pct() -> None:
    out = recount_match_summary([])
    assert out == {
        "direct_count": 0,
        "transferable_count": 0,
        "gap_count": 0,
        "overall_fit_pct": 0,
    }


def test_unknown_match_types_ignored() -> None:
    """Defensive: a malformed match_type doesn't crash and isn't counted."""
    matches = _matches(2, 1, 1) + [{"match_type": "wishful"}, {"foo": "bar"}]
    out = recount_match_summary(matches)
    # 2 direct + 1 transferable + 1 gap = 4 (unknowns dropped)
    assert out["direct_count"] == 2
    assert out["transferable_count"] == 1
    assert out["gap_count"] == 1
    assert out["overall_fit_pct"] == round((2 + 0.5) / 4 * 100)  # 63


def test_real_world_ingeline_case() -> None:
    """The case that triggered this work — INGELINE run, 2026-05-04.

    The LLM authored ``direct=15, transferable=9, gap=7, fit=63`` for
    a matches array that actually contained 16/8/7. Recount must produce
    the correct figures.
    """
    out = recount_match_summary(_matches(16, 8, 7))
    assert out == {
        "direct_count": 16,
        "transferable_count": 8,
        "gap_count": 7,
        "overall_fit_pct": 65,  # (16 + 4) / 31 * 100 = 64.5 -> 65
    }


def test_rounding_is_to_nearest_integer() -> None:
    # 1 direct + 1 transferable + 1 gap = 3 total, fit = 1.5/3 = 50
    assert recount_match_summary(_matches(1, 1, 1))["overall_fit_pct"] == 50
    # 2 direct + 1 transferable + 0 gap = 3 total, fit = 2.5/3 = 83.33 -> 83
    assert recount_match_summary(_matches(2, 1, 0))["overall_fit_pct"] == 83
    # 1 direct + 0 transferable + 2 gap = 3 total, fit = 1/3 = 33.33 -> 33
    assert recount_match_summary(_matches(1, 0, 2))["overall_fit_pct"] == 33
