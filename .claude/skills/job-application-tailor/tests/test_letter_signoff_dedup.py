"""Regression: the letter renderer must not emit the closing salutation twice.

Generators sometimes append the signoff (e.g. "Cordialement,") as the final body
paragraph AND also set the `signoff` field, which used to render the salutation
twice. generate_letter_docx now strips trailing closing-salutation / signoff-echo
/ sender-name paragraphs before appending the signoff block.
"""
from __future__ import annotations

import sys
from pathlib import Path

from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from docx_generator import generate_letter_docx  # noqa: E402

SETTINGS = {"formatting": {"font_name": "Calibri", "body_font_size_pt": 11}}


def _render(tmp_path, paragraphs):
    data = {
        "greeting": "Bonjour,",
        "paragraphs": paragraphs,
        "signoff": "Cordialement,",
        "name": "Edward Gent",
    }
    out = tmp_path / "letter.docx"
    generate_letter_docx(out, data, SETTINGS)
    return "\n".join(p.text for p in Document(str(out)).paragraphs)


def test_stray_signoff_paragraph_is_not_duplicated(tmp_path):
    txt = _render(tmp_path, ["Premier paragraphe.", "Je serais ravi d'en discuter.", "Cordialement,"])
    assert txt.count("Cordialement,") == 1
    assert txt.count("Edward Gent") == 1


def test_clean_letter_still_renders_signoff_once(tmp_path):
    txt = _render(tmp_path, ["Premier paragraphe.", "Je serais ravi d'en discuter."])
    assert txt.count("Cordialement,") == 1
    assert "Je serais ravi" in txt


def test_trailing_name_and_blank_paragraphs_are_trimmed(tmp_path):
    txt = _render(tmp_path, ["Corps du texte.", "Edward Gent", ""])
    assert txt.count("Edward Gent") == 1
    assert txt.count("Cordialement,") == 1
