"""Regression tests for the rules documented in prompts/tailor_cv.md.

These exercise the pure-Python validators in scripts/tailor_invariants.py
against hand-built fixtures. They pin the rules at the JSON-shape level so
that a prompt edit that accidentally removes (say) the training-in-education
rule will be caught by the next CI run rather than by a confused recruiter
six weeks later.
"""
from __future__ import annotations

from scripts.tailor_invariants import (
    find_consolidated_line_issues,
    find_missing_load_bearing_roles,
    find_non_consolidated_non_load_bearing_roles,
    find_training_entries_in_experience,
)
from tests.conftest import load_fixture


# --- Training-in-Education rule --------------------------------------------

def test_training_entries_not_in_experience(sample_fact_base):
    good = load_fixture("tailored_cv_good.json")
    assert find_training_entries_in_experience(good, sample_fact_base) == []


def test_training_leak_is_detected(sample_fact_base):
    leaked = load_fixture("tailored_cv_training_leaked.json")
    violations = find_training_entries_in_experience(leaked, sample_fact_base)
    assert len(violations) == 1
    assert "École Cube" in violations[0]


# --- Compression: load-bearing preservation --------------------------------

def test_compression_keeps_load_bearing_role(sample_fact_base, sample_match_analysis):
    good = load_fixture("tailored_cv_good.json")
    violations = find_missing_load_bearing_roles(
        good, sample_fact_base, sample_match_analysis, cutoff_year=2005
    )
    assert violations == []


def test_compression_detects_dropped_load_bearing_role(
    sample_fact_base, sample_match_analysis
):
    dropped = load_fixture("tailored_cv_dropped_load_bearing.json")
    violations = find_missing_load_bearing_roles(
        dropped, sample_fact_base, sample_match_analysis, cutoff_year=2005
    )
    assert len(violations) == 1
    assert "OldCo Media" in violations[0]


# --- Compression: non-load-bearing consolidation ---------------------------

def test_compression_consolidates_non_load_bearing(sample_fact_base, sample_match_analysis):
    good = load_fixture("tailored_cv_good.json")
    violations = find_non_consolidated_non_load_bearing_roles(
        good, sample_fact_base, sample_match_analysis, cutoff_year=2005
    )
    assert violations == []


# --- Compression: cutoff-null disables the rule ----------------------------

def test_compression_disabled_when_cutoff_null(sample_fact_base, sample_match_analysis):
    dropped = load_fixture("tailored_cv_dropped_load_bearing.json")
    assert find_missing_load_bearing_roles(
        dropped, sample_fact_base, sample_match_analysis, cutoff_year=None
    ) == []
    assert find_non_consolidated_non_load_bearing_roles(
        dropped, sample_fact_base, sample_match_analysis, cutoff_year=None
    ) == []


# --- Consolidated line must be dateless in the detected language ----------

def test_consolidated_line_is_dateless_in_detected_language():
    good = load_fixture("tailored_cv_good.json")
    assert find_consolidated_line_issues(good, expected_language="fr") == []


def test_consolidated_line_with_date_is_flagged():
    dated = load_fixture("tailored_cv_consolidated_dated.json")
    violations = find_consolidated_line_issues(dated, expected_language="fr")
    assert any("empty date_line" in v for v in violations)
