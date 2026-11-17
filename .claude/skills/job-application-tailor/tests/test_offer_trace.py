"""Tests for scripts/offer_trace.py and the `gate offer` check built on it.

Cases are the real misses found on 2026-11-17 in the packs since June."""
from __future__ import annotations

import json
from argparse import Namespace

import pytest

from scripts.commands.gate import cmd_gate
from scripts.offer_trace import language_mismatch, raw_language, untraced_technologies

EDENRED = ("As a Backend .Net Developer, you will be entrusted with building, testing, and maintaining "
           "high-quality .Net APIs and services that integrate with our partners. Docker and Azure DevOps.")


def _untraced(techs, raw):
    return untraced_technologies({"technologies": techs}, raw)


def test_inferred_technologies_are_flagged():
    # the offer says ".Net APIs": C# and REST were inferred
    assert _untraced([".NET", "Docker", "Azure DevOps", "C#", "REST APIs"], EDENRED) == ["C#", "REST APIs"]


@pytest.mark.parametrize("tech, raw", [
    ("Power BI", "Maîtrise de PowerBI serait appréciable"),          # spacing
    ("OpenAI", "Copilot Studio, Open AI."),                          # spacing
    ("REST APIs", "Vous concevez des API REST robustes."),           # word order + plural
    ("LLMs", "Experience with LLM orchestration"),                   # plural
    ("Make / Zapier", "Outils : Zapier et Make."),                   # a list item, token by token
    ("Développement .NET", "Developpement .net sur Azure"),          # accents and case
])
def test_spelling_variants_are_traced(tech, raw):
    assert _untraced([tech], raw) == []


@pytest.mark.parametrize("tech, raw", [
    ("GitHub Copilot", "IA générative (OpenAI, Copilot, Gemini, etc.)"),  # made more specific
    ("JavaScript", "Stack JS/TS (React, Node.js)"),                      # expanded
    ("Agents IA", "You will build AI agents for our clients."),          # translated
])
def test_specified_expanded_or_translated_names_are_flagged(tech, raw):
    assert _untraced([tech], raw) == [tech]


def test_language_mismatch_only_for_an_english_text_analysed_as_french():
    english = "We are looking for an engineer who will be part of our team and you will work on the platform " * 2
    french = "Nous recherchons un ingénieur pour notre équipe et vous serez dans le projet avec nous " * 2
    assert raw_language(english) == "en" and raw_language(french) == "fr"
    assert raw_language("Short text.") is None
    assert language_mismatch({"detected_language": "fr"}, english)
    assert language_mismatch({"detected_language": "en"}, english) is None
    assert language_mismatch({"detected_language": "fr"}, french) is None
    msg = language_mismatch({"detected_language": "fr"}, english + " French is not required.")
    assert "French is not required" in msg and "confirm the pack language" in msg


# ---------------------------------------------------------------- gate offer

@pytest.fixture
def run(tmp_path):
    prep = tmp_path / "14072026-role" / "_prep"
    prep.mkdir(parents=True)
    return prep


def _offer(techs, lang="en"):
    return {"job_title": "Dev", "company_name": "Acme", "required_skills": [], "preferred_skills": [],
            "responsibilities": [], "technologies": techs, "ats_keywords": [], "detected_language": lang}


def _gate(prep, capsys):
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage="offer", folder=str(prep.parent), cv=None))
    return e.value.code, capsys.readouterr().out


def test_gate_offer_blocks_an_untraced_technology(run, capsys):
    (run / "job_offer_analysis.json").write_text(json.dumps(_offer([".NET", "C#"])), encoding="utf-8")
    (run / "raw_offer.md").write_text(EDENRED, encoding="utf-8")
    code, out = _gate(run, capsys)
    assert code == 1
    assert "technologies: 'C#' is not named in raw_offer.md" in out


def test_gate_offer_passes_without_a_cached_offer(run, capsys):
    (run / "job_offer_analysis.json").write_text(json.dumps(_offer(["C#"])), encoding="utf-8")
    code, out = _gate(run, capsys)
    assert code == 0, out
    assert "no raw_offer.md - not checked" in out


def test_gate_offer_warns_on_language_but_passes(run, capsys):
    (run / "job_offer_analysis.json").write_text(json.dumps(_offer([".NET"], lang="fr")), encoding="utf-8")
    (run / "raw_offer.md").write_text(EDENRED + " You will join our team and we are in Paris. " * 3,
                                      encoding="utf-8")
    code, out = _gate(run, capsys)
    assert code == 0, out
    assert "[WARN] offer analysis vs raw_offer.md" in out and "reads as English" in out
