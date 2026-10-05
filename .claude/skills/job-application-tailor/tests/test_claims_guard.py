"""Regression tests for scripts/claims_guard.py (anti-exaggeration guard)."""
from __future__ import annotations

from scripts.claims_guard import calibration_bullets, check, _norm

MASTER = _norm("Python (lecture/adaptation de scripts)\nC#, WinForms, WPF\nstand-ups quotidiens\nSQL Server, PostgreSQL\nGitLab, GitHub")
FAMILIAR = ["Docker", "RabbitMQ", "CI/CD", "ASP .Net Core"]


def run(cv=None, letter=None, offer=None, addendum=""):
    docs = {"tailored_cv.json": cv or {}, "letter.json": letter or {}}
    return check(None, MASTER, FAMILIAR, addendum, docs, offer or {})


def test_intensity_wording_is_flagged():
    errs = run(cv={"summary_paragraphs": ["Pratique quotidienne de WCF"]})
    assert any(e.startswith("[intensity]") for e in errs)


def test_intensity_wording_present_in_source_is_allowed():
    assert run(cv={"experience": [{"bullets": ["Mise en place de stand-ups quotidiens"]}]}) == []


def test_familiar_skill_outside_familiar_section_is_flagged():
    cv = {"skills_sections": [{"heading": "Outils", "items": ["Docker"]}]}
    assert any(e.startswith("[familiar]") for e in run(cv=cv))


def test_familiar_skill_in_familiar_section_is_ok():
    cv = {"skills_sections": [{"heading": "Familier / à approfondir", "items": ["Docker", "RabbitMQ"]}]}
    assert run(cv=cv) == []


def test_unsourced_skill_flagged_and_sourced_ok():
    cv = {"skills_sections": [{"heading": "Langages", "items": ["C#", "Oracle"]}]}
    errs = run(cv=cv)
    assert len(errs) == 1 and "Oracle" in errs[0]


def test_python_must_keep_qualifier():
    cv = {"skills_sections": [{"heading": "Langages", "items": ["Python"]}]}
    assert any(e.startswith("[calibration]") for e in run(cv=cv))
    cv = {"skills_sections": [{"heading": "Langages", "items": ["Python (lecture/adaptation de scripts)"]}]}
    assert run(cv=cv) == []


def test_familiar_skill_in_letter_flagged():
    assert any(e.startswith("[familiar]") for e in run(letter={"paragraphs": ["J'utilise Docker."]}))


def test_jd_contagion_flagged():
    errs = run(cv={"summary_paragraphs": ["Expert Azure DevOps"]}, offer={"technologies": ["Azure DevOps", "C#"]})
    assert any(e.startswith("[jd-contagion]") for e in errs)


def test_calibration_bullets_parsed():
    txt = "## Skill calibration (x)\n\nintro\n\n- **WCF** a\n- **WPF** b\n\n## Hidden skills\n- z"
    assert calibration_bullets(txt) == ["**WCF** a", "**WPF** b"]


def test_jd_tech_named_as_an_admitted_gap_is_allowed():
    letter = {"paragraphs": ["Je n'ai pas d'expérience Azure DevOps."]}
    assert run(letter=letter, offer={"technologies": ["Azure DevOps"]}) == []


def _earlier(meta, bullet, extra=None):
    exp = [{"role_line": "Expériences antérieures", "metadata_line": meta, "bullets": [bullet]}]
    if extra:
        exp.insert(0, extra)
    return {"experience": exp}


def test_earlier_line_with_one_clause_per_employer_passes():
    cv = _earlier("Peaktime SAS | JFC Informatique & Média (Asnières) | ROCC Computers Ltd",
                  "Parcours en C et C++. Peaktime : logiciel TV. JFC : radio. ROCC : OS propriétaire.",
                  {"role_line": "X", "metadata_line": "JFC Informatique & Média (Kantar) | Paris | 2002", "bullets": []})
    assert run(cv=cv) == []


def test_earlier_line_missing_clause_flagged():
    cv = _earlier("Peaktime SAS | ROCC Computers Ltd", "Développement C++ et C sous Unix, assembleur.")
    assert any(e.startswith("[earlier-line]") for e in run(cv=cv))


def test_earlier_line_same_name_as_full_entry_must_be_disambiguated():
    cv = _earlier("JFC Informatique & Média", "JFC : radio.",
                  {"role_line": "X", "metadata_line": "JFC Informatique & Média (Kantar) | Paris | 2002", "bullets": []})
    assert any("disambiguator" in e for e in run(cv=cv))


def test_jd_tech_named_as_something_to_learn_is_allowed():
    letter = {"paragraphs": ["La cryptographie reste à apprendre."]}
    assert run(letter=letter, offer={"technologies": ["Cryptographie"]}) == []


def test_jd_tech_in_a_sentence_with_nouveau_is_still_flagged():
    letter = {"paragraphs": ["J'ai déployé Kubernetes sur un nouveau projet."]}
    assert any(e.startswith("[jd-contagion]") for e in run(letter=letter, offer={"technologies": ["Kubernetes"]}))
