"""Shared negation helper: a negated clause is never evidence for a skill.

Used by:
- claims_guard.py — addendum text is a SOURCE for the claims check only where
  it is affirmative ("No Kubernetes in this role" must not source
  Kubernetes); also the rule-6 gap-admission exemption.
- _grounding_common.py — fact-base prose (experience details, including the
  addendum bullets merged into them, summary, off-CV facts) grounds a match /
  role claim only through its affirmative clauses.

Semantics (one definition, so the checks cannot drift):

- Text is split into sentences (line breaks, ``.``/``!``/``?`` followed by
  whitespace, ``;``) and each sentence into clauses on ``,`` ``;`` ``:``,
  spaced dashes (`` — `` `` – `` `` - ``) and parentheses.
- A clause is *negated* when it contains a negation or gap word (pas, jamais,
  ne, n', ni, non, aucun, sans, no, not, never, without, n't, ...; "à
  apprendre", "reste à", "to learn", ...). A negation word directly followed
  by a hyphen is part of a compound, not a negation: "no-code", "non-profit",
  "pas-à-pas".
- Only negated clauses are dropped; the rest of the sentence stays evidence.
  Two cases where the negation predicates something outside its own clause
  extend it to that short subject (at most ``SHORT_ITEM_WORDS`` words each):
  * a subject list - "Razor, Blazor are not used": the negated clause does
    not start with the negation, so the comma-separated items just before it
    are negated too ("Delphi, never Razor" stays a contrast: Delphi is kept);
  * a label - "Kubernetes: never used" / "Kubernetes — not in this role": a
    clause that starts with the negation right after ``:`` or a spaced dash
    also negates the label before it (and that label's comma list).
- ``affirmative_sentences`` is the sentence-scope variant for rule text, where
  a whole sentence carrying a negation is dropped. claims_guard uses it for the
  addendum's "Skill calibration" section; "Hidden skills" bullets are never
  filtered.

Matching is accent- and case-insensitive; returned clauses keep their
original spelling.
"""
from __future__ import annotations

import re
import unicodedata

# Negation / gap-admission words, matched on folded text (lowercase, accents
# stripped, typographic apostrophe -> '). `(?![\w-])` keeps compounds such as
# "no-code" / "non-" from counting as negations.
NEGATION_RE = re.compile(
    r"(?<![\w-])(?:"
    r"pas|jamais|ne|ni|non|aucun(?:e|s|es)?|sans|"
    r"no|not|never|without|none|nor|"
    r"a apprendre|reste a|a developper|se developper|novice|to learn"
    r")(?![\w-])"
    r"|(?<![\w-])n'(?=[a-z])"      # French elision: n'est, n'ai, n'utilise
    r"|\wn't\b"                    # English contraction: don't, isn't, wasn't
)

SHORT_ITEM_WORDS = 4

_SENTENCE_SPLIT = re.compile(r"\n|;|(?<=[.!?])[*_)\]'\"»]*\s+")
_CLAUSE_SPLIT = re.compile(r"(,|;|:|\(|\)|\[|\]|\s[—–-]\s)")
_LEADING_CONJ = re.compile(r"^(?:et|and|mais|but|ou|or)\s+")
_STRIP = " \t*_\"'«»`"
_BULLET = re.compile(r"^\s*[-*+]\s+")


def fold(text: str) -> str:
    """Lowercase, strip accents, normalise apostrophes — for matching only."""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return s.replace("’", "'").replace("‘", "'")


def is_negated(text: str) -> bool:
    """True when ``text`` (a clause or a sentence) contains a negation / gap word."""
    return NEGATION_RE.search(fold(text)) is not None


def _starts_negated(clause: str) -> bool:
    """True when the negation is in the clause's first word ("pas X", "never X")."""
    s = _LEADING_CONJ.sub("", fold(clause).strip(_STRIP))
    m = NEGATION_RE.search(s)
    return m is not None and m.start() < len(s.split(" ", 1)[0])


def _is_short(clause: str) -> bool:
    return 0 < len(clause.split()) <= SHORT_ITEM_WORDS


def _sentence_clauses(sentence: str) -> list[tuple[str, str]]:
    """``(separator_before, clause)`` pairs; empty clauses are dropped."""
    parts = _CLAUSE_SPLIT.split(_BULLET.sub("", sentence))
    out: list[tuple[str, str]] = []
    sep = ""
    for i, piece in enumerate(parts):
        if i % 2:  # captured separator
            sep = piece.strip() or "-"
            continue
        clause = piece.strip(_STRIP)
        if clause:
            out.append((sep, clause))
            sep = ""
    return out


def _clause_flags(items: list[tuple[str, str]]) -> list[bool]:
    """Negated flag per clause, with the subject-list / label extensions."""
    own = [is_negated(c) for _, c in items]
    flags = list(own)

    def negate_list_before(j: int) -> None:
        # items[j] is negated; extend over the comma-separated short items before it
        while j > 0 and items[j][0] == "," and _is_short(items[j - 1][1]):
            flags[j - 1] = True
            j -= 1

    for i, (sep, clause) in enumerate(items):
        if not own[i]:
            continue
        if not _starts_negated(clause):
            negate_list_before(i)                        # "Razor, Blazor are not used"
        elif i > 0 and sep in (":", "—", "–", "-") and _is_short(items[i - 1][1]):
            flags[i - 1] = True                          # "Kubernetes: never used"
            negate_list_before(i - 1)
    return flags


def split_clauses(text: str) -> list[str]:
    """Split ``text`` into sentences, then clauses; empty pieces are dropped."""
    return [c for s in _SENTENCE_SPLIT.split(text) if s for _, c in _sentence_clauses(s)]


def affirmative_clauses(text: str) -> list[str]:
    """The clauses of ``text`` that are not negated (usable as evidence)."""
    out: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if not sentence:
            continue
        items = _sentence_clauses(sentence)
        out.extend(c for (_, c), neg in zip(items, _clause_flags(items)) if not neg)
    return out


def affirmative_sentences(text: str) -> list[str]:
    """Sentence-scope variant: drop every sentence that contains a negation.

    For rule text (the addendum's "Skill calibration" section), where a rule
    names its subject several clauses away from the negation ("Kafka —
    evaluated, not adopted"; "JDBC + jOOQ, never Hibernate"). Clause scope
    would keep the subject as evidence there.
    """
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip() and not is_negated(s)]


def affirmative_text(text: str, sep: str = "\n") -> str:
    """``text`` with every negated clause removed, clauses joined by ``sep``."""
    return sep.join(affirmative_clauses(text))
