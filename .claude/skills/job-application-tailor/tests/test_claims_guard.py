"""Regression tests for scripts/claims_guard.py (anti-exaggeration guard)."""
from __future__ import annotations

import pytest

from scripts.claims_guard import (
    _norm,
    calibration_bullets,
    check,
    qualified_skills_from_rows,
    stack_hint_techs,
)

MASTER = _norm("Python (lecture/adaptation de scripts)\nC#, WinForms, WPF\nstand-ups quotidiens\nSQL Server, PostgreSQL\nGitLab, GitHub")
FAMILIAR = ["Docker", "RabbitMQ", "CI/CD", "ASP .Net Core"]
# Skills-table rows as the master-CV docx reader sees them (heading | items).
ROWS = [
    ["Langages", "C#, Python (lecture/adaptation de scripts)"],
    ["Architecture", "Clean Architecture (usage pragmatique), SOLID"],
]
QUALIFIED = qualified_skills_from_rows(ROWS)


def run(cv=None, letter=None, offer=None, addendum="", profile=None):
    docs = {"tailored_cv.json": cv or {}, "letter.json": letter or {}}
    return check(None, MASTER, FAMILIAR, addendum, docs, offer or {},
                 qualified=QUALIFIED, profile=profile)


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
    errs = run(cv=cv)
    assert errs == ["[calibration] tailored_cv.json: 'Python' must keep the master qualifier '(lecture/adaptation de scripts)'"]
    cv = {"skills_sections": [{"heading": "Langages", "items": ["Python (lecture/adaptation de scripts)"]}]}
    assert run(cv=cv) == []


def test_qualified_skills_derived_from_skills_table_items_only():
    rows = ROWS + [
        ["Python (heading cells are not items)", "C"],
        ["Divers", "R (stats), X (y)"],   # 1-char names are ignored
    ]
    assert qualified_skills_from_rows(rows) == {
        "Python": "lecture/adaptation de scripts",
        "Clean Architecture": "usage pragmatique",
    }


def test_any_master_qualified_skill_must_keep_its_qualifier():
    cv = {"skills_sections": [{"heading": "Méthodes", "items": ["clean architecture", "SOLID"]}]}
    errs = [e for e in run(cv=cv) if e.startswith("[calibration]")]
    assert errs == ["[calibration] tailored_cv.json: 'Clean Architecture' must keep the master qualifier '(usage pragmatique)'"]


def test_calibration_rule_is_not_user_specific():
    # Without a qualified-skills map, a bare "Python" is not a calibration error
    # even though the master text happens to contain "python (lecture".
    docs = {"tailored_cv.json": {"skills_sections": [{"heading": "Langages", "items": ["Python"]}]}}
    errs = check(None, MASTER, FAMILIAR, "", docs, {})
    assert not any(e.startswith("[calibration]") for e in errs)


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


# ----------------------------------------------------- rule 6, cold flow

PROFILE = {"tech_stack_hints": [
    "Kubernetes, Terraform (CI/CD, en bonus sur l'offre)",
    "C# / .NET — inferred from job listings",
]}


def test_stack_hint_techs_drop_annotations():
    assert stack_hint_techs(PROFILE) == ["Kubernetes", "Terraform", "C#", ".NET"]


def test_stack_contagion_flagged_when_no_offer():
    letter = {"paragraphs": ["J'ai déployé Kubernetes en production."]}
    errs = run(letter=letter, profile=PROFILE)
    assert len(errs) == 1 and errs[0].startswith("[stack-contagion] letter.json: 'Kubernetes'")


def test_stack_tech_that_is_in_master_cv_is_allowed():
    assert run(letter={"paragraphs": ["Développement en C#."]}, profile=PROFILE) == []


def test_stack_tech_named_as_a_gap_is_allowed():
    letter = {"paragraphs": ["Je n'ai pas encore utilisé Terraform."]}
    assert run(letter=letter, profile=PROFILE) == []


