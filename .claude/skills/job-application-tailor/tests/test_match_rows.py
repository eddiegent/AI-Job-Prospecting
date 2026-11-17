"""Tests for scripts/match_rows.py - one match row per offer item."""
from __future__ import annotations

import json
from argparse import Namespace

from scripts.commands.pipeline import cmd_match_rows
from scripts.match_rows import absorbed_technologies, coverage_problems, expected_rows, row_key

OFFER = {
    "required_skills": ["C#", "Maîtrise de SQL Server"],
    "preferred_skills": ["Docker", "c# "],                 # duplicate of a required skill
    "technologies": ["C#", "Kubernetes", ""],               # duplicate + empty
    "responsibilities": ["Concevoir des API REST", "Maîtrise de SQL Server."],  # duplicate with a dot
}


def test_expected_rows_one_per_item_first_list_wins():
    assert expected_rows(OFFER) == [
        {"requirement": "C#", "category": "required_skill"},
        {"requirement": "Maîtrise de SQL Server", "category": "required_skill"},
        {"requirement": "Docker", "category": "preferred_skill"},
        {"requirement": "Kubernetes", "category": "technology"},
        {"requirement": "Concevoir des API REST", "category": "responsibility"},
    ]


def test_expected_rows_ignores_missing_lists():
    assert expected_rows({"technologies": ["Go"]}) == [{"requirement": "Go", "category": "technology"}]


def test_row_key_ignores_case_accents_spacing_and_trailing_punctuation():
    assert row_key("  Maîtrise   de C# .") == row_key("maitrise de c#")


def test_exact_rows_have_no_problems():
    matches = [{**r, "match_type": "gap"} for r in expected_rows(OFFER)]
    assert coverage_problems(OFFER, matches) == []


def test_missing_extra_duplicate_and_wrong_category_are_reported():
    matches = [
        {"requirement": "C#", "category": "required_skill"},
        {"requirement": "c#", "category": "required_skill"},              # duplicate row
        {"requirement": "Docker", "category": "technology"},              # wrong category
        {"requirement": "Kubernetes, Docker", "category": "technology"},  # merged items: not an item
    ]
    problems = coverage_problems(OFFER, matches)
    assert any("matches[1] 'c#' duplicates matches[0]" in p for p in problems)
    assert any("'Docker' has category 'technology', expected 'preferred_skill'" in p for p in problems)
    assert any("'Kubernetes, Docker' is not an item" in p for p in problems)
    missing = [p for p in problems if p.startswith("no row for")]
    assert len(missing) == 3  # SQL Server, Kubernetes, Concevoir des API REST


def test_match_rows_command_prints_the_rows(tmp_path, capsys):
    prep = tmp_path / "run" / "_prep"
    prep.mkdir(parents=True)
    (prep / "job_offer_analysis.json").write_text(json.dumps(OFFER, ensure_ascii=False), encoding="utf-8")
    cmd_match_rows(None, Namespace(target=str(tmp_path / "run")))
    assert json.loads(capsys.readouterr().out) == expected_rows(OFFER)


# A technology a skill item already names gets no row (2026-11-17 comparison runs:
# "Jira, Confluence" plus "Jira" and "Confluence" scored one fact three times).
ABSORBING = {
    "required_skills": ["Jira, Confluence", "Vibe coding avec des outils comme Replit ou Claude",
                        "API design and lifecycle management"],
    "preferred_skills": ["Strong expertise in Java", "C# / .NET"],
    "technologies": ["Jira", "Confluence", "Replit", "Claude", "APIs", "Java", "JavaScript", "C", "Python"],
    "responsibilities": ["Write Python scripts"],
}


def test_technology_named_in_a_skill_item_gets_no_row():
    assert absorbed_technologies(ABSORBING) == {"jira", "confluence", "replit", "claude", "apis", "java"}
    techs = [r["requirement"] for r in expected_rows(ABSORBING) if r["category"] == "technology"]
    # "java" is not in "javascript", "c" is not in "c#", and a responsibility absorbs nothing
    assert techs == ["JavaScript", "C", "Python"]


def test_rows_without_the_absorbed_technologies_have_no_problems():
    matches = [{**r, "match_type": "gap"} for r in expected_rows(ABSORBING)]
    assert coverage_problems(ABSORBING, matches) == []
    extra = matches + [{"requirement": "Jira", "category": "technology", "match_type": "direct"}]
    assert any("'Jira' is not an item" in p for p in coverage_problems(ABSORBING, extra))


def test_spacing_around_a_slash_does_not_matter():
    offer = {"preferred_skills": ["No-code tools (Claude Cowork/skills, Make, etc.)"],
             "technologies": ["Claude Cowork / skills", "Make"]}
    assert absorbed_technologies(offer) == {"claude cowork/skills", "make"}
