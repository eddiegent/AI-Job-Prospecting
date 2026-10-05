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
       "Familier / a approfondir" heading, and never in tagline/summary/letters.
    3. Every item in a (non-familiar) skills section must appear literally in the
       master CV or the addendum - no invented skills.
    4. A skill the master CV qualifies (e.g. "Python (lecture/adaptation de
       scripts)") must keep its qualifier.
    5. JD contagion: a technology from job_offer_analysis.technologies that is
       absent from master CV + addendum must not appear anywhere in the output.
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


def master_cv_text(master_path: Path) -> tuple[str, list[str]]:
    """Return (full normalised text, familiar-only items) from MASTER_CV.docx."""
    from docx import Document

    doc = Document(str(master_path))
    parts: list[str] = [p.text for p in doc.paragraphs]
    familiar: list[str] = []
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            parts.append(" | ".join(cells))
            if cells and _norm(cells[0]).startswith(FAMILIAR_HEADINGS):
                for chunk in " ".join(cells[1:]).split(","):
                    chunk = re.sub(r"^\s*(backend et api|frontend)\s+", "", chunk.strip(), flags=re.I)
                    if not chunk:
                        continue
                    if "ci/cd" in chunk.lower():
                        familiar.append("CI/CD")  # "Github / GitLab CI/CD": only CI/CD is familiar
                    else:
                        familiar.extend(x.strip() for x in chunk.split(" / ") if x.strip())
    return _norm("\n".join(parts)), familiar


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


def check(prep: Path, master_text: str, familiar: list[str], addendum_text: str,
          docs: dict[str, Any], offer: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source = master_text + "\n" + _norm(addendum_text)

    for name, doc in docs.items():
        for s in _strings(doc):
            m = INTENSITY_RE.search(s)
            if m:
                ctx = _norm(" ".join(s[:m.end()].split()[-2:]))
                if ctx and ctx in source:  # phrase (with its noun) already in master/addendum
                    continue
                errors.append(f"[intensity] {name}: '{m.group(0)}' is not supported by any source: {s[:110]!r}")

    cv = docs.get("tailored_cv.json", {})
    familiar_norm = [_norm(f) for f in familiar]
    for sec in cv.get("skills_sections", []):
        heading = _norm(sec.get("heading", ""))
        is_fam = heading.startswith(FAMILIAR_HEADINGS)
        for item in sec.get("items", []):
            if not is_fam:
                for f in familiar:
                    if _norm(item) == _norm(f) or _norm(f) in _norm(item).split(" / "):
                        errors.append(f"[familiar] skills '{sec['heading']}': '{item}' is familiar-only in the master CV; move it under 'Familier / à approfondir'")
                if not _tok_in(re.sub(r"\s*\(.*?\)", "", item), source):
                    errors.append(f"[unsourced-skill] skills '{sec['heading']}': '{item}' not found in master CV or addendum")
            if _norm(item) == "python" and "python (lecture" in master_text:
                errors.append("[calibration] Python must keep the master qualifier '(lecture/adaptation de scripts)'")

    narrative = []
    for k in ("title", "tagline"):
        if cv.get(k):
            narrative.append((f"tailored_cv.{k}", cv[k]))
    for s in cv.get("summary_paragraphs", []):
        narrative.append(("tailored_cv.summary", s))
    for name in ("letter.json", "short_letter.json", "linkedin.json"):
        for s in _strings(docs.get(name, {})):
            narrative.append((name, s))
    for where, text in narrative:
        for f in familiar:
            if len(f) > 2 and _tok_in(f, _norm(text)):
                errors.append(f"[familiar] {where}: mentions familiar-only skill '{f}' - keep it out of headline/summary/letters")

    neg = re.compile(r"\b(pas|aucun(?:e)?|sans|jamais|no|not|never|without|ne connais|n'ai pas)\b")
    for d in docs.values():
        for text in _strings(d):
            for sent in re.split(r"(?<=[.!?])\s+", _norm(text)):
                for tech in offer.get("technologies", []):
                    if tech and not _tok_in(tech, source) and _tok_in(tech, sent) and not neg.search(sent):
                        errors.append(f"[jd-contagion] '{tech}' comes from the job posting but is in neither master CV nor addendum: {sent[:90]!r}")
    return errors


def cmd_check(prep: Path) -> int:
    p = _paths(prep)
    master_text, familiar = master_cv_text(p["master"])
    add_text = p["addendum"].read_text(encoding="utf-8") if p["addendum"].exists() else ""
    docs = {}
    for name in ("tailored_cv.json", "letter.json", "short_letter.json", "linkedin.json"):
        f = prep / name
        if f.exists():
            docs[name] = json.loads(f.read_text(encoding="utf-8"))
    offer_f = prep / "job_offer_analysis.json"
    offer = json.loads(offer_f.read_text(encoding="utf-8")) if offer_f.exists() else {}
    errors = check(prep, master_text, familiar, add_text, docs, offer)
    if errors:
        print(f"CLAIMS CHECK FAILED - {len(errors)} problem(s):")
        for e in errors:
            print("  -", e)
        print("Fix the wording (do not add the claim to the master CV / addendum just to pass) and re-run.")
        return 1
    print("Claims check OK - no unsourced intensity wording, familiar-only skills or invented skills.")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] not in ("merge", "check"):
        print("usage: claims_guard.py {merge|check} <prep_dir>")
        return 2
    prep = Path(argv[2]).resolve()
    return cmd_merge(prep) if argv[1] == "merge" else cmd_check(prep)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
