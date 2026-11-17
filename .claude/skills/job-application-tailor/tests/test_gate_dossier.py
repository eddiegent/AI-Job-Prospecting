"""Tests for `gate dossier` (cold flow): dossier completeness and the hook
alignment warning (scripts/cold_hooks.py)."""
from __future__ import annotations

import json
from argparse import Namespace

import pytest

from scripts.cold_hooks import first_connection_request, hook_alignment, hook_words
from scripts.commands.gate import cmd_gate

SECTIONS = ["Quick Reference", "Company at a glance", "Why you, why them — angle of approach", "Who to contact",
            "Likely objections and prepared answers", "Conversation openers", "Interview prep — role-specific",
            "Transition narrative", "Research gaps"]

HOOK = ("Votre nouvelle génération de CRS pour Accor, connectée à des centaines de distributeurs, "
        "pose des défis d'intégration multi-canal que je connais bien.")


def _dossier(sections=SECTIONS, filler=900, links=4) -> str:
    parts = ["# Dossier de prospection — Acme"]
    for s in sections:
        parts += [f"## {s}", "x" * filler]
    parts += [f"- https://acme.example/source/{i}" for i in range(links)]
    return "\n\n".join(parts) + "\n"


def _run(tmp_path, dossier: str | None, letter_hook: str = HOOK, conn: str = HOOK):
    prep = tmp_path / "cold-14072026-acme" / "_prep"
    prep.mkdir(parents=True)
    if dossier is not None:
        (prep / "company_dossier.md").write_text(dossier, encoding="utf-8")
    (prep / "letter.json").write_text(json.dumps({"paragraphs": [letter_hook, "Suite."]}), encoding="utf-8")
    (prep / "linkedin.json").write_text(json.dumps({"variants": [
        {"subject_hint": "Direct message — post-acceptance", "message": "Unrelated follow-up text here."},
        {"subject_hint": "Connection request", "message": conn},
    ]}), encoding="utf-8")
    (prep / "company_profile.json").write_text(json.dumps({"company_name": "Acme"}), encoding="utf-8")
    return prep.parent


def _gate(folder, capsys):
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage="dossier", folder=str(folder), cv=None))
    return e.value.code, capsys.readouterr().out


def test_complete_dossier_with_aligned_hooks_passes(tmp_path, capsys):
    code, out = _gate(_run(tmp_path, _dossier()), capsys)
    assert code == 0, out
    assert "[PASS] company dossier completeness" in out
    assert "[PASS] hook alignment (letter / connection request):" in out


def test_french_headings_pass(tmp_path, capsys):
    fr = ["Référence rapide", "L'entreprise en un coup d'œil", "Pourquoi vous, pourquoi eux", "Qui contacter",
          "Objections probables", "Ouvertures de conversation", "Préparation entretien", "Récit de transition",
          "Lacunes de recherche"]
    code, out = _gate(_run(tmp_path, _dossier(sections=fr)), capsys)
    assert code == 0, out


def test_truncated_dossier_fails_with_every_reason(tmp_path, capsys):
    code, out = _gate(_run(tmp_path, _dossier(sections=SECTIONS[:4], filler=100, links=1)), capsys)
    assert code == 1
    assert "a complete dossier is 10,000+" in out
    assert "4 '## ' sections, expected 9" in out
    assert "no 'Research gaps' section" in out
    assert "1 source link(s)" in out


def test_missing_dossier_fails(tmp_path, capsys):
    code, out = _gate(_run(tmp_path, None), capsys)
    assert code == 1 and "company_dossier.md not found" in out


def test_drifted_hook_is_a_warning_not_a_failure(tmp_path, capsys):
    other = "Bonjour, je suis développeur senior et je cherche un nouveau poste à Lyon rapidement."
    code, out = _gate(_run(tmp_path, _dossier(), conn=other), capsys)
    assert code == 0, out
    assert "[WARN] hook alignment" in out and "regenerate the one that drifted" in out


def test_hook_words_ignore_the_company_name_and_short_words():
    assert hook_words("Acme Robotics builds robots for Acme clients", "Acme Robotics") == {"builds", "robots",
                                                                                            "client"}


def test_first_connection_request_prefers_the_connection_variant():
    li = {"variants": [{"subject_hint": "InMail", "message": "a"}, {"subject_hint": "Connection request", "message": "b"}]}
    assert first_connection_request(li) == "b"
    assert first_connection_request({"variants": [{"message": "c"}]}) == "c"
    assert hook_alignment({"paragraphs": [HOOK]}, {"variants": [{"message": HOOK}]}, "Acme")[0] >= 5