def test_offer_technologies_take_precedence_over_profile():
    letter = {"paragraphs": ["J'ai déployé Kubernetes en production."]}
    errs = run(letter=letter, offer={"technologies": ["Kubernetes"]}, profile=PROFILE)
    assert len(errs) == 1 and errs[0].startswith("[jd-contagion] letter.json:")


def test_run_check_reads_company_profile_in_cold_prep(tmp_path, monkeypatch):
    """run_check picks up company_profile.json when job_offer_analysis.json is absent."""
    import json

    from docx import Document

    from scripts.claims_guard import run_check

    master = tmp_path / "MASTER_CV.docx"
    doc = Document()
    doc.add_paragraph("Développeur C# senior.")
    t = doc.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "Langages"
    t.rows[0].cells[1].text = "C#, Python (lecture/adaptation de scripts)"
    doc.save(str(master))
    monkeypatch.setenv("JOB_TAILOR_HOME", str(tmp_path))

    prep = tmp_path / "_prep"
    prep.mkdir()
    (prep / "company_profile.json").write_text(json.dumps(PROFILE), encoding="utf-8")
    (prep / "letter.json").write_text(json.dumps(
        {"paragraphs": ["J'ai déployé Kubernetes en production."]}), encoding="utf-8")
    (prep / "tailored_cv.json").write_text(json.dumps(
        {"skills_sections": [{"heading": "Langages", "items": ["C#", "Python"]}]}), encoding="utf-8")

    errs = run_check(prep, master=master)
    assert any(e.startswith("[stack-contagion] letter.json: 'Kubernetes'") for e in errs)
    assert "[calibration] tailored_cv.json: 'Python' must keep the master qualifier '(lecture/adaptation de scripts)'" in errs


# ------------------------------------------- addendum prohibitions are not a source

def test_addendum_prohibition_does_not_source_the_forbidden_tech():
    cv = {"skills_sections": [{"heading": "Données", "items": ["Entity Framework"]}]}
    errs = run(cv=cv, addendum="Écrire SQL Server, jamais Entity Framework.")
    assert any(e.startswith("[unsourced-skill]") and "Entity Framework" in e for e in errs)


def test_addendum_positive_line_still_sources_a_skill():
    cv = {"skills_sections": [{"heading": "Desktop", "items": ["Delphi"]}]}
    assert run(cv=cv, addendum="- **Delphi — logiciels Telmar Peaktime.**") == []


def test_addendum_mixed_line_keeps_positive_sentence_drops_prohibition():
    addendum = ("- **Delphi — logiciels Telmar.** Ne pas l'étendre à Razor.\n"
                "- Razor, Azure DevOps ne sont pas dans le fact base.")
    cv = {"skills_sections": [{"heading": "Outils", "items": ["Delphi", "Razor", "Azure DevOps"]}]}
    errs = run(cv=cv, addendum=addendum)
    assert sorted(e.split("'")[3] for e in errs) == ["Azure DevOps", "Razor"]
    assert all(e.startswith("[unsourced-skill]") for e in errs)


def test_addendum_prohibition_does_not_exempt_jd_contagion():
    letter = {"paragraphs": ["J'ai utilisé Razor en production."]}
    errs = run(letter=letter, offer={"technologies": ["Razor"]},
               addendum="Razor n'est pas dans le fact base, ne jamais le reprendre.")
    assert any(e.startswith("[jd-contagion] letter.json: 'Razor'") for e in errs)


# ------------------------------------- addendum sections and clause-level negation

from scripts.claims_guard import addendum_source_text, familiar_items  # noqa: E402


def test_no_code_is_not_a_negation_in_the_addendum():
    cv = {"skills_sections": [{"heading": "Low-code", "items": ["Glide"]}]}
    addendum = "## Off-CV facts to remember\n- Comparé trois plateformes no-code, dont Glide."
    assert run(cv=cv, addendum=addendum) == []


def test_hidden_skills_bullets_are_never_filtered():
    bullet = "- Diagnostic d'un portage qui ne pouvait pas être livré sans équivalent VSS fiable."
    cv = {"skills_sections": [{"heading": "Systèmes", "items": ["VSS"]}]}
    assert run(cv=cv, addendum="## Hidden skills\n" + bullet) == []
    errs = run(cv=cv, addendum="## Off-CV facts to remember\n" + bullet)
    assert any(e.startswith("[unsourced-skill]") and "'VSS'" in e for e in errs)


