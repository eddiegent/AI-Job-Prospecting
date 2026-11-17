"""Anti-exaggeration guard for generated application material.

Two subcommands:

``merge <prep_dir>``
    Mandatory step before tailoring. Builds ``<prep_dir>/cv_fact_base_merged.json``
    = cached fact base + user addendum (extra experience bullets, hidden skills,
    off-CV facts) + the addendum's "Skill calibration" bullets
    (``addendum_skill_calibration``) + the master CV's "Familier / a approfondir"
    row (``familiar_only_skills``). Prompts must read THIS file, so the addendum can
    no longer be silently skipped.

``check <prep_dir>``
    Deterministic post-check of tailored_cv.json / letter.json / short_letter.json /
    linkedin.json. Exit 1 on any ERROR. Rules:

    1. No intensity/frequency wording that no source supports
       ("quotidien", "au quotidien", "tous les jours", "daily", "every day").
    2. Skills listed as familiar-only in the master CV (e.g. Docker, RabbitMQ,
       CI/CD, Entity Framework) may appear in the skills section ONLY under the
       "Familier / a approfondir" heading, and never in tagline/summary/letters -
       except named as a gap, in a negated clause ("n8n reste à apprendre",
       "pas encore de Docker en production").
    3. Every item in a (non-familiar) skills section must appear literally in the
       master CV or the addendum - no invented skills. Negated addendum clauses
       ("never Hibernate", "no Go in this role") are not a source
       (``addendum_source_text``, negation semantics in ``scripts/_negation.py``);
       this also applies to rules 1 and 6.
    4. Calibration: any skill the master CV's skills table writes as
       ``Name (qualifier)`` must keep its qualifier - a tailored skills item equal
       to the bare ``Name`` is an error (qualified skills are derived from the
       master CV's table rows, see ``qualified_skills_from_rows``).
    5. Earlier-experience line: one clause ("Employer: ..." / "Employer : ...")
       per company named in its metadata_line, in the same order, and a company
       name that also appears in a full entry must be disambiguated.
    6. JD / stack contagion: a technology from job_offer_analysis.technologies
       (offer flow, ``[jd-contagion]``) - or, when there is no
       job_offer_analysis.json, from company_profile.tech_stack_hints (cold flow,
       ``[stack-contagion]``) - that is absent from master CV + addendum must not
       appear anywhere in the output, unless the sentence admits the gap.
    7. Durations: every "N ans / années / mois / years / months" (digits or
       spelled out: "trente ans") must match a duration the master CV or
       addendum states for that unit ("35+ ans", "dont 15+ en C#/.NET", "en
       6 mois"). A range ("2 à 5 ans") describes a requirement, not the
       candidate, and is skipped.
    8. Figures: every other number in the CV, in a letter's paragraphs or in a
       LinkedIn message must be one the master CV or addendum states - "45 000+
       sauvegardes" for a CV that says "17 000+" and an invented "équipe de 12
       personnes" both fail. A percentage needs a percentage in the source. Not
       claims: a figure in a negated clause, the role's own figure in a clause
       that isn't about the candidate, a number that follows the same name as
       in the offer / research (".NET 4.8"), a long reference number found
       there; years, dates and call / commute times are ignored.

Every message is ``[rule] <file>: ...`` so a gate can tell whose file failed.
``run_check(..., only=...)`` restricts the check to some of the four files
(``cli.py gate cv|letters|linkedin`` each check only their own stage's files).
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

INTENSITY_RE = re.compile(
    r"\b(au quotidien|quotidien(?:ne)?s?|tous les jours|every ?day|daily|day[- ]to[- ]day)\b",
    re.IGNORECASE,
)
FAMILIAR_HEADINGS = ("familier", "familiar")
DOC_NAMES = ("tailored_cv.json", "letter.json", "short_letter.json", "linkedin.json")
# Raw text about the role / company: its figures may be quoted back (rule 8).
ROLE_TEXT_NAMES = ("raw_offer.md", "company_research.md", "raw_research.md")
# Legal-form suffixes dropped from a company name before looking for its
# earlier-experience clause ("Globex SA" -> "Globex").
LEGAL_SUFFIXES = (
    "sa", "sas", "sasu", "sarl", "eurl", "sca", "scop", "snc", "ltd", "limited",
    "inc", "llc", "llp", "plc", "corp", "co", "gmbh", "ag", "kg", "bv", "nv",
    "srl", "spa", "sl", "ab", "as", "oy",
)
_LEGAL_SUFFIX_RE = re.compile(r"(?:[\s,]+(?:" + "|".join(LEGAL_SUFFIXES) + r")\.?)+$")


# Rule 7 - durations. Patterns run on _norm()-ed text (lowercase, no accents).
_UNITS = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12,
    "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
}
_UNIT_WORDS = "|".join(sorted(_UNITS, key=len, reverse=True))
_TENS_WORDS = "|".join(_TENS)
_NUMBER = (rf"\d+|(?:{_TENS_WORDS})(?:[- ](?:et[- ])?(?:{_UNIT_WORDS}))?|(?:{_UNIT_WORDS})")
_DURATION_RE = re.compile(
    rf"(?<![\w.,])(?P<num>{_NUMBER})\s*\+?\s*(?P<unit>annees?|ans?|mois|years?|yrs?|months?)(?![\w])"
)
# "2 a 5 ans", "3-5 years", "2 to 4 years", "deux ou trois ans": a range.
_RANGE_BEFORE_RE = re.compile(rf"(?:{_NUMBER})\s*(?:a|-|to|ou|or)\s*$")
# Source-only shorthand: "dont 15+ en C#/.NET" states 15 years.
_SOURCE_PLUS_EN_RE = re.compile(r"(?<![\w.,])(\d+)\s*\+\s*(?:en|in)\b")


def _number_value(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    parts = re.split(r"[- ](?:et[- ])?", token)
    if parts[0] in _TENS:
        return _TENS[parts[0]] + (_UNITS.get(parts[1], 0) if len(parts) > 1 else 0)
    return _UNITS.get(token)


def _unit_class(unit: str) -> str:
    return "month" if unit.startswith(("mois", "month")) else "year"


def durations(text_norm: str, *, skip_ranges: bool = True) -> list[tuple[int, str, str]]:
    """``(value, 'year'|'month', matched text)`` for each duration in normalised text."""
    out = []
    for m in _DURATION_RE.finditer(text_norm):
        if skip_ranges and _RANGE_BEFORE_RE.search(text_norm[max(0, m.start() - 40):m.start()]):
            continue
        value = _number_value(m.group("num"))
        if value is not None:
            out.append((value, _unit_class(m.group("unit")), m.group(0)))
    return out


_MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_WORDS = "|".join(_MONTHS)
_SPAN_RE = re.compile(rf"\b({_MONTH_WORDS}) (\d{{4}}) ?- ?({_MONTH_WORDS}) (\d{{4}})\b")
# A sentence about the candidate, not about the offer or the company.
_FIRST_PERSON_RE = re.compile(r"(?:\bj'|\bm'|\b(?:je|mon|ma|mes|moi|i|i'm|i've|my)\b)")


def tenure_durations(source_norm: str) -> set[tuple[int, str]]:
    """Durations implied by the CV's own "Mars 2005 - Juin 2010" ranges: a role's
    span in whole years (rounded down and to nearest) and in months."""
    found: set[tuple[int, str]] = set()
    for m1, y1, m2, y2 in _SPAN_RE.findall(source_norm):
        months = (int(y2) - int(y1)) * 12 + _MONTHS[m2] - _MONTHS[m1]
        if months <= 0:
            continue
        found |= {(months // 12, "year"), (round(months / 12), "year"), (months, "month")}
    return found


def source_durations(source_norm: str) -> set[tuple[int, str]]:
    found = {(v, u) for v, u, _ in durations(source_norm, skip_ranges=False)}
    found |= {(int(n), "year") for n in _SOURCE_PLUS_EN_RE.findall(source_norm)}
    return found | tenure_durations(source_norm)


# Rule 8 - figures. Patterns run on figure_text()-ed text. A figure is a
# standalone number: "17 000+", "150", "80 %", "2,5". Digits glued to a name
# are part of the name, not a figure ("b2b", "aes-256", "bac+5", "24/7",
# "1er", "#144").
_FIGURE_RE = re.compile(
    r"(?<![a-z0-9.,/#+_-])"
    r"(?P<value>\d+(?:\.\d{1,2})?)"
    r"(?![a-z0-9_/]|[.,]\d|-[a-z0-9])"
    r"(?P<pct>\s*(?:%|pour ?cent\b|percent\b))?"
)
_THOUSANDS_RE = re.compile(r"(?<=\d)[ ,.](?=\d{3}(?!\d))")
_DECIMAL_COMMA_RE = re.compile(r"(?<=\d),(?=\d)")
_YEAR_RE = re.compile(r"(?<![\w.,/-])(?:19|20)\d{2}(?![\w/]|[.,]\d)")
# "17 novembre", "1er mars", "november 17", "17/11/2026", "9h30".
_DATE_RES = (
    re.compile(rf"(?<!\w)\d{{1,2}}(?:er|st|nd|rd|th)? (?:{_MONTH_WORDS})\b"),
    re.compile(rf"\b(?:{_MONTH_WORDS}) \d{{1,2}}(?:st|nd|rd|th)?(?!\w| \d{{3}})"),
    re.compile(r"(?<!\w)\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?!\w)"),
    re.compile(r"(?<!\w)\d{1,2} ?h ?\d{0,2}(?!\w)"),
    # A call or a commute is not a claim: "20 minutes", "~50 min", "2 heures".
    re.compile(r"(?<![\w.,])\d+ ?(?:min|mn|minutes?|heures?|hours?|hrs?)(?!\w)"),
)
# The whole of a duration range ("2 a 5 ans", "3-5 years"): rule 7's business.
_RANGE_RE = re.compile(
    rf"(?<![\w.,])(?:{_NUMBER})\s*(?:a|-|to|ou|or)\s*(?:{_NUMBER})\s*\+?\s*"
    r"(?:annees?|ans?|mois|years?|yrs?|months?)(?![\w])"
)


def figure_text(text_norm: str) -> str:
    """Normalised text with numbers in one piece: thousands separators removed
    ("17 000+" and "17,000+" -> "17000+") and a decimal comma turned into a dot
    ("2,5" -> "2.5"), so a number never straddles a clause split on ","."""
    return _DECIMAL_COMMA_RE.sub(".", _THOUSANDS_RE.sub("", text_norm))


def figures(text: str, *, keep_durations: bool = False) -> list[tuple[str, str, str]]:
    """``(value, 'pct'|'num', word before)`` for each figure in
    ``figure_text()``-ed text.

    Years, dates and call / commute times are not figures, and neither are
    durations (rule 7's business) unless ``keep_durations`` - set for the
    source, where "35+ ans" backs a later "j'en ai plus de 35". A trailing "+"
    is not part of the value, so "300+" and "plus de 300" compare equal.
    """
    blank = (*_DATE_RES, _YEAR_RE) if keep_durations else (_RANGE_RE, _DURATION_RE, *_DATE_RES, _YEAR_RE)
    for rx in blank:
        text = rx.sub(lambda m: " " * len(m.group(0)), text)
    out = []
    for m in _FIGURE_RE.finditer(text):
        before = re.search(r"([a-z][\w'-]*)\W*$", text[:m.start()])
        out.append((m.group("value"), "pct" if m.group("pct") else "num", before.group(1) if before else ""))
    return out


_STATED_PCT_RE = re.compile(
    r"(\d+(?:\.\d+)?)(?:\s*(?:-|a|to)\s*(\d+(?:\.\d+)?))?\s*(?:%|pour ?cent\b|percent\b)")


def stated_numbers(text: str, *, every_digit_run: bool = False) -> tuple[set[str], set[str]]:
    """``(numbers, percentages)`` that ``figure_text()``-ed text states.

    Wider than ``figures()``: durations count ("35+ ans" backs "j'en ai plus
    de 35") and both ends of "95-98%" are percentages. With ``every_digit_run``
    (the role side: offer, company research) glued numbers count too, so an
    offer reference in a URL or "M365" is found. The master CV is read without
    it: there, any stray digit run would back an invented "équipe de 12".
    """
    percentages = {n for m in _STATED_PCT_RE.finditer(text) for n in m.groups() if n}
    numbers = {value for value, _, _ in figures(text, keep_durations=True)} | percentages
    if every_digit_run:
        numbers |= set(re.findall(r"\d+(?:\.\d{1,2})?", text)) | set(re.findall(r"\d+", text))
    return numbers, percentages


# Words that sit before a count, not before a version: "équipe de 12", "ses 650".
_FIGURE_STOPWORDS = frozenset(
    "de du des le la les un une et ou a au aux en sur sous avec pour par dans vers chez plus moins "
    "environ pres ses vos nos mes leurs ces the of to in on at for with by over under about around "
    "than and or its your our my their some".split())


def _named_in_role(value: str, before: str, role: str) -> bool:
    """True when the role text has the same name right before the number
    (".net 4.8", "microsoft 365", "industrie 4.0"): a version or product
    designation quoted back, not a count the candidate claims. A count is told
    apart by the word before it ("équipe de 12 personnes" -> "de"), so a team
    size copied from the offer into "j'ai dirigé ..." stays a claim."""
    if len(before) < 3 or before in _FIGURE_STOPWORDS:
        return False
    return re.search(rf"(?<![\w]){re.escape(before)}\s+{re.escape(value)}(?![\d])", role) is not None


def figure_strings(name: str, doc: Any) -> list[str]:
    """The strings of a generated file that rule 8 reads: the prose a recruiter
    takes as the candidate's claims. Contact details, addresses, dates and
    subject lines are left out - they carry numbers that are not claims."""
    if not isinstance(doc, dict):
        return []
    if name == "tailored_cv.json":
        keep = {k: v for k, v in doc.items() if k not in ("candidate_name", "contact_line")}
        return list(_strings(keep))
    if name == "linkedin.json":
        return [v.get("message", "") for v in doc.get("variants", []) if isinstance(v, dict)]
    return [p for p in doc.get("paragraphs", []) if isinstance(p, str)]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+\.", ".", s)  # "ASP .Net" == "ASP.Net"
    return re.sub(r"\s+", " ", s).strip()


def _tok_in(token: str, haystack_norm: str) -> bool:
    t = _norm(token)
    if not t:
        return True
    return re.search(r"(?<![a-z0-9#+.])" + re.escape(t) + r"(?![a-z0-9#+])", haystack_norm) is not None


def _is_familiar_row(cells: list[str]) -> bool:
    return bool(cells) and _norm(cells[0]).startswith(FAMILIAR_HEADINGS)


def familiar_items(rows: list[list[str]]) -> list[str]:
    """Familiar-only skills from the master CV's "Familier / Familiar" row(s).

    Items are split on commas, then on " / ". A leading word (or words) that
    the master CV lists as a regular skill in another row is a tool qualifier,
    not a familiar skill: with "GitHub" and "GitLab" in a tools row,
    "GitHub / GitLab CI/CD" yields only "CI/CD"; with neither listed
    elsewhere, "RabbitMQ / Kafka" yields both.
    """
    regular: set[str] = set()
    for cells in rows:
        if _is_familiar_row(cells):
            continue
        for item in re.split(r"[,\n]", ",".join(cells[1:])):
            name = _norm(re.sub(r"\s*\(.*?\)", "", item))
            if name:
                regular.add(name)

    familiar: list[str] = []
    for cells in rows:
        if not _is_familiar_row(cells):
            continue
        for chunk in re.split(r"[,\n]", " ".join(cells[1:])):
            chunk = re.sub(r"^\s*(backend et api|frontend)\s+", "", chunk.strip(), flags=re.I)
            for part in chunk.split(" / "):
                words = part.split()
                # drop the longest leading run of words that is a regular skill
                for k in range(len(words), 0, -1):
                    if _norm(" ".join(words[:k])) in regular:
                        words = words[k:]
                        break
                item = " ".join(words).strip()
                if item and item not in familiar:
                    familiar.append(item)
    return familiar


def _master_cv_parts(master_path: Path) -> tuple[str, list[str], list[list[str]]]:
    """Return (full normalised text, familiar-only items, raw table rows)."""
    from docx import Document

    doc = Document(str(master_path))
    parts: list[str] = [p.text for p in doc.paragraphs]
    rows: list[list[str]] = []
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            rows.append(cells)
            parts.append(" | ".join(cells))
    return _norm("\n".join(parts)), familiar_items(rows), rows


def master_cv_text(master_path: Path) -> tuple[str, list[str]]:
    """Return (full normalised text, familiar-only items) from MASTER_CV.docx."""
    text, familiar, _ = _master_cv_parts(master_path)
    return text, familiar


_QUALIFIED_RE = re.compile(r"^(?P<name>[^()]+?)\s*\((?P<qual>[^()]+)\)\s*$")


def qualified_skills_from_rows(rows: list[list[str]]) -> dict[str, str]:
    """Map skill name -> qualifier for every ``Name (qualifier)`` skills-table item.

    Skills-table rows are ``heading | item, item, ...``; only the item cells
    (everything after the first) are scanned, split on commas. Names of one
    character or less are ignored - too short to compare reliably.
    """
    out: dict[str, str] = {}
    for cells in rows:
        for chunk in ",".join(cells[1:]).split(","):
            m = _QUALIFIED_RE.match(chunk.strip())
            if m and len(m.group("name").strip()) > 1:
                out[m.group("name").strip()] = m.group("qual").strip()
    return out


def stack_hint_techs(profile: dict[str, Any]) -> list[str]:
    """Tech tokens from company_profile.tech_stack_hints (cold flow, rule 6).

    Hints are prose-ish ("C# / .NET (listed on site)", "Kubernetes - inferred
    from job listings"): annotations in brackets or after a spaced dash are
    dropped, then the shared grounding tokenizer splits the rest into tokens.
    """
    from scripts._grounding_common import split_tokens

    out: list[str] = []
    for hint in profile.get("tech_stack_hints", []) or []:
        hint = re.sub(r"\([^)]*\)", " ", str(hint))
        hint = re.split(r"\s[\u2014\u2013-]\s", hint)[0]
        for tok in split_tokens(hint):
            tok = tok.strip()
            if len(tok) >= 2 and tok not in out:
                out.append(tok)
    return out


def addendum_source_text(addendum_text: str) -> str:
    """Normalised addendum text usable as a SOURCE of truth.

    The addendum mixes facts ("Spring Boot - billing services") with
    prohibitions ("write JDBC, never Hibernate"; "No Go in this role").
    Naming a tech in a negated clause must not make it sourced
    (``scripts/_negation.py`` defines the clause split and negation words):

    - "Hidden skills" bullets are kept whole - positive by definition, even
      when the justification says "without" / "sans".
    - "Skill calibration" is rule text: a sentence carrying any negation is
      dropped whole, because a rule names its subject several clauses away
      from the negation ("Kafka - evaluated, not adopted").
    - Everything else: only the negated clauses are dropped.

    Each kept piece is normalised on its own, so pieces never glue together.
    """
    from scripts._negation import affirmative_clauses, affirmative_sentences
    from scripts.user_customization import addendum_lines

    kept: list[str] = []
    for section, line in addendum_lines(addendum_text):
        if section == "hidden_skills" and line.startswith("- "):
            kept.append(line[2:])
        elif section == "skill_calibration":
            kept.extend(affirmative_sentences(line))
        else:
            kept.extend(affirmative_clauses(line))
    return "\n".join(n for n in (_norm(k) for k in kept) if n)


def calibration_bullets(addendum_text: str) -> list[str]:
    m = re.search(r"^## Skill calibration.*?$(.*?)(?=^## |\Z)", addendum_text, re.S | re.M)
    if not m:
        return []
    return [ln[2:].strip() for ln in m.group(1).splitlines() if ln.startswith("- ")]


def _paths(prep: Path) -> dict[str, Path]:
    from scripts.paths import resolve_user_data_dir

    data = resolve_user_data_dir()
    return {"master": data / "MASTER_CV.docx", "addendum": data / "cv_addendum.md"}


# ------------------------------------------------------------------ merge
def cmd_merge(prep: Path) -> int:
    from scripts.user_customization import parse_addendum_md, merge_addendum_into_fact_base

    p = _paths(prep)
    fb = json.loads((prep / "cv_fact_base.json").read_text(encoding="utf-8"))
    add_text = p["addendum"].read_text(encoding="utf-8") if p["addendum"].exists() else ""
    merged = merge_addendum_into_fact_base(fb, parse_addendum_md(add_text))
    cal = calibration_bullets(add_text)
    if cal:
        merged["addendum_skill_calibration"] = cal
    _, familiar = master_cv_text(p["master"])
    merged["familiar_only_skills"] = familiar
    out = prep / "cv_fact_base_merged.json"
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    added = sum(len(v) for v in parse_addendum_md(add_text).get("additional_experience", {}).values())
    print(f"OK - wrote {out.name}: {added} addendum bullets merged, {len(cal)} calibration notes, "
          f"{len(familiar)} familiar-only skills.")
    return 0


# ------------------------------------------------------------------ check
def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)


def _clause_position(company: str, text_norm: str) -> int:
    """Start of the "<Employer>: ..." clause for ``company`` in the bullet text, or -1.

    The clause may name the company in full or by its leading word(s)
    ("Globex: ..." for "Globex Industries SA"); a bracketed disambiguator and
    a trailing legal form (SA, SAS, Ltd, GmbH, ... - ``LEGAL_SUFFIXES``) are
    ignored. Up to two extra words may sit between the name and the colon,
    with or without a space before it (French "Globex :" / English "Globex:").
    """
    name = _norm(re.sub(r"\s*\(.*?\)", "", company))
    name = _LEGAL_SUFFIX_RE.sub("", name).strip()
    words = name.split()
    starts = []
    for k in range(len(words), 0, -1):
        prefix = " ".join(words[:k])
        m = re.search(r"(?<![a-z0-9])" + re.escape(prefix) + r"(?: [^\s:.]+){0,2}\s?:", text_norm)
        if m:
            starts.append(m.start())
    return min(starts) if starts else -1


def check_earlier_line(cv: dict[str, Any], name: str = "tailored_cv.json") -> list[str]:
    errs: list[str] = []
    entries = cv.get("experience", [])
    for e in entries:
        if _norm(e.get("role_line", "")) not in ("experiences anterieures", "earlier experience"):
            continue
        companies = [c.strip() for c in e.get("metadata_line", "").split("|") if c.strip()]
        text = _norm(" ".join(e.get("bullets", [])))
        pos = -1
        for c in companies:
            i = _clause_position(c, text)
            if i == -1:
                errs.append(f"[earlier-line] {name}: no 'Employer: ...' clause for '{c}' "
                            f"in the earlier-experience bullet")
            elif i < pos:
                errs.append(f"[earlier-line] {name}: clause for '{c}' is out of order versus the heading line")
            else:
                pos = i
            base = _norm(re.sub(r"\s*\(.*?\)", "", c))
            if "(" not in c:
                for other in entries:
                    other_company = _norm(re.sub(r"\s*\(.*?\)", "", other.get("metadata_line", "").split("|")[0]))
                    if other is not e and base and base == other_company:
                        errs.append(f"[earlier-line] {name}: '{c}' also appears in a full entry; "
                                    f"add a disambiguator such as '(<city>)'")
                        break
    return errs


def check(prep: Path, master_text: str, familiar: list[str], addendum_text: str,
          docs: dict[str, Any], offer: dict[str, Any],
          qualified: dict[str, str] | None = None,
          profile: dict[str, Any] | None = None,
          role_text: str = "") -> list[str]:
    """Run rules 1-8. ``qualified`` = master CV ``Name -> qualifier`` map (rule 4);
    ``profile`` = company_profile.json, used by rule 6 only when ``offer`` is empty;
    ``role_text`` = raw offer / company research text, whose figures may be quoted
    back (rule 8)."""
    errors: list[str] = []
    qualified_norm = {_norm(k): (k, v) for k, v in (qualified or {}).items()}
    source = master_text + "\n" + addendum_source_text(addendum_text)

    for name, doc in docs.items():
        for s in _strings(doc):
            m = INTENSITY_RE.search(s)
            if m:
                ctx = _norm(" ".join(s[:m.end()].split()[-2:]))
                if ctx and ctx in source:  # phrase (with its noun) already in master/addendum
                    continue
                errors.append(f"[intensity] {name}: '{m.group(0)}' is not supported by any source: {s[:110]!r}")

    sourced = source_durations(source)
    # Durations the offer / company states ("mission de 24 mois", "5 ans
    # demandés") may be quoted back, as long as the sentence isn't a claim
    # about the candidate.
    role_side = source_durations(_norm(" ".join(_strings([offer or {}, profile or {}]))))
    for name, doc in docs.items():
        for s in _strings(doc):
            for sentence in re.split(r"(?<=[.!?])\s+", _norm(s)):
                for value, unit, text in durations(sentence):
                    if (value, unit) in sourced:
                        continue
                    if (value, unit) in role_side and not _FIRST_PERSON_RE.search(sentence):
                        continue
                    stated = sorted(v for v, u in sourced if u == unit)
                    errors.append(f"[duration] {name}: '{text}' - no source states a {value}-{unit} duration "
                                  f"(master CV / addendum / role dates give {unit}s: {stated or 'none'}); use one "
                                  f"of those, or a date instead (\"depuis 2025\"): {sentence[:90]!r}")

    # Rule 8 - figures. A number in the candidate's prose must be one the
    # master CV or addendum states. A figure is not a claim when it sits in a
    # negated clause ("je n'ai pas administré Microsoft 365"), when it is the
    # role's own figure in a clause that isn't about the candidate, when it
    # follows the same name as in the offer / research (".NET 4.8"), or when
    # it is a long reference number found there.
    from scripts._negation import affirmative_clauses

    stated = dict(zip(("num", "pct"), stated_numbers(figure_text(source))))
    role = figure_text(_norm(" ".join(_strings([offer or {}, profile or {}]))) + " " + role_text)
    role_stated = dict(zip(("num", "pct"), stated_numbers(role, every_digit_run=True)))
    for name, doc in docs.items():
        for s in figure_strings(name, doc):
            for sentence in re.split(r"(?<=[.!?])\s+", figure_text(_norm(s))):
                for clause in affirmative_clauses(sentence):
                    # clause scope, not sentence: "Acme, avec ses 650
                    # collaborateurs, est ce que je recherche" quotes Acme
                    first_person = bool(_FIRST_PERSON_RE.search(clause))
                    for value, kind, before in figures(clause):
                        if value in stated[kind]:
                            continue
                        if value in role_stated[kind] and not first_person:
                            continue
                        if len(value) >= 5 and value in role_stated["num"]:
                            continue
                        if _named_in_role(value, before, role):
                            continue
                        shown = value + (" %" if kind == "pct" else "")
                        errors.append(f"[figure] {name}: '{shown}' - neither the master CV nor the addendum "
                                      f"states this figure; use the source's own number or drop it: "
                                      f"{sentence[:90]!r}")

    cvn = "tailored_cv.json"
    cv = docs.get(cvn, {})
    errors.extend(check_earlier_line(cv, cvn))
    for sec in cv.get("skills_sections", []):
        heading = _norm(sec.get("heading", ""))
        is_fam = heading.startswith(FAMILIAR_HEADINGS)
        for item in sec.get("items", []):
            if not is_fam:
                for f in familiar:
                    if _norm(item) == _norm(f) or _norm(f) in _norm(item).split(" / "):
                        errors.append(f"[familiar] {cvn}: skills '{sec['heading']}': '{item}' is familiar-only "
                                      f"in the master CV; move it under the familiar heading ('Familier / à approfondir')")
                if not _tok_in(re.sub(r"\s*\(.*?\)", "", item), source):
                    errors.append(f"[unsourced-skill] {cvn}: skills '{sec['heading']}': '{item}' not found in master CV or addendum")
            hit = qualified_norm.get(_norm(item))
            if hit:
                errors.append(f"[calibration] {cvn}: '{hit[0]}' must keep the master qualifier '({hit[1]})'")

    narrative = []
    for k in ("title", "tagline"):
        if cv.get(k):
            narrative.append((f"{cvn} ({k})", cv[k]))
    for s in cv.get("summary_paragraphs", []):
        narrative.append((f"{cvn} (summary)", s))
    for name in ("letter.json", "short_letter.json", "linkedin.json"):
        for s in _strings(docs.get(name, {})):
            narrative.append((name, s))
    from scripts._negation import affirmative_clauses

    for where, text in narrative:
        # a mention inside a negated clause admits the gap ("n8n reste à apprendre")
        claimed = _norm(" | ".join(affirmative_clauses(text)))
        for f in familiar:
            if len(f) > 2 and _tok_in(f, claimed):
                errors.append(f"[familiar] {where}: mentions familiar-only skill '{f}' - keep it out of "
                              f"headline/summary/letters, or name it as a gap (\"{f} reste à apprendre\")")

    if offer:
        techs, label, origin = offer.get("technologies", []), "jd-contagion", "the job posting"
    elif profile:
        techs, label, origin = stack_hint_techs(profile), "stack-contagion", "the company's tech_stack_hints"
    else:
        techs, label, origin = [], "", ""
    techs = [t for t in techs if t and not _tok_in(t, source)]
    if techs:
        for name, d in docs.items():
            for text in _strings(d):
                # a mention inside a negated clause admits the gap ("no Terraform yet")
                flagged: set[str] = set()
                for clause in affirmative_clauses(text):
                    cl = _norm(clause)
                    for tech in techs:
                        if tech not in flagged and _tok_in(tech, cl):
                            flagged.add(tech)
                            errors.append(f"[{label}] {name}: '{tech}' comes from {origin} but is in neither "
                                          f"master CV nor addendum: {cl[:90]!r}")
    return errors


def run_check(prep: Path, master: Path | None = None,
              only: tuple[str, ...] | list[str] | None = None) -> list[str]:
    """Load the master CV, addendum and the generated docs in ``prep``; return errors.

    ``master`` overrides the default ``<user-data-dir>/MASTER_CV.docx``.
    ``only`` restricts the check to those files (subset of ``DOC_NAMES``);
    default = every one of them that exists. Rule 6 reads
    ``job_offer_analysis.json`` (offer flow) or, when that is absent,
    ``company_profile.json`` (cold flow).
    """
    p = _paths(prep)
    if master is not None:
        p["master"] = master
    master_text, familiar, rows = _master_cv_parts(p["master"])
    add_text = p["addendum"].read_text(encoding="utf-8") if p["addendum"].exists() else ""
    unknown = [n for n in (only or ()) if n not in DOC_NAMES]
    if unknown:
        raise ValueError(f"unknown claims file(s): {unknown}; expected some of {DOC_NAMES}")
    docs = {}
    for name in (only or DOC_NAMES):
        f = prep / name
        if f.exists():
            docs[name] = json.loads(f.read_text(encoding="utf-8"))
    offer_f = prep / "job_offer_analysis.json"
    offer = json.loads(offer_f.read_text(encoding="utf-8")) if offer_f.exists() else {}
    profile_f = prep / "company_profile.json"
    profile = None
    if not offer_f.exists() and profile_f.exists():
        profile = json.loads(profile_f.read_text(encoding="utf-8"))
    role_text = " ".join(_norm((prep / n).read_text(encoding="utf-8"))
                         for n in ROLE_TEXT_NAMES if (prep / n).exists())
    return check(prep, master_text, familiar, add_text, docs, offer,
                 qualified=qualified_skills_from_rows(rows), profile=profile, role_text=role_text)


def cmd_check(prep: Path) -> int:
    errors = run_check(prep)
    if errors:
        print(f"CLAIMS CHECK FAILED - {len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        print("Fix the wording (do not add the claim to the master CV / addendum just to pass) and re-run.")
        return 1
    print("Claims check OK - no unsourced intensity wording, figures or durations, no familiar-only "
          "or invented skills.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("merge", "check"):
        print("usage: claims_guard.py {merge|check} <prep_dir>")
        return 2
    prep = Path(argv[2]).resolve()
    return cmd_merge(prep) if argv[1] == "merge" else cmd_check(prep)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
