"""Compare original vs regenerated application packs (_prep/ files).

Usage: python tools/compare_packs.py [--gates]   (--gates also runs the current
cv/letters/linkedin/interview gates on every pack)
"""
import json
import re
import sys
from pathlib import Path

OUT = Path(r"C:\GitProjects\AI\Job Prospecting\output")
# (label, original, run 1 = first regeneration, run 2 = after the gate fixes).
# Run 1 folders were moved aside with a run1_ prefix so run 2 could reuse the date.
RUNS = [
    ("Opus #148", "good-19102026-AI-Product-Builder-Junior-Opus-Recruitment-Solutions",
     "run1_good-21102026-AI-Product-Builder-Junior-Opus-Recruitment-Solutions",
     "medium-21102026-AI-Product-Builder-Junior-Opus-Recruitment-Solutions"),
    ("CANAL+ #147", "medium-13102026-AI-Builder-(CDI)-CANAL+-Group-(CANAL+-TECH)",
     "run1_good-21102026-AI-Builder-(CDI)-CANAL+-Group-(CANAL+-TECH)",
     "medium-21102026-AI-Builder-(CDI)-CANAL+-Group-(CANAL+-TECH)"),
    ("Brevo #146", "medium-11102026-AI-Native-Product-Engineer-Brevo",
     "run1_medium-21102026-AI-Native-Product-Engineer-Brevo",
     "medium-21102026-AI-Native-Product-Engineer-Brevo"),
    ("OTOQI #145", "medium-09102026-Low-Code-Product-Builder-H-F-OTOQI",
     "run1_medium-21102026-Low-Code-Product-Builder-H-F-OTOQI",
     "medium-21102026-Low-Code-Product-Builder-H-F-OTOQI"),
    ("APB #144", "medium-09102026-AI-Product-Builder-Automatisation-Outils-Metiers-(H-F)-Groupe-APB",
     "run1_good-21102026-AI-Product-Builder-Automatisation-Outils-Metiers-(H-F)-Groupe-APB",
     "good-21102026-AI-Product-Builder-Automatisation-Outils-Metiers-(H-F)-Groupe-APB"),
]


def load(folder, name):
    p = OUT / folder / "_prep" / name
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8") if name.endswith(".md") else json.loads(p.read_text(encoding="utf-8"))


def body_len(letter):
    return sum(len(p) for p in letter.get("paragraphs", [])) if letter else 0


def summarize(folder):
    s = {}
    ma = load(folder, "match_analysis.json")
    ms = ma["match_summary"]
    s["fit"] = f"{ms['overall_fit_pct']}% ({ms['direct_count']}D/{ms['transferable_count']}T/{ms['gap_count']}G of {len(ma['matches'])})"
    s["gaps"] = [m["requirement"][:45] for m in ma["matches"] if m["match_type"] == "gap"]
    offer = load(folder, "job_offer_analysis.json")
    s["size/lang"] = f"{offer.get('company_size')}/{offer.get('detected_language')}"
    cv = load(folder, "tailored_cv.json")
    s["tagline"] = cv.get("tagline", "")
    s["skills order"] = " > ".join(x["heading"] for x in cv["skills_sections"][:3])
    s["experience"] = " | ".join(f"{e['role_line'][:22]}({len(e['bullets'])})" for e in cv["experience"])
    earlier = [e for e in cv["experience"] if e["role_line"].startswith(("Expériences antérieures", "Earlier"))]
    s["consolidated"] = earlier[0]["metadata_line"] if earlier else "(none)"
    s["cv words"] = sum(len(" ".join(e["bullets"]).split()) for e in cv["experience"]) + sum(len(p.split()) for p in cv.get("summary_paragraphs", []))
    s["summary lead"] = (cv.get("summary_paragraphs") or [""])[0][:70]
    letter = load(folder, "letter.json")
    s["letter"] = f"{len(letter['paragraphs'])} paras, {body_len(letter)} chars, to: {letter.get('recipient_name', '')[:40]}"
    s["letter opening"] = letter["paragraphs"][0][:90]
    sl = load(folder, "short_letter.json")
    s["short letter"] = f"{body_len(sl)} chars" if sl else "(missing)"
    li = load(folder, "linkedin.json")
    s["linkedin"] = "; ".join(f"{v.get('target')}:{(v.get('contact_name') or '?')[:18]}({len(v.get('message', ''))})" for v in li["variants"])
    ip = load(folder, "interview_prep.md")
    s["interview"] = f"{len(ip)} chars, {len(re.findall(r'^## ', ip, re.M))} sections"
    cr = load(folder, "company_research.md")
    s["research"] = f"{len(cr)} chars" if cr else "(missing)"
    return s


GATES = ("cv", "letters", "linkedin", "interview")
CLI = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "job-application-tailor" / "scripts" / "cli.py"


def gate_results(folder):
    """Current gates on the pack's _prep/ (gate match is skipped: it rewrites match_summary)."""
    import subprocess
    out = []
    for stage in GATES:
        r = subprocess.run([sys.executable, str(CLI), "gate", stage, str(OUT / folder)],
                           capture_output=True, text=True, encoding="utf-8")
        fails = [l[7:].strip() for l in r.stdout.splitlines() if l.startswith("[FAIL]")]
        out.append(f"{stage}:{'PASS' if r.returncode == 0 else 'FAIL(' + ', '.join(fails) + ')'}")
    return " ".join(out)


with_gates = "--gates" in sys.argv
for label, *folders in RUNS:
    print(f"\n==================== {label}")
    sums = [summarize(f) for f in folders]
    if with_gates:
        for s, f in zip(sums, folders):
            s["gates now"] = gate_results(f)
    for k in sums[0]:
        vals = [s.get(k) for s in sums]
        mark = "  " if len({str(v) for v in vals}) == 1 else "* "
        print(f"{mark}{k}:")
        for name, v in zip(("ORIG", "RUN1", "RUN2"), vals):
            print(f"    {name}: {v}")