def test_negation_drops_only_its_clause():
    src = addendum_source_text("## Additional experience entries\n### Acme — 2020\n"
                               "- Bases : PostgreSQL ; SQLite en local. Pas de SQL Server ici.")
    assert "postgresql" in src and "sqlite en local." in src
    assert "sql server" not in src


def test_skill_calibration_sentences_with_a_negation_are_dropped_whole():
    addendum = "## Skill calibration\n- **Kafka — évalué, pas retenu.** Go : usage quotidien."
    src = addendum_source_text(addendum)
    assert "kafka" not in src and "go : usage quotidien." in src


def test_jd_tech_in_an_affirmative_clause_of_a_contrast_is_flagged():
    letter = {"paragraphs": ["J'ai déployé Kubernetes, pas Terraform."]}
    errs = run(letter=letter, offer={"technologies": ["Kubernetes", "Terraform"]})
    assert [e.split("'")[1] for e in errs] == ["Kubernetes"]


def test_familiar_items_drop_tool_qualifiers_listed_elsewhere():
    rows = [["Outils", "GitHub, GitLab, Jira"],
            ["Familiar / to deepen", "Docker, GitHub / GitLab CI/CD, RabbitMQ / Kafka"]]
    assert familiar_items(rows) == ["Docker", "CI/CD", "RabbitMQ", "Kafka"]


# --------------------------------------------------- earlier-experience line

def test_earlier_line_accepts_english_colon_and_legal_suffixes():
    cv = _earlier("Globex SA | Initech GmbH", "Globex SA: built tools. Initech: payroll in C.")
    assert run(cv=cv) == []
    cv = _earlier("Globex SA | Initech GmbH", "Initech: payroll. Globex: built tools.")
    assert any("out of order" in e for e in run(cv=cv))


def test_earlier_line_messages_name_the_file_and_are_generic():
    cv = _earlier("Globex SA", "Built tools.")
    errs = run(cv=cv)
    assert errs == ["[earlier-line] tailored_cv.json: no 'Employer: ...' clause for 'Globex SA' "
                    "in the earlier-experience bullet"]
    cv = _earlier("Globex SA", "Globex : x.",
                  {"role_line": "X", "metadata_line": "Globex SA | Lyon | 2010", "bullets": []})
    assert any("'(<city>)'" in e for e in run(cv=cv))


# ------------------------------------------------------------- run_check(only=)

def _prep_with_cv_and_letter_problems(tmp_path, monkeypatch):
    import json

    from docx import Document

    master = tmp_path / "MASTER_CV.docx"
    doc = Document()
    doc.add_paragraph("Développeur C# senior.")
    doc.save(str(master))
    monkeypatch.setenv("JOB_TAILOR_HOME", str(tmp_path))
    prep = tmp_path / "_prep"
    prep.mkdir()
    (prep / "job_offer_analysis.json").write_text(json.dumps({"technologies": ["Kubernetes"]}), encoding="utf-8")
    (prep / "tailored_cv.json").write_text(json.dumps(
        {"skills_sections": [{"heading": "Langages", "items": ["C#", "Oracle"]}]}), encoding="utf-8")
    (prep / "letter.json").write_text(json.dumps({"paragraphs": ["J'ai déployé Kubernetes."]}), encoding="utf-8")
    (prep / "linkedin.json").write_text(json.dumps({"connection_request": "Bonjour"}), encoding="utf-8")
    return prep, master


def test_run_check_only_scopes_to_the_named_files(tmp_path, monkeypatch):
    from scripts.claims_guard import run_check

    prep, master = _prep_with_cv_and_letter_problems(tmp_path, monkeypatch)
    every = run_check(prep, master=master)
    assert any("tailored_cv.json:" in e for e in every) and any("letter.json:" in e for e in every)
    cv_only = run_check(prep, master=master, only=("tailored_cv.json",))
    assert cv_only and all("tailored_cv.json:" in e for e in cv_only)
    letters = run_check(prep, master=master, only=("letter.json", "short_letter.json"))
    assert letters == [e for e in every if " letter.json:" in e]
    assert run_check(prep, master=master, only=("linkedin.json",)) == []


