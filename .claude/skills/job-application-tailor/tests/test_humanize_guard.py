"""Tests for scripts/humanize_guard.py - the comparison of a letter or LinkedIn
file after the humanizer pass with the snapshot of its draft.

The cases come from the 2026-11-17 reruns: an invented sentence in a short
letter, and subject lines / LinkedIn subject hints edited although the pass is
told to leave them alone."""
from __future__ import annotations

import copy

import pytest

from scripts.humanize_guard import changed_fields, compare, names, new_sentences, numbers

DRAFT_LETTER = {
    "greeting": "Bonjour,",
    "subject_line": "Candidature - Développeur .Net IA",
    "paragraphs": [
        "Votre offre de Développeur .Net IA m'a arrêté sur une ligne : utiliser GitHub Copilot, "
        "mais savoir relire et valider le code généré. Je vous propose donc ma candidature.",
        "Chez Oodrive, j'ai fait évoluer une suite de sauvegarde B2B qui tourne sur 17 000+ sauvegardes "
        "par jour. J'ai aussi remplacé ses communications WCF par gRPC. Les revues de code y étaient une "
        "vraie pratique d'équipe, pas une formalité.",
    ],
    "signoff": "Cordialement,",
    "name": "Alex Dupont",
}


def _final(**changes) -> dict:
    doc = copy.deepcopy(DRAFT_LETTER)
    doc.update(changes)
    return doc


def test_identical_file_only_warns_that_the_pass_may_not_have_run():
    errors, warnings = compare("letter.json", DRAFT_LETTER, copy.deepcopy(DRAFT_LETTER))
    assert errors == []
    assert len(warnings) == 1 and "identical to the draft" in warnings[0]


def test_real_style_rewrite_passes_clean():
    # the edits the pass really made on pack #159 (Andema)
    final = _final(paragraphs=[
        "Votre offre de Développeur .Net IA m'a retenu sur une ligne : utiliser GitHub Copilot en sachant "
        "relire et valider le code généré. Alors je vous propose ma candidature.",
        "Chez Oodrive, j'ai fait évoluer une suite de sauvegarde B2B qui tourne sur 17 000+ sauvegardes "
        "par jour. J'ai aussi remplacé ses communications WCF par gRPC. On y faisait de vraies revues de "
        "code en équipe.",
    ])
    assert compare("letter.json", DRAFT_LETTER, final) == ([], [])


@pytest.mark.parametrize("field,value", [
    ("subject_line", "Candidature : Développeur .Net IA"),
    ("greeting", "Bonjour Madame,"),
    ("signoff", "Bien cordialement,"),
])
def test_field_outside_the_prose_must_not_change(field, value):
    errors, _ = compare("letter.json", DRAFT_LETTER, _final(**{field: value}))
    assert len(errors) == 1 and f"the pass changed '{field}'" in errors[0]


def test_added_number_is_an_error_and_a_dropped_one_a_warning():
    final = _final(paragraphs=[DRAFT_LETTER["paragraphs"][0],
                               DRAFT_LETTER["paragraphs"][1].replace("17 000+", "45 000+")])
    errors, warnings = compare("letter.json", DRAFT_LETTER, final)
    assert any("the number 45000 is not in the draft" in e for e in errors)
    assert any("the number 17000 from the draft is gone" in w for w in warnings)


def test_same_number_in_another_notation_is_not_new():
    final = _final(paragraphs=[DRAFT_LETTER["paragraphs"][0],
                               DRAFT_LETTER["paragraphs"][1].replace("17 000+", "plus de 17000")])
    assert compare("letter.json", DRAFT_LETTER, final) == ([], [])


def test_added_name_is_an_error():
    final = _final(paragraphs=[DRAFT_LETTER["paragraphs"][0],
                               DRAFT_LETTER["paragraphs"][1] + " J'ai aussi travaillé avec Kubernetes chez Thales."])
    errors, _ = compare("letter.json", DRAFT_LETTER, final)
    assert any("the name 'Kubernetes'" in e for e in errors)
    assert any("the name 'Thales'" in e for e in errors)


def test_word_capitalised_because_it_now_opens_a_sentence_is_not_a_name():
    final = _final(paragraphs=["Utiliser GitHub Copilot, mais savoir relire et valider le code généré : votre "
                               "offre de Développeur .Net IA m'a arrêté sur cette ligne. Donc je vous propose "
                               "ma candidature.", DRAFT_LETTER["paragraphs"][1]])
    errors, _ = compare("letter.json", DRAFT_LETTER, final)
    assert errors == []


def test_invented_sentence_is_reported_as_a_warning():
    # the sentence the pass added to pack #167's short letter
    final = _final(paragraphs=[DRAFT_LETTER["paragraphs"][0],
                               DRAFT_LETTER["paragraphs"][1] + " L'ensemble pouvait ensuite fonctionner "
                               "durablement sans intervention."])
    errors, warnings = compare("letter.json", DRAFT_LETTER, final)
    assert errors == []
    assert len(warnings) == 1 and "shares few words with the draft" in warnings[0]


def test_names_ignores_sentence_openers_and_elided_articles():
    text = "L'équipe utilise gRPC. Elle travaille chez Oodrive : Paris reste proche. I'm fine."
    assert names(text) == {"gRPC", "Oodrive"}


def test_numbers_fold_thousands_separators():
    assert numbers("17 000+ sauvegardes, 80 % de moins, version 4.8") == {"17000", "80", "4.8"}


def test_new_sentences_needs_enough_content_words():
    draft = "Je développe des outils pour des équipes métier."
    assert new_sentences(draft, "Merci. Bien à vous.") == []  # too short to judge
    assert new_sentences(draft, "Je développe aussi des outils pour plusieurs équipes métier.") == []


def test_linkedin_only_the_message_may_change():
    draft = {"outreach_type": "cold", "variants": [
        {"target": "hiring_manager", "contact_name": "Ana Roy", "subject_hint": "Connection request",
         "message": "Bonjour Ana, votre équipe travaille sur des intégrations API."}]}
    final = copy.deepcopy(draft)
    final["variants"][0]["message"] = "Bonjour Ana, votre équipe travaille sur les intégrations API."
    assert compare("linkedin.json", draft, final) == ([], [])

    final["variants"][0]["subject_hint"] = "Connection"
    final["outreach_type"] = "warm"
    assert changed_fields("linkedin.json", draft, final) == ["outreach_type", "variants[0].subject_hint"]

    final["variants"].append({"target": "recruiter", "message": "Bonjour."})
    assert "variants (count 1 -> 2)" in changed_fields("linkedin.json", draft, final)
