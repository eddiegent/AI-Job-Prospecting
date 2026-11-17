"""Cold flow: does the opening hook match across the letter, LinkedIn and dossier?

The cold-prospect SKILL.md calls mismatched hooks "the most preventable
cold-flow mistake" and asks for an alignment check by hand. This measures it:
distinctive words (five letters or more, first six kept, stopwords and the
company's own name removed) shared by the letter's first paragraph and the
first connection request.

Calibrated on the five cold packs with a dossier (2026-11-17): aligned hooks
shared 5-12 such words; hooks taken from two different packs shared 0-4. Five
packs is a thin base and a drift within the same company would share more
words than a cross-company pair, so `gate dossier` reports a low overlap as a
warning to check by eye, never as a failure.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

HOOK_MIN_SHARED = 5

STOPWORDS = frozenset("""avec dans pour votre vous nous notre leurs cette comme aussi plus mais tres bien entre depuis
sans chez sont etre avoir fait faire leur elle elles ils mon mes ses ces tout tous toute toutes
about with your their there which would could from have this that what when where these those into
over more just than them they then been were will also very""".split())


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def hook_words(text: str, company: str = "") -> set[str]:
    company_words = {w[:6] for w in re.findall(r"[a-z]{4,}", _norm(company))}
    return {w[:6] for w in re.findall(r"[a-z]{5,}", _norm(text))
            if w not in STOPWORDS and w[:6] not in company_words}


def first_connection_request(linkedin: dict[str, Any]) -> str:
    variants = linkedin.get("variants") or []
    for v in variants:
        if (v.get("subject_hint") or "").strip().lower().startswith("connection request"):
            return v.get("message", "")
    return variants[0].get("message", "") if variants else ""


def hook_alignment(letter: dict[str, Any], linkedin: dict[str, Any], company: str) -> tuple[int, set[str]]:
    """``(shared word count, shared words)`` between the letter's opening
    paragraph and the first connection request."""
    paragraphs = letter.get("paragraphs") or [""]
    shared = hook_words(paragraphs[0], company) & hook_words(first_connection_request(linkedin), company)
    return len(shared), shared