# ---------------------------------------------------------------- rule 7: durations

DUR_MASTER = _norm("Ingénieur avec plus de 35 ans d'expérience, dont 15+ en C#/.NET. "
                   "Portage livré en production en 6 mois. "
                   "Development Manager | Telmar | Mars 2005 – Juin 2010")


def run_dur(text, offer=None, profile=None, addendum=""):
    return [e for e in check(None, DUR_MASTER, [], addendum, {"letter.json": {"paragraphs": [text]}},
                             offer or {}, profile=profile) if e.startswith("[duration]")]


def test_duration_stated_in_master_cv_passes():
    assert run_dur("Plus de 35 ans de développement, dont 15 ans de C#/.NET, livré en 6 mois.") == []


def test_spelled_out_duration_not_in_any_source_is_flagged():
    errs = run_dur("Trente ans de carrière dans le logiciel.")
    assert len(errs) == 1 and "'trente ans'" in errs[0] and "30-year" in errs[0]


def test_inflated_duration_is_flagged_with_the_sourced_values():
    errs = run_dur("J'ai passé 17 ans chez Oodrive.")
    assert len(errs) == 1 and "17-year" in errs[0] and "[5, 15, 35]" in errs[0]


def test_role_span_from_cv_dates_counts_as_a_source():
    # Telmar: Mars 2005 – Juin 2010 = 63 months -> 5 years.
    assert run_dur("Cinq ans chez Telmar sur des outils média.") == []


def test_month_and_year_units_are_kept_apart():
    errs = run_dur("Le portage a pris 6 ans.")
    assert len(errs) == 1 and "6-year" in errs[0]


def test_a_range_describes_a_requirement_and_is_skipped():
    assert run_dur("Votre offre demande 2 à 5 ans d'expérience ; je suis plus senior.") == []


def test_offer_duration_quoted_outside_the_first_person_passes():
    offer = {"responsibilities": ["Mission freelance de 24 mois"]}
    assert run_dur("Candidature — mission freelance 24 mois.", offer=offer) == []
    errs = run_dur("J'ai 24 mois d'expérience sur ce type de mission.", offer=offer)
    assert len(errs) == 1 and "24-month" in errs[0]


def test_addendum_duration_counts_as_a_source():
    add = "## Off-CV facts to remember\n- 30+ années de carrière technique en langue seconde.\n"
    assert run_dur("Trente ans de carrière.", addendum=add) == []


@pytest.mark.parametrize("text", [
    "Docker reste à apprendre de mon côté.",
    "Je n'ai pas encore utilisé RabbitMQ en production.",
    "Orchestration : Make en mission. Docker : pas encore pratiqué.",
])
def test_familiar_skill_named_as_a_gap_is_allowed(text):
    errs = run(letter={"paragraphs": [text]})
    assert not any(e.startswith("[familiar]") for e in errs), errs


@pytest.mark.parametrize("text", [
    "Je n'utilise que Docker pour mes déploiements.",
    "Non seulement Docker, mais aussi Kubernetes.",
    "Not only Docker but also RabbitMQ.",
    "J'utilise Docker, pas Kubernetes.",
])
def test_familiar_skill_claimed_despite_a_negation_word_is_flagged(text):
    assert any(e.startswith("[familiar]") for e in run(letter={"paragraphs": [text]}))


# ---------------------------------------------------------------- rule 8: figures
# The hole it closes: a tailored CV and letter saying "45 000+ sauvegardes" where
# the master CV says "17 000+", and an invented "équipe de 12 personnes", passed
# `gate cv` and `gate letters` (found 2026-11-17).

