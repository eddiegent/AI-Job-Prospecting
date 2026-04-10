"""Phase 1 regression tests for the user customization layer.

Pin the invariants listed under PLUGIN_ROADMAP.md Phase 1 "Tests to write
first". Each test maps one-to-one to a bullet in that list.

The philosophy matches ``tests/test_tailor_invariants.py``: keep the
checks pure-Python (no model calls), fixture data inline, and use pytest's
``tmp_path`` for the few tests that need a real filesystem.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.user_customization import (
    find_forbidden_title_label_violations,
    find_team_context_solo_phrasing,
    load_addendum,
    load_customization_context,
    load_user_prefs,
    merge_addendum_into_fact_base,
)


# --- Addendum loader -------------------------------------------------------

def test_addendum_missing_returns_empty_context(tmp_path):
    ctx = load_customization_context(tmp_path)
    assert ctx["addendum"] == {
        "additional_experience": {},
        "hidden_skills": [],
        "off_cv_facts": [],
    }
    assert "prefs" in ctx


def test_addendum_parses_additional_experience_entries(tmp_path):
    (tmp_path / "cv_addendum.md").write_text(
        "## Additional experience entries\n"
        "\n"
        "### Acme Corp \u2014 Janvier 2018 - Present\n"
        "- Led Fortran to C++ migration of legacy pricing engine\n"
        "- Mentored two junior developers\n",
        encoding="utf-8",
    )
    addendum = load_addendum(tmp_path / "cv_addendum.md")
    key = "Acme Corp \u2014 Janvier 2018 - Present"
    assert key in addendum["additional_experience"]
    assert addendum["additional_experience"][key] == [
        "Led Fortran to C++ migration of legacy pricing engine",
        "Mentored two junior developers",
    ]


def test_addendum_content_reaches_tailor_cv_context(tmp_path, sample_fact_base):
    (tmp_path / "cv_addendum.md").write_text(
        "## Additional experience entries\n"
        "\n"
        "### Acme Corp \u2014 Janvier 2018 - Present\n"
        "- Migrated pricing engine from Fortran to C++\n",
        encoding="utf-8",
    )
    ctx = load_customization_context(tmp_path)
    merged = merge_addendum_into_fact_base(sample_fact_base, ctx["addendum"])
    acme = next(e for e in merged["experience"] if e["company"] == "Acme Corp")
    assert "Migrated pricing engine from Fortran to C++" in acme["details"]


def test_addendum_never_writes_to_fact_base_cache(tmp_path, sample_fact_base):
    # Simulate an on-disk fact base cache and snapshot its bytes.
    cache = tmp_path / "cv_fact_base.json"
    cache.write_bytes(json.dumps(sample_fact_base, indent=2).encode("utf-8"))
    before_sha = hashlib.sha256(cache.read_bytes()).hexdigest()

    (tmp_path / "cv_addendum.md").write_text(
        "## Additional experience entries\n"
        "\n"
        "### Acme Corp \u2014 Janvier 2018 - Present\n"
        "- Added bullet that must not leak to disk\n",
        encoding="utf-8",
    )
    ctx = load_customization_context(tmp_path)
    merged = merge_addendum_into_fact_base(sample_fact_base, ctx["addendum"])
    # Use the merged result so the optimizer can't prove it unused.
    assert merged is not sample_fact_base

    after_sha = hashlib.sha256(cache.read_bytes()).hexdigest()
    assert after_sha == before_sha, (
        "merge_addendum_into_fact_base mutated the fact-base cache on disk; "
        "the addendum is supposed to be a per-run in-memory layer only"
    )


def test_addendum_merge_normalizes_dashes_in_dates():
    """The extractor emits unicode en dashes in date strings, but users
    writing cv_addendum.md naturally type ASCII hyphens. The merger must
    treat the two as equivalent or the addendum silently fails to apply.
    """
    fact_base = {
        "experience": [
            {
                "company": "JFC Informatique & M\u00e9dia",
                "dates": "Octobre 1994 \u2013 Mai 2001",
                "details": ["Existing bullet"],
            }
        ]
    }
    addendum = {
        "additional_experience": {
            # ASCII hyphen on purpose — this is what a user will type.
            "JFC Informatique & M\u00e9dia \u2014 Octobre 1994 - Mai 2001": [
                "Fortran to C++ conversions",
            ]
        },
        "hidden_skills": [],
        "off_cv_facts": [],
    }
    merged = merge_addendum_into_fact_base(fact_base, addendum)
    assert "Fortran to C++ conversions" in merged["experience"][0]["details"]


def test_addendum_does_not_contaminate_verify_fact_base(sample_fact_base):
    original_tech = list(sample_fact_base.get("technologies", []))
    addendum = {
        "additional_experience": {},
        "hidden_skills": ["Fortran", "COBOL"],
        "off_cv_facts": ["Worked on legacy systems"],
    }
    merged = merge_addendum_into_fact_base(sample_fact_base, addendum)
    # technologies stays exactly as extracted from the raw docx.
    assert merged.get("technologies", []) == original_tech
    # Hidden skills go to a distinct bucket.
    assert merged.get("addendum_hidden_skills") == ["Fortran", "COBOL"]


# --- User prefs loader -----------------------------------------------------

def test_missing_prefs_file_is_not_an_error(tmp_path):
    prefs = load_user_prefs(tmp_path / "user_prefs.yaml")
    assert prefs["default_language"] == "auto"
    assert prefs["forbidden_title_labels"] == []
    assert prefs["team_context_companies"] == []


def test_user_prefs_forbidden_title_labels_blocks_label(tmp_path):
    (tmp_path / "user_prefs.yaml").write_text(
        "forbidden_title_labels:\n  - Backend\n",
        encoding="utf-8",
    )
    prefs = load_user_prefs(tmp_path / "user_prefs.yaml")
    offending = {"title": "Senior Backend Developer"}
    ok = {"title": "Senior Desktop & Services Developer"}
    assert find_forbidden_title_label_violations(offending, prefs) != []
    assert find_forbidden_title_label_violations(ok, prefs) == []


def test_user_prefs_team_context_companies_prevents_solo_phrasing(tmp_path):
    (tmp_path / "user_prefs.yaml").write_text(
        "team_context_companies:\n  - Oodrive\n",
        encoding="utf-8",
    )
    prefs = load_user_prefs(tmp_path / "user_prefs.yaml")

    solo = (
        "Chez Oodrive, en tant que seul d\u00e9veloppeur sur le projet, "
        "j'ai con\u00e7u l'architecture compl\u00e8te."
    )
    team = (
        "Chez Oodrive, au sein d'une \u00e9quipe de cinq d\u00e9veloppeurs, "
        "j'ai contribu\u00e9 \u00e0 l'architecture."
    )
    assert find_team_context_solo_phrasing(solo, prefs) != []
    assert find_team_context_solo_phrasing(team, prefs) == []
