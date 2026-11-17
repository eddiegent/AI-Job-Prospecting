"""Check the offer analysis against the cached offer text (`_prep/raw_offer.md`).

Why: the match rows are built from the offer analysis (scripts/match_rows.py),
so a technology the analysis adds becomes a scored row. Of the 103 offer packs
from 2026-06-01 to 2026-11-16, 14 listed a technology the offer never names:
"C#" and "REST APIs" for an offer that says ".Net APIs", "GitHub Copilot" for
one that says "Copilot", "JavaScript / TypeScript" for "JS/TS", "Agents IA"
for an English offer's "AI agents".

Two checks:

- ``untraced_technologies`` (blocking in ``gate offer``): every item of
  ``technologies`` must be found in the raw text - as written, with spaces or
  hyphens ignored ("PowerBI" = "Power BI"), through a known synonym, or word by
  word (each content word's first five letters, plural "s" ignored, so "API
  REST" covers "REST APIs" only when both words are there). The skill lists
  are not checked: they paraphrase the offer by design.
- ``language_mismatch`` (a warning): the raw text reads as English while
  ``detected_language`` is ``fr``. The analysis prompt flips to French on
  French-market signals because WebFetch can translate a French posting; the
  warning makes that flip visible, and stronger when the offer says French is
  not required.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from scripts._grounding_common import SYNONYMS, canonical, split_tokens

STOPWORDS = frozenset(
    "de des du la le les et en au aux un une of the and for in on with a an ou or dans pour par sur".split())
_FR_WORDS = frozenset("le la les des une et est pour avec vous nous dans sur sont du au aux ce cette votre vos "
                      "notre".split())
_EN_WORDS = frozenset("the and is for with you we in on are of to our your this that will be as an".split())
# Minimum function-word count before the raw text's language is judged at all.
LANGUAGE_MIN_WORDS = 15
_NO_FRENCH = re.compile(
    r"french (?:is )?not (?:required|mandatory|needed)|no french (?:required|needed)|"
    r"francais (?:n'est )?(?:pas|non) (?:requis|obligatoire|necessaire)", re.I)


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", s.replace("’", "'"))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9#+.]+", text)


def _stem(word: str) -> str:
    return word.strip(".").rstrip("s")[:5]


def _phrase_in(phrase: str, raw: str) -> bool:
    return re.search(r"(?<![\w])" + re.escape(phrase) + r"(?![\w])", raw) is not None


def _found(item: str, raw: str, raw_stems: set[str], raw_squeezed: str) -> bool:
    item_n = _norm(item).strip()
    if not item_n:
        return True
    content = [w for w in _words(item_n) if w not in STOPWORDS and len(w.strip(".")) >= 2]
    if content and all(_stem(w) in raw_stems for w in content):
        return True
    squeezed = re.sub(r"[\s-]+", "", item_n)
    if len(squeezed) >= 4 and squeezed in raw_squeezed:
        return True
    if _phrase_in(item_n, raw):
        return True
    canon = canonical(item)
    return any(_phrase_in(_norm(alias), raw) for alias in SYNONYMS.get(canon, [canon]))


def untraced_technologies(offer: dict[str, Any], raw_text: str) -> list[str]:
    """Items of ``offer['technologies']`` the raw offer text doesn't name."""
    raw = _norm(raw_text)
    raw_stems = {_stem(w) for w in _words(raw)}
    raw_squeezed = re.sub(r"[\s-]+", "", raw)
    out = []
    for item in offer.get("technologies") or []:
        if not isinstance(item, str) or _found(item, raw, raw_stems, raw_squeezed):
            continue
        # a list item ("Make / Zapier") is traced when each of its tokens is
        tokens = [t for t in split_tokens(item) if len(t.strip()) > 1]
        if tokens and len(tokens) > 1 and all(_found(t, raw, raw_stems, raw_squeezed) for t in tokens):
            continue
        out.append(item)
    return out


def raw_language(raw_text: str) -> str | None:
    """'fr' / 'en' by function-word counts, or None when the text is too short."""
    words = re.findall(r"[a-z']+", _norm(raw_text))
    fr = sum(w in _FR_WORDS for w in words)
    en = sum(w in _EN_WORDS for w in words)
    if fr + en < LANGUAGE_MIN_WORDS:
        return None
    return "fr" if fr > en else "en"


def language_mismatch(offer: dict[str, Any], raw_text: str) -> str | None:
    """A warning when the raw text is English but the analysis says French."""
    detected = offer.get("detected_language")
    if detected != "fr" or raw_language(raw_text) != "en":
        return None
    msg = ("raw_offer.md reads as English but detected_language is 'fr' - the pack will be in French. "
           "Fine if WebFetch translated a French posting (the analysis prompt's market-signal flip); "
           "say so to the user either way")
    if _NO_FRENCH.search(_norm(raw_text)):
        msg += ". The offer says French is not required: the team likely works in English - confirm the " \
               "pack language with the user before Step 4"
    return msg