FIG_MASTER = _norm("Ingénieur avec plus de 35 ans d'expérience. "
                   "Suite de sauvegarde B2B : 17 000+ sauvegardes par jour, chiffrement AES-256. "
                   "Tri sur 300+ scénarios Make, dont environ 150 stabilisés. "
                   "Stockage saturé (95-98%), coûts réduits de 80 %. Bac+5.")


def run_fig(text, name="letter.json", offer=None, profile=None, addendum="", role_text=""):
    doc = {"variants": [{"message": text}]} if name == "linkedin.json" else {"paragraphs": [text]}
    if name == "tailored_cv.json":
        doc = {"experience": [{"role_line": "Dev", "metadata_line": "Acme | 2021 - 2025", "bullets": [text]}]}
    return [e for e in check(None, FIG_MASTER, [], addendum, {name: doc}, offer or {},
                             profile=profile, role_text=_norm(role_text)) if e.startswith("[figure]")]


@pytest.mark.parametrize("text", [
    "Une suite qui tourne sur 17 000+ sauvegardes par jour.",
    "A suite running 17,000+ backups a day.",          # English thousands separator
    "Une suite qui tourne sur 17000 sauvegardes.",       # no separator, no plus
    "J'ai stabilisé environ 150 scénarios sur plus de 300 recensés.",
    "Un stockage saturé à 98 %, et des coûts réduits de 80 %.",   # both ends of "95-98%" count
    "On me demande 2 à 5 ans d'expérience : j'en ai plus de 35.",  # elliptical duration
])
def test_figure_stated_in_the_master_cv_passes(text):
    assert run_fig(text) == []


@pytest.mark.parametrize("name", ["letter.json", "short_letter.json", "linkedin.json", "tailored_cv.json"])
def test_inflated_figure_is_flagged_in_every_file(name):
    errs = run_fig("Une suite qui tourne sur 45 000+ sauvegardes par jour.", name=name)
    assert len(errs) == 1 and "'45000'" in errs[0] and name in errs[0]


def test_invented_figure_is_flagged():
    errs = run_fig("Chez Acme, j'ai dirigé une équipe de 12 personnes.")
    assert len(errs) == 1 and "'12'" in errs[0]


def test_percentage_needs_a_percentage_in_the_source():
    # 150 is a count in the master CV, never a percentage
    errs = run_fig("J'ai réduit les incidents de 150 %.")
    assert len(errs) == 1 and "'150 %'" in errs[0]


@pytest.mark.parametrize("text", [
    "Lyon, le 17 novembre 2026.",
    "Available from November 17.",
    "Chez Acme de 2021 à 2025.",
    "Un appel de 20 minutes suffit, je suis à ~50 min de vos locaux.",
    "Disponible dès 9h30.",
    "Produit B2B, chiffrement AES-256, niveau Bac+5, support 24/7, version .NET8.",
    "C'était mon 1er projet.",
])
def test_dates_times_and_numbers_glued_to_a_name_are_not_figures(text):
    assert run_fig(text) == []


def test_figure_in_a_negated_clause_is_not_a_claim():
    assert run_fig("Je n'ai jamais administré Microsoft 365.") == []
    assert len(run_fig("J'ai administré Microsoft 365 pendant ce projet.")) == 1


def test_role_figure_may_be_quoted_outside_a_first_person_clause():
    research = "Acme compte 650 collaborateurs et accompagne plus de 1 000 entreprises."
    assert run_fig("Acme, avec ses 650 collaborateurs, est le type d'équipe que je recherche.",
                   role_text=research) == []
    # the same number claimed by the candidate is still a claim
    errs = run_fig("J'ai encadré 650 collaborateurs.", role_text=research)
    assert len(errs) == 1 and "'650'" in errs[0]


def test_count_copied_from_the_offer_into_a_first_person_clause_is_flagged():
    # figure contagion: the offer's team size turned into the candidate's own claim
    offer = {"responsibilities": ["Poste en 100 % présentiel, vous encadrez une équipe de 12 personnes"]}
    assert run_fig("Le 100 % présentiel me convient.", offer=offer) == []
    errs = run_fig("J'ai dirigé une équipe de 12 personnes.", offer=offer)
    assert len(errs) == 1 and "'12'" in errs[0]


