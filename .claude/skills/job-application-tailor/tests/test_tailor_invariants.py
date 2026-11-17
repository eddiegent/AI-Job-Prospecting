"""Regression tests for the rules documented in prompts/cv_rules.md.

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
    find_missing_recent_roles,
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
    assert any("dateless" in v for v in violations)


# --- Recent roles always appear in full ------------------------------------

def test_recent_roles_all_present(sample_fact_base):
    good = load_fixture("tailored_cv_good.json")
    assert find_missing_recent_roles(good, sample_fact_base, cutoff_year=2005) == []


def test_recent_role_folded_into_consolidated_line_is_flagged(sample_fact_base):
    cv = load_fixture("tailored_cv_good.json")
    midway = cv["experience"].pop(1)
    cv["experience"][-1]["metadata_line"] = "Midway Systems | TinyShop"
    violations = find_missing_recent_roles(cv, sample_fact_base, cutoff_year=2005)
    assert len(violations) == 1 and "Midway Systems" in violations[0]
    assert midway["metadata_line"].startswith("Midway Systems")


def test_recent_role_cutoff_null_requires_every_role(sample_fact_base):
    good = load_fixture("tailored_cv_good.json")
    violations = find_missing_recent_roles(good, sample_fact_base, cutoff_year=None)
    assert len(violations) == 1 and "TinyShop" in violations[0]


def _nested_fact_base() -> dict:
    return {"experience": [
        {"type": "role", "company": "Telmar Peaktime SAS", "dates": "Mars 2005 – Juin 2010"},
        {"type": "role", "company": "JFC Informatique & Média (Kantar)", "dates": "Décembre 2002 – Mars 2005"},
        {"type": "role", "company": "Peaktime SAS", "dates": "Mai 2001 – Décembre 2002"},
        {"type": "role", "company": "JFC Informatique & Média", "dates": "Octobre 1994 – Mai 2001"},
    ]}


def _entry(role: str, meta: str) -> dict:
    return {"role_line": role, "metadata_line": meta, "bullets": []}


def test_recent_role_matching_tells_nested_company_names_apart():
    # The 2002-2005 JFC role is folded; the 1994-2001 JFC line must not
    # stand in for it, nor Telmar Peaktime for Peaktime.
    cv = {"experience": [
        _entry("Development Manager", "Telmar Peaktime SAS | Paris | Mars 2005 – Juin 2010"),
        _entry("Analyste", "JFC Informatique & Média | Asnières | Octobre 1994 – Mai 2001"),
        _entry("Expériences antérieures", "JFC Informatique & Média (Kantar) | Peaktime SAS"),
    ]}
    violations = find_missing_recent_roles(cv, _nested_fact_base(), cutoff_year=2005)
    assert len(violations) == 1 and "(Kantar)" in violations[0]


def test_recent_role_matching_tolerates_moved_parenthetical_and_legal_form():
    fb = {"experience": [{"type": "role", "company": "Oodrive SAS", "dates": "Juillet 2010 – Mars 2025"},
                         *_nested_fact_base()["experience"]]}
    cv = {"experience": [
        _entry("R&D", "Oodrive SA | Paris | Juillet 2010 – Mars 2025"),
        _entry("Development Manager", "Telmar Peaktime SAS | Paris | Mars 2005 – Juin 2010"),
        _entry("Chef de Projet (Kantar)", "JFC Informatique & Média | Paris | Décembre 2002 – Mars 2005"),
    ]}
    assert find_missing_recent_roles(cv, fb, cutoff_year=2005) == []


def test_load_bearing_ambiguous_company_needs_the_roles_years():
    fb = _nested_fact_base()
    cv = {"experience": [
        _entry("Development Manager", "Telmar Peaktime SAS | Paris | Mars 2005 – Juin 2010"),
        _entry("Chef de Projet", "JFC Informatique & Média (Kantar) | Paris | Décembre 2002 – Mars 2005"),
        _entry("Expériences antérieures", "Peaktime SAS | JFC Informatique & Média"),
    ]}
    kantar_only = {"matches": [{"match_type": "direct",
                                "evidence": "UK parent at JFC Informatique & Média (2002–2005)"}]}
    assert find_missing_load_bearing_roles(cv, fb, kantar_only, cutoff_year=2005) == []
    asnieres = {"matches": [{"match_type": "direct",
                             "evidence": "Fortran to C++ at JFC Informatique & Média (1994–2001)"}]}
    violations = find_missing_load_bearing_roles(cv, fb, asnieres, cutoff_year=2005)
    assert len(violations) == 1 and "'JFC Informatique & Média'" in violations[0]


def test_load_bearing_ignores_a_longer_name_and_a_year_belonging_to_another_role():
    # "Peaktime" here is Telmar Peaktime, and 2002 belongs to the Kantar role.
    fb = _nested_fact_base()
    cv = {"experience": [
        _entry("Development Manager", "Telmar Peaktime SAS | Paris | Mars 2005 – Juin 2010"),
        _entry("Chef de Projet", "JFC Informatique & Média (Kantar) | Paris | Décembre 2002 – Mars 2005"),
        _entry("Analyste", "JFC Informatique & Média | Asnières | Octobre 1994 – Mai 2001"),
        _entry("Expériences antérieures", "Peaktime SAS"),
    ]}
    ma = {"matches": [{"match_type": "transferable", "evidence":
                       "Outils presse chez JFC Informatique & Média (Kantar) (2002–2005) et M6 chez Telmar Peaktime SAS."}]}
    assert find_missing_load_bearing_roles(cv, fb, ma, cutoff_year=2005) == []


def test_load_bearing_detected_from_a_short_name_and_the_roles_location():
    # 2026-11-17: evidence citing "JFC (Asnières)" left the role folded.
    fb = {"experience": [
        {"type": "role", "company": "JFC Informatique & Média (Kantar)", "dates": "Décembre 2002 – Mars 2005",
         "location": "Paris"},
        {"type": "role", "company": "Oodrive SAS", "dates": "Juillet 2010 – Mars 2025", "location": "Paris"},
        {"type": "role", "company": "JFC Informatique & Média", "dates": "Octobre 1994 – Mai 2001",
         "location": "Asnières"},
    ]}
    cv = {"experience": [
        _entry("R&D", "Oodrive SAS | Paris | Juillet 2010 – Mars 2025"),
        _entry("Expériences antérieures", "JFC Informatique & Média (Kantar) | JFC Informatique & Média (Asnières)"),
    ]}
    asnieres = {"matches": [{"match_type": "direct", "evidence": "Analyse fonctionnelle chez JFC (Asnières)"}]}
    violations = find_missing_load_bearing_roles(cv, fb, asnieres, cutoff_year=2006)
    assert len(violations) == 1 and "Octobre 1994" in violations[0]
    kantar = {"matches": [{"match_type": "direct", "evidence": "Interface UK chez JFC (Kantar)"}]}
    violations = find_missing_load_bearing_roles(cv, fb, kantar, cutoff_year=2006)
    assert len(violations) == 1 and "Décembre 2002" in violations[0]
    plain = {"matches": [{"match_type": "direct", "evidence": "Outils presse chez JFC"}]}
    assert find_missing_load_bearing_roles(cv, fb, plain, cutoff_year=2006) == []
