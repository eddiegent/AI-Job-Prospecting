"""Guard for the humanizer pass (prompts/humanize_pass.md).

The pass rewrites the style of the letters and LinkedIn messages. It must not
change what they say. This module compares a file after the pass with the
snapshot of its draft taken before it (``cli.py gate letters|linkedin --draft``
saves the snapshot in ``_prep/pre_humanize/``).

Why it exists: on 2026-11-17, three packs were rerun with the pass. One short
letter came back with a sentence the fact base does not support ("L'équipe
pouvait ensuite s'y retrouver sans moi"), and two runs edited fields the pass
is told to leave alone (subject line, LinkedIn subject hints). Every gate
passed.

Blocking (errors):
- a field outside the prose changed (anything but a letter's ``paragraphs`` or
  a LinkedIn variant's ``message``), or variants were added / removed;
- a number appears in the prose that the draft did not have;
- a name appears that the draft did not have: a capitalised word that does not
  open a sentence, or a word with an inner capital ("gRPC", "PostgreSQL").

Non-blocking (warnings):
- a number from the draft is gone (the pass may cut, but should keep facts);
- a sentence shares few words with the draft: likely new content, to be
  checked against the fact base or cut.

The comparison is with the draft, not with the CV: the claims check
(``claims_guard.py``) is what ties the text to the sources.
"""
from __future__ import annotations

import re
from typing import Any

from scripts.claims_guard import _norm, figure_text

SNAPSHOT_DIR = "pre_humanize"

# A sentence with at least this many content words, of which less than this
# share is in the draft, is reported as new. Calibrated on the 2026-11-17 runs:
# real rewrites kept 0.6+ of their words; the invented sentence kept 0.25.
NEW_SENTENCE_MIN_WORDS = 4
NEW_SENTENCE_MAX_OVERLAP = 0.5
CONTENT_WORD_MIN_LEN = 5
STEM_LEN = 5

_TOKEN_RE = re.compile(r"[^\W\d_][\w.#+-]*", re.UNICODE)
_SENTENCE_END_RE = re.compile(r"[.!?:;\n]")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def prose(name: str, doc: dict[str, Any]) -> list[str]:
    """The strings the pass may rewrite."""
    if name == "linkedin.json":
        return [v.get("message", "") for v in doc.get("variants", []) if isinstance(v, dict)]
    return [p for p in doc.get("paragraphs", []) if isinstance(p, str)]


def changed_fields(name: str, draft: dict[str, Any], final: dict[str, Any]) -> list[str]:
    """Names of the fields outside the prose that differ between draft and final."""
    out: list[str] = []
    prose_key = "variants" if name == "linkedin.json" else "paragraphs"
    for key in sorted(set(draft) | set(final)):
        if key != prose_key and draft.get(key) != final.get(key):
            out.append(key)
    if name == "linkedin.json":
        dv, fv = draft.get("variants", []), final.get("variants", [])
        if len(dv) != len(fv):
            out.append(f"variants (count {len(dv)} -> {len(fv)})")
        for i, (a, b) in enumerate(zip(dv, fv)):
            for key in sorted(set(a) | set(b)):
                if key != "message" and a.get(key) != b.get(key):
                    out.append(f"variants[{i}].{key}")
    return out


def numbers(text: str) -> set[str]:
    """Every number in the text, thousands separators removed."""
    return set(_NUMBER_RE.findall(figure_text(_norm(text))))


def _tokens(text: str) -> list[tuple[str, bool]]:
    """``(token, opens_a_sentence)`` pairs. An elided article or pronoun
    ("L'équipe", "J'ai") is its own token, so the word after it never counts
    as opening the sentence in its place."""
    out = []
    for m in _TOKEN_RE.finditer(text.replace("’", "'")):
        before = text[:m.start()].rstrip(" \t\"'«»()[]*_-–—")
        opens = not before or bool(_SENTENCE_END_RE.match(before[-1]))
        out.append((m.group(0).rstrip(".-+"), opens))
    return out


def names(text: str) -> set[str]:
    """Words that read as names: capitalised without opening a sentence, or
    carrying an inner capital. One-letter tokens are ignored ("I", "J'")."""
    found = set()
    for token, opens in _tokens(text):
        if len(token) < 2:
            continue
        if any(c.isupper() for c in token[1:]) or (token[0].isupper() and not opens):
            found.add(token)
    return found


def _stems(text: str) -> list[str]:
    words = re.findall(r"[a-z][a-z'-]*", _norm(text))
    return [w[:STEM_LEN] for w in words if len(w) >= CONTENT_WORD_MIN_LEN]


def new_sentences(draft_text: str, final_text: str) -> list[str]:
    """Sentences of the final text that share few content words with the draft."""
    known = set(_stems(draft_text))
    out = []
    for sentence in _SENTENCE_SPLIT_RE.split(final_text):
        stems = _stems(sentence)
        if len(stems) < NEW_SENTENCE_MIN_WORDS:
            continue
        overlap = sum(1 for s in stems if s in known) / len(stems)
        if overlap < NEW_SENTENCE_MAX_OVERLAP:
            out.append(sentence.strip())
    return out


def _all_strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)


def compare(name: str, draft: dict[str, Any], final: dict[str, Any]) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` for one file after the humanizer pass."""
    errors: list[str] = []
    warnings: list[str] = []

    for field in changed_fields(name, draft, final):
        errors.append(f"{name}: the pass changed '{field}' - only the prose may change "
                      f"(a letter's paragraphs, a LinkedIn message); restore it from the draft")

    draft_prose, final_prose = "\n".join(prose(name, draft)), "\n".join(prose(name, final))
    if draft_prose == final_prose:
        return errors, warnings

    draft_numbers, final_numbers = numbers(draft_prose), numbers(final_prose)
    for n in sorted(final_numbers - draft_numbers):
        errors.append(f"{name}: the number {n} is not in the draft - the pass must not add figures")
    for n in sorted(draft_numbers - final_numbers):
        warnings.append(f"{name}: the number {n} from the draft is gone - keep every fact unless it had to be cut")

    # a word the draft has in any spelling of its case is not new ("Côté" / "côté")
    known = {t.casefold() for s in _all_strings(draft) for t, _ in _tokens(s)}
    for n in sorted(names(final_prose)):
        if n.casefold() not in known:
            errors.append(f"{name}: the name '{n}' is not in the draft - the pass must not add people, "
                          f"companies or tools")

    for sentence in new_sentences(draft_prose, final_prose):
        warnings.append(f"{name}: this sentence shares few words with the draft - check it against the "
                        f"fact base or cut it: {sentence[:120]!r}")
    return errors, warnings