def test_version_named_in_the_offer_may_be_quoted_in_the_first_person():
    offer = {"job_title": "Développeur .NET 4.8 / SQL Server 2022", "technologies": ["Microsoft 365"]}
    assert run_fig("J'ai postulé à votre offre de Développeur .NET 4.8 / SQL Server 2022.", offer=offer) == []
    assert run_fig("Je découvre Microsoft 365 avec intérêt.", offer=offer) == []
    # same number, but not after the name the offer gives it
    assert len(run_fig("J'ai livré 365 correctifs.", offer=offer)) == 1


def test_long_reference_number_from_the_offer_passes():
    offer = {"source_url": "https://candidat.francetravail.fr/offres/recherche/detail/8576883"}
    assert run_fig("Je me positionne sur votre offre 8576883.", offer=offer) == []
    assert len(run_fig("Je me positionne sur votre offre 8576884.", offer=offer)) == 1


def test_addendum_figure_counts_as_a_source():
    add = "## Off-CV facts to remember\n- Toolkit open source : 100+ candidatures traitées.\n"
    assert run_fig("Un toolkit qui a traité 100+ candidatures.", addendum=add) == []
    assert len(run_fig("Un toolkit qui a traité 100+ candidatures.")) == 1


def test_figures_outside_the_prose_fields_are_ignored():
    # contact details, addresses, dates and subject lines carry numbers that are not claims
    docs = {
        "tailored_cv.json": {"candidate_name": "A 9", "contact_line": "06 12 34 56 78 | 91800 Brunoy"},
        "letter.json": {"sender_address": ["12 rue de la Paix", "91800 Brunoy"], "date_line": "17/11/2026",
                        "subject_line": "Candidature - réf. 4242", "paragraphs": ["Bonjour."]},
        "linkedin.json": {"variants": [{"subject_hint": "Connection request (300 max)", "message": "Bonjour."}]},
    }
    assert [e for e in check(None, FIG_MASTER, [], "", docs, {}) if e.startswith("[figure]")] == []


# --- item 16 (2026-11-17): skills table, translations, caps, gap wording,
# intensity scope, interview-prep figures ------------------------------------

TABLE = _norm("Langages | C#, Python (lecture/adaptation de scripts)\n"
              "Architecture | Conception de systèmes distribués")
MASTER_WITH_BULLET = _norm("Langages | C#, Python (lecture/adaptation de scripts)\n"
                           "Architecture | Conception de systèmes distribués\n"
                           "Migration ponctuelle vers SharePoint en 2019")


def run16(cv=None, letter=None, addendum="", translations=None, caps=None, offer=None):
    docs = {"tailored_cv.json": cv or {}, "letter.json": letter or {}}
    return check(None, MASTER_WITH_BULLET, FAMILIAR, addendum, docs, offer or {}, qualified=QUALIFIED,
                 skills_table=TABLE, translations=translations, level_caps=caps)


def _skills(*items):
    return {"skills_sections": [{"heading": "Skills", "items": list(items)}]}


def test_a_tool_named_once_in_a_bullet_is_not_a_skills_source():
    errs = run16(cv=_skills("C#", "SharePoint"))
    assert len(errs) == 1 and "[unsourced-skill]" in errs[0] and "SharePoint" in errs[0]


def test_a_translated_skill_needs_the_addendum_pair():
    assert any("[unsourced-skill]" in e for e in run16(cv=_skills("Distributed systems design")))
    pairs = [("Conception de systèmes distribués", "Distributed systems design")]
    assert run16(cv=_skills("Distributed systems design"), translations=pairs) == []


def test_a_capped_skill_outside_the_skills_table_is_blocked_in_the_skills_section():
    errs = run16(cv=_skills("Supabase"), addendum="## Hidden skills\n- Supabase en formation\n",
                 caps=["Supabase", "Python"])
    assert any("[capped-skill]" in e and "Supabase" in e for e in errs)
    # Python is capped but in the table: listing it (with its qualifier) is fine
    assert run16(cv=_skills("Python (lecture/adaptation de scripts)"), caps=["Python"]) == []


def test_translation_and_cap_sections_are_rules_not_sources():
    addendum = "## Skill level caps\n- Stripe — vu en formation\n## Skill translations\n- Kafka = Kafka\n"
    errs = run16(cv=_skills("Stripe", "Kafka"), addendum=addendum)
    assert {e.split("'")[3] for e in errs if "[unsourced-skill]" in e} == {"Stripe", "Kafka"}


@pytest.mark.parametrize("text", [
    "Docker, je ne l'ai pratiqué qu'en formation.",
    "Je dois encore approfondir Docker.",
    "I have used Docker only in training.",
])
def test_familiar_skill_named_as_training_only_or_to_deepen_is_a_gap(text):
    assert not [e for e in run16(letter={"paragraphs": [text]}) if "[familiar]" in e]


def test_familiar_skill_claimed_plainly_is_still_flagged():
    assert any("[familiar]" in e for e in run16(letter={"paragraphs": ["J'utilise Docker en production."]}))


def test_intensity_about_the_reader_or_the_company_is_not_a_claim():
    letter = {"paragraphs": ["Vous êtes rattaché à Acme au quotidien ?", "Acme livre tous les jours."]}
    assert run16(letter=letter, offer={"company_name": "Acme"}) == []


def test_intensity_about_the_candidate_is_still_flagged_in_a_letter():
    errs = run16(letter={"paragraphs": ["J'utilise Claude Code au quotidien."]})
    assert any("[intensity]" in e for e in errs)


def test_intensity_matches_a_source_in_the_other_language():
    # MASTER has "stand-ups quotidiens"
    docs = {"tailored_cv.json": {"experience": [{"bullets": ["Ran daily stand-ups with the business teams"]}]}}
    assert check(None, MASTER, FAMILIAR, "", docs, {}) == []
    docs = {"tailored_cv.json": {"experience": [{"bullets": ["Used Claude Code daily"]}]}}
    assert any("[intensity]" in e for e in check(None, MASTER, FAMILIAR, "", docs, {}))


def _interview_prep(tmp_path, monkeypatch, md: str, summary=None):
    import json

    from docx import Document

    doc = Document()
    doc.add_paragraph("Développeur C# senior, 17 000+ sauvegardes par jour.")
    doc.save(str(tmp_path / "MASTER_CV.docx"))
    monkeypatch.setenv("JOB_TAILOR_HOME", str(tmp_path))
    prep = tmp_path / "_prep"
    prep.mkdir()
    (prep / "interview_prep.md").write_text(md, encoding="utf-8")
    (prep / "raw_offer.md").write_text("Equipe de 12 personnes, 650 collaborateurs.", encoding="utf-8")
    (prep / "match_analysis.json").write_text(json.dumps({
        "match_summary": summary or {"overall_fit_pct": 72.4, "direct_count": 2},
        "matches": [{"requirement": "C#", "category": "required_skill", "match_type": "direct"}]}),
        encoding="utf-8")
    return prep


def test_interview_prep_figures_come_from_a_source(tmp_path, monkeypatch):
    from scripts.claims_guard import interview_figure_errors

    md = "\n".join([
        "## Fit Score: 72% — GOOD",                                     # heading: skipped
        "## Quick Reference", "- Folder: 2026-11-17 #164", "## Talking points",
        "Tu as tenu 17 000+ sauvegardes par jour.",                       # master CV
        "L'équipe compte 12 personnes, sur 650 collaborateurs.",          # offer
        "Le score est de 72 % et passe le seuil de 70 %.",                # match analysis, threshold
        "**« Une migration de 20 000 utilisateurs. Comment faites-vous ? »**",  # question
        "Gérer les erreurs 429 avec un retry.",                           # HTTP code
        "Tu as récupéré 45 000 sauvegardes.",                             # invented
    ])
    errs = interview_figure_errors(_interview_prep(tmp_path, monkeypatch, md))
    assert len(errs) == 1 and "'45000'" in errs[0]
