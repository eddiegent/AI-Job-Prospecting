"""Tests for `cli.py gate <stage> <folder>` and `cli.py read-cv`
(scripts/commands/gate.py, scripts/commands/pipeline.py)."""
from __future__ import annotations

import copy
import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.commands.gate import cmd_gate
from scripts.commands.pipeline import cmd_read_cv
from tests.conftest import load_fixture


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """User data dir with a tiny master CV and no prefs/addendum."""
    from docx import Document

    data = tmp_path / "userdata"
    data.mkdir()
    doc = Document()
    doc.add_paragraph("Alex Dupont")
    doc.add_paragraph("Senior Engineer, C++ and API platforms.", style="Heading 1")
    # the education line tailored_cv_good.json carries: its "6" must be sourced (claims rule 8)
    doc.add_paragraph("2025 — Product Builder No-Code, École Cube (RNCP Niveau 6)")
    doc.add_paragraph("   ")  # blank paragraphs are skipped by read-cv
    t = doc.add_table(rows=2, cols=2)
    t.rows[0].cells[0].text = "Langages"
    t.rows[0].cells[1].text = "C++, Python (scripts)"
    t.rows[1].cells[0].text = "Familier / a approfondir"
    t.rows[1].cells[1].text = "Docker"
    doc.save(str(data / "MASTER_CV.docx"))
    monkeypatch.setenv("JOB_TAILOR_HOME", str(data))
    return data


def _run(tmp_path: Path, files: dict[str, dict]) -> Path:
    run = tmp_path / "good-14072026-role"
    prep = run / "_prep"
    prep.mkdir(parents=True)
    for name, payload in files.items():
        (prep / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return run


def _gate(stage: str, folder: Path, capsys) -> tuple[int, str]:
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage=stage, folder=str(folder), cv=None))
    return e.value.code, capsys.readouterr().out


def _offer() -> dict:
    return {"job_title": "Dev", "company_name": "Acme", "required_skills": ["C++"],
            "preferred_skills": [], "responsibilities": [], "technologies": ["Kubernetes", "C++"],
            "ats_keywords": []}


def _offer_for(ma: dict) -> dict:
    """An offer whose items are exactly the rows of ``ma`` (one row per offer
    item, scripts/match_rows.py), so a match test checks grounding alone."""
    lists = {"required_skill": "required_skills", "preferred_skill": "preferred_skills",
             "technology": "technologies", "responsibility": "responsibilities"}
    offer = {"job_title": "Dev", "company_name": "Acme", "required_skills": [], "preferred_skills": [],
             "responsibilities": [], "technologies": [], "ats_keywords": []}
    for m in ma["matches"]:
        offer[lists[m["category"]]].append(m["requirement"])
    return offer


def test_gate_unknown_folder_exits_2(tmp_path, home):
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage="cv", folder=str(tmp_path / "nope"), cv=None))
    assert e.value.code == 2


def test_gate_missing_input_fails_and_stops(tmp_path, home, capsys):
    code, out = _gate("roles", _run(tmp_path, {}), capsys)
    assert code == 1
    assert "[FAIL] schema role_candidates.json" in out
    assert "role_candidates.json not found" in out
    assert "role grounding" not in out  # later checks skipped
    assert "skipped" in out


def test_gate_match_recounts_in_place_and_passes(tmp_path, home, capsys):
    ma = load_fixture("sample_match_analysis.json")
    ma["match_summary"]["overall_fit_pct"] = 12  # LLM drift
    for m in ma["matches"]:  # a technology the fact base lacks is a gap, never half credit
        if m["requirement"] == "Distributed systems":
            m["match_type"] = "gap"
    run = _run(tmp_path, {"match_analysis.json": ma, "job_offer_analysis.json": _offer_for(ma),
                          "cv_fact_base_merged.json": load_fixture("sample_fact_base.json")})
    code, out = _gate("match", run, capsys)
    assert code == 0, out
    assert "[PASS] match rows = offer items" in out
    assert "[PASS] recount match_summary: updated" in out
    assert "[PASS] schema match_analysis.json" in out
    assert "[PASS] match grounding (vs cv_fact_base_merged.json)" in out
    saved = json.loads((run / "_prep" / "match_analysis.json").read_text(encoding="utf-8"))
    assert saved["match_summary"]["overall_fit_pct"] != 12
    # second run: already in sync
    code, out = _gate("match", run, capsys)
    assert "[PASS] recount match_summary: unchanged" in out


def _gate_check(stage: str, folder: Path, capsys, **extra) -> tuple[int, str]:
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage=stage, folder=str(folder), cv=None, check=True, **extra))
    return e.value.code, capsys.readouterr().out


def test_gate_match_check_reports_a_stale_summary_and_writes_nothing(tmp_path, home, capsys):
    ma = load_fixture("sample_match_analysis.json")
    ma["match_summary"]["overall_fit_pct"] = 12
    for m in ma["matches"]:
        if m["requirement"] == "Distributed systems":
            m["match_type"] = "gap"
    run = _run(tmp_path, {"match_analysis.json": ma, "job_offer_analysis.json": _offer_for(ma),
                          "cv_fact_base_merged.json": load_fixture("sample_fact_base.json")})
    target = run / "_prep" / "match_analysis.json"
    before = target.read_bytes()
    code, out = _gate_check("match", run, capsys)
    assert code == 1
    assert "[FAIL] recount match_summary" in out and "--check: file not changed" in out
    assert target.read_bytes() == before


def test_gate_match_check_passes_a_pack_analysed_before_the_required_gap_fields(tmp_path, home, capsys):
    ma = load_fixture("sample_match_analysis.json")
    for m in ma["matches"]:
        if m["requirement"] == "Distributed systems":
            m["match_type"] = "gap"
    from scripts.common import recount_match_summary
    ma["match_summary"] = {k: v for k, v in recount_match_summary(ma["matches"]).items()
                           if k not in ("required_gap_count", "required_gaps")}
    run = _run(tmp_path, {"match_analysis.json": ma, "job_offer_analysis.json": _offer_for(ma),
                          "cv_fact_base_merged.json": load_fixture("sample_fact_base.json")})
    code, out = _gate_check("match", run, capsys)
    assert code == 0, out
    assert "counts match" in out and "[PASS] match grounding" in out


def test_gate_match_check_keeps_auditing_after_a_stale_summary(tmp_path, home, capsys):
    ma = load_fixture("sample_match_analysis.json")
    ma["match_summary"]["overall_fit_pct"] = 12
    run = _run(tmp_path, {"match_analysis.json": ma, "job_offer_analysis.json": _offer_for(ma),
                          "cv_fact_base_merged.json": load_fixture("sample_fact_base.json")})
    code, out = _gate_check("match", run, capsys)
    assert code == 1 and "match_summary is stale" in out
    assert "match rows = offer items" in out and "skipped" not in out


def test_gate_check_and_draft_together_are_refused(tmp_path, home, capsys):
    run = _run(tmp_path, {})
    code, _ = _gate_check("letters", run, capsys, draft=True)
    assert code == 2


def _direct(req: str) -> dict:
    return {"match_summary": {}, "matches": [
        {"requirement": req, "category": "technology", "match_type": "direct", "evidence": "x"}]}


def test_gate_match_blocks_rows_that_are_not_the_offer_items(tmp_path, home, capsys):
    offer = {**_offer(), "responsibilities": ["Concevoir des API"]}
    ma = {"match_summary": {}, "matches": [
        {"requirement": "c++ ", "category": "required_skill", "match_type": "direct", "evidence": "x"},
        {"requirement": "Kubernetes", "category": "required_skill", "match_type": "gap"},
        {"requirement": "Leadership", "category": "responsibility", "match_type": "gap"},
    ]}
    run = _run(tmp_path, {"match_analysis.json": ma, "job_offer_analysis.json": offer,
                          "cv_fact_base_merged.json": load_fixture("sample_fact_base.json")})
    code, out = _gate("match", run, capsys)
    assert code == 1
    assert "[FAIL] match rows = offer items" in out
    assert "'Kubernetes' has category 'required_skill', expected 'technology'" in out
    assert "'Leadership' is not an item of the offer analysis" in out
    assert "no row for offer item 'Concevoir des API' (responsibility)" in out
    assert "match-rows" in out
    # "c++ " is the offer's "C++" (case and spacing don't count), and listed twice in the
    # offer it still needs one row only
    assert "C++" not in out.split("[FAIL] match rows")[1].split("[")[0]


def test_gate_match_fails_without_merged_fact_base(tmp_path, home, capsys):
    """No silent fallback to cv_fact_base.json: the addendum would be ignored."""
    run = _run(tmp_path, {"match_analysis.json": _direct("C++"), "job_offer_analysis.json": _offer(),
                          "cv_fact_base.json": load_fixture("sample_fact_base.json")})
    code, out = _gate("match", run, capsys)
    assert code == 1
    assert "[FAIL] match grounding (vs cv_fact_base_merged.json)" in out
    assert "cv_fact_base_merged.json not found" in out
    assert "python scripts/claims_guard.py merge" in out and "Step 3.9" in out


def test_gate_match_grounds_against_merged_fact_base(tmp_path, home, capsys):
    fb = load_fixture("sample_fact_base.json")
    run = _run(tmp_path, {"match_analysis.json": _direct("Kubernetes"),
                          "job_offer_analysis.json": _offer_for(_direct("Kubernetes")),
                          "cv_fact_base_merged.json": fb})
    code, out = _gate("match", run, capsys)
    assert code == 1 and "[FAIL] match grounding (vs cv_fact_base_merged.json)" in out

    merged = copy.deepcopy(fb)
    merged["addendum_hidden_skills"] = ["Kubernetes"]
    (run / "_prep" / "cv_fact_base_merged.json").write_text(json.dumps(merged), encoding="utf-8")
    code, out = _gate("match", run, capsys)
    assert code == 0, out
    assert "[PASS] match grounding (vs cv_fact_base_merged.json)" in out


@pytest.mark.parametrize("detail, passes", [
    (None, False),                                         # no evidence at all
    ("Pas de Kubernetes à ce poste.", False),              # negated addendum line is not evidence
    ("No Kubernetes in this role, only Docker.", False),
    ("Déploiement des services sur Kubernetes.", True),    # positive line grounds it
    ("Pas de Docker ; déploiement sur Kubernetes.", True),  # only the negated clause is dropped
])
def test_gate_match_negated_addendum_detail_does_not_ground(tmp_path, home, capsys, detail, passes):
    merged = load_fixture("sample_fact_base.json")
    if detail:
        merged["experience"][0]["details"].append(detail)  # where merge_addendum_into_fact_base puts it
    run = _run(tmp_path, {"match_analysis.json": _direct("Kubernetes"),
                          "job_offer_analysis.json": _offer_for(_direct("Kubernetes")),
                          "cv_fact_base_merged.json": merged})
    code, out = _gate("match", run, capsys)
    assert (code == 0) is passes, out


@pytest.mark.parametrize("stage, target", [("roles", "role_candidates.json"),
                                           ("selected-role", "selected_role.json")])
def test_gate_role_grounding_fails_without_merged_fact_base(tmp_path, home, capsys, stage, target):
    role = {"title": "Senior Engineer", "source": "generalist", "seniority_band": "senior",
            "generated_at": "2026-10-20T10:00:00Z", "company_name": "Acme", "language": "en",
            "emphasis_areas": ["C++"], "rationale": "x"}
    payload = ({"candidates": [{k: role[k] for k in ("title", "rationale", "seniority_band", "emphasis_areas")}],
                "generated_at": role["generated_at"], "company_name": "Acme"}
               if stage == "roles" else role)
    run = _run(tmp_path, {target: payload, "company_profile.json": {"tech_stack_hints": ["Kubernetes"]},
                          "cv_fact_base.json": load_fixture("sample_fact_base.json")})
    code, out = _gate(stage, run, capsys)
    assert code == 1, out
    assert "cv_fact_base_merged.json not found" in out and "claims_guard.py merge" in out


def _fact_base() -> dict[str, dict]:
    return {"cv_fact_base_merged.json": load_fixture("sample_fact_base.json")}


def test_gate_cv_reports_every_failure_together(tmp_path, home, capsys):
    (home / "user_prefs.yaml").write_text('forbidden_title_labels:\n  - "Backend"\n', encoding="utf-8")
    cv = load_fixture("tailored_cv_good.json")
    cv["title"] = "Backend Engineer"
    cv["skills_sections"] = [{"heading": "Langages", "items": ["C++", "Python"]}]
    code, out = _gate("cv", _run(tmp_path, {"tailored_cv.json": cv, **_fact_base()}), capsys)
    assert code == 1
    assert "[PASS] schema tailored_cv.json" in out
    assert "[PASS] cv timeline" in out
    assert "[FAIL] forbidden title labels in tailored_cv.json" in out
    assert "[FAIL] claims check (tailored_cv.json)" in out
    assert "tailored_cv.json: 'Python' must keep the master qualifier '(scripts)'" in out
    assert "gate cv: FAIL (2 check(s) failed)" in out


def test_gate_cv_schema_failure_stops_stage(tmp_path, home, capsys):
    code, out = _gate("cv", _run(tmp_path, {"tailored_cv.json": {"title": "x"}}), capsys)
    assert code == 1
    assert "[FAIL] schema tailored_cv.json" in out
    assert "claims check" not in out


def test_gate_cv_fails_when_a_recent_role_is_folded(tmp_path, home, capsys):
    cv = _clean_cv()
    del cv["experience"][1]  # Midway Systems, 2010-2017
    cv["experience"][-1]["metadata_line"] = "Midway Systems | TinyShop"
    code, out = _gate("cv", _run(tmp_path, {"tailored_cv.json": cv, **_fact_base()}), capsys)
    assert code == 1
    assert "[FAIL] cv timeline" in out
    assert "'Midway Systems' (2010 - 2017) is not a full experience entry" in out


def test_gate_cv_load_bearing_role_folded_only_warns(tmp_path, home, capsys):
    cv = _clean_cv()
    del cv["experience"][2]  # OldCo Media, named by the match evidence
    cv["experience"][-1]["metadata_line"] = "OldCo Media | TinyShop"
    cv["experience"][-1]["bullets"] = ["OldCo Media : développement C++. TinyShop : premiers postes (C++)."]
    files = {"tailored_cv.json": cv, **_fact_base(),
             "match_analysis.json": load_fixture("sample_match_analysis.json")}
    code, out = _gate("cv", _run(tmp_path, files), capsys)
    assert code == 0, out
    assert "[PASS] cv timeline" in out
    assert "[WARN] cv timeline" in out and "'OldCo Media'" in out


def test_gate_cv_timeline_checks_the_heading_language(tmp_path, home, capsys):
    files = {"tailored_cv.json": _clean_cv(), **_fact_base(),
             "job_offer_analysis.json": {**_offer(), "detected_language": "en"}}
    code, out = _gate("cv", _run(tmp_path, files), capsys)
    assert code == 1
    assert "should contain 'Earlier experience'" in out


def test_gate_cv_timeline_needs_a_fact_base(tmp_path, home, capsys):
    code, out = _gate("cv", _run(tmp_path, {"tailored_cv.json": _clean_cv()}), capsys)
    assert code == 1
    assert "neither cv_fact_base_merged.json nor cv_fact_base.json found" in out


def _clean_cv() -> dict:
    cv = load_fixture("tailored_cv_good.json")
    cv["experience"][-1]["bullets"] = ["TinyShop : premiers postes en développement logiciel (C++)."]
    return cv


def _bad_cv() -> dict:
    cv = _clean_cv()
    cv["skills_sections"] = [{"heading": "Langages", "items": ["C++", "Python"]}]  # loses its qualifier
    return cv


def _linkedin(msg: str = "Bonjour, échange possible ?") -> dict:
    return {"variants": [{"target": "recruiter", "message": msg}]}


def _letter(par: str) -> dict:
    return {"greeting": "Bonjour,", "paragraphs": [par], "signoff": "Cordialement,", "name": "Alex Dupont"}


def _short_letter(chars: int = 600) -> dict:
    """A short letter whose body is exactly ``chars`` characters."""
    return _letter(("Je développe des outils C++ pour des équipes métier. " * 20)[:chars])


@pytest.mark.parametrize("chars,passes", [(499, False), (500, True), (750, True), (751, False)])
def test_gate_letters_short_letter_length_bounds(tmp_path, home, capsys, chars, passes):
    files = {"letter.json": _letter("Bonjour."), "short_letter.json": _short_letter(chars)}
    code, out = _gate("letters", _run(tmp_path, files), capsys)
    assert (code == 0) is passes, out
    if passes:
        assert f"[PASS] short letter length: {chars} characters" in out
    else:
        verb = "add 1" if chars < 500 else "cut 1"
        assert f"short_letter.json body is {chars} characters" in out and verb in out


def test_gate_letters_short_letter_length_sums_the_paragraphs(tmp_path, home, capsys):
    short = _letter("x" * 300)
    short["paragraphs"].append("y" * 199)
    code, out = _gate("letters", _run(tmp_path, {"letter.json": _letter("Bonjour."), "short_letter.json": short}),
                      capsys)
    assert code == 1
    assert "body is 499 characters" in out


def test_gate_linkedin_ignores_problems_in_other_stages_files(tmp_path, home, capsys):
    run = _run(tmp_path, {"tailored_cv.json": _bad_cv(), "linkedin.json": _linkedin(),
                          "letter.json": _letter("J'utilise Docker au travail.")})
    code, out = _gate("linkedin", run, capsys)
    assert code == 0, out
    assert "[PASS] claims check (linkedin.json)" in out


def test_gate_cv_ignores_letter_problems_and_letters_ignore_cv(tmp_path, home, capsys):
    files = {"tailored_cv.json": _clean_cv(), **_fact_base(),
             "letter.json": _letter("J'utilise Docker au travail."), "short_letter.json": _short_letter()}
    run = _run(tmp_path, files)
    code, out = _gate("cv", run, capsys)
    assert code == 0, out
    assert "[PASS] claims check (tailored_cv.json)" in out

    files["tailored_cv.json"] = _bad_cv()
    files["letter.json"] = _letter("Bonjour.")
    run2 = _run(tmp_path / "b", files)
    code, out = _gate("letters", run2, capsys)
    assert code == 0, out
    assert "[PASS] claims check (letter.json, short_letter.json)" in out


def test_gate_letters_messages_name_the_file(tmp_path, home, capsys):
    offer = _offer()
    run = _run(tmp_path, {"job_offer_analysis.json": offer,
                          "letter.json": _letter("J'ai déployé Kubernetes en production."),
                          "short_letter.json": _letter("J'utilise Docker au travail.")})
    code, out = _gate("letters", run, capsys)
    assert code == 1
    assert "[jd-contagion] letter.json: 'Kubernetes'" in out
    assert "[familiar] short_letter.json: mentions familiar-only skill 'Docker'" in out


# ------------------------------------------------------------ humanizer guard

def _gate_draft(stage: str, folder: Path, capsys) -> tuple[int, str]:
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage=stage, folder=str(folder), cv=None, draft=True))
    return e.value.code, capsys.readouterr().out


def _write(run: Path, name: str, payload: dict) -> None:
    (run / "_prep" / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _letters_run(tmp_path: Path) -> Path:
    letter = _letter("Je développe des outils C++ pour des équipes métier depuis longtemps.")
    letter["subject_line"] = "Candidature - Dev"
    return _run(tmp_path, {"letter.json": letter, "short_letter.json": _short_letter()})


def test_gate_without_a_draft_snapshot_passes_with_a_note(tmp_path, home, capsys):
    code, out = _gate("letters", _letters_run(tmp_path), capsys)
    assert code == 0, out
    assert "[PASS] humanizer guard (letter.json, short_letter.json): no draft snapshot - not checked" in out


def test_gate_draft_saves_a_snapshot_and_a_style_only_rewrite_passes(tmp_path, home, capsys):
    run = _letters_run(tmp_path)
    code, out = _gate_draft("letters", run, capsys)
    assert code == 0, out
    assert "draft snapshot saved (letter.json, short_letter.json)" in out
    assert (run / "_prep" / "pre_humanize" / "letter.json").exists()

    letter = json.loads((run / "_prep" / "letter.json").read_text(encoding="utf-8"))
    letter["paragraphs"] = ["Depuis longtemps, je développe des outils C++ pour des équipes métier."]
    _write(run, "letter.json", letter)
    code, out = _gate("letters", run, capsys)
    assert code == 0, out
    assert "[PASS] humanizer guard (letter.json, short_letter.json)" in out


def test_gate_fails_when_the_pass_adds_a_number_a_name_or_touches_another_field(tmp_path, home, capsys):
    run = _letters_run(tmp_path)
    assert _gate_draft("letters", run, capsys)[0] == 0

    letter = json.loads((run / "_prep" / "letter.json").read_text(encoding="utf-8"))
    letter["subject_line"] = "Candidature : Dev"
    letter["paragraphs"] = ["Je développe des outils C++ pour 40 équipes métier chez Globex depuis longtemps."]
    _write(run, "letter.json", letter)
    code, out = _gate("letters", run, capsys)
    assert code == 1
    assert "[FAIL] humanizer guard (letter.json, short_letter.json)" in out
    assert "the pass changed 'subject_line'" in out
    assert "the number 40 is not in the draft" in out
    assert "the name 'Globex' is not in the draft" in out
    assert "--draft" in out  # the way out when a gate fix needed a new fact


def test_gate_warns_on_a_sentence_the_draft_did_not_have(tmp_path, home, capsys):
    run = _letters_run(tmp_path)
    assert _gate_draft("letters", run, capsys)[0] == 0
    letter = json.loads((run / "_prep" / "letter.json").read_text(encoding="utf-8"))
    letter["paragraphs"][0] += " L'ensemble pouvait ensuite fonctionner durablement sans intervention."
    _write(run, "letter.json", letter)
    code, out = _gate("letters", run, capsys)
    assert code == 0, out  # a warning: the wording alone cannot prove a new claim
    assert "[WARN] humanizer guard" in out and "shares few words with the draft" in out


def test_gate_draft_that_fails_leaves_no_snapshot_behind(tmp_path, home, capsys):
    run = _letters_run(tmp_path)
    assert _gate_draft("letters", run, capsys)[0] == 0
    # a new draft that fails its own checks: the old snapshot must not survive it
    _write(run, "short_letter.json", _short_letter(100))
    code, out = _gate_draft("letters", run, capsys)
    assert code == 1
    assert "draft snapshot saved" not in out
    assert not (run / "_prep" / "pre_humanize" / "letter.json").exists()


def test_gate_draft_is_refused_outside_the_humanized_stages(tmp_path, home, capsys):
    run = _run(tmp_path, {"tailored_cv.json": _clean_cv(), **_fact_base()})
    with pytest.raises(SystemExit) as e:
        cmd_gate(None, Namespace(stage="cv", folder=str(run), cv=None, draft=True))
    assert e.value.code == 2
    assert not (run / "_prep" / "pre_humanize").exists()


def test_gate_linkedin_draft_then_out_of_scope_edit_fails(tmp_path, home, capsys):
    run = _run(tmp_path, {"linkedin.json": {"variants": [
        {"target": "recruiter", "subject_hint": "Connection request", "message": "Bonjour, échange possible ?"}]}})
    assert _gate_draft("linkedin", run, capsys)[0] == 0
    edited = {"variants": [
        {"target": "recruiter", "subject_hint": "Connection", "message": "Bonjour, un échange est-il possible ?"}]}
    _write(run, "linkedin.json", edited)
    code, out = _gate("linkedin", run, capsys)
    assert code == 1
    assert "the pass changed 'variants[0].subject_hint'" in out


def test_read_cv_prints_paragraphs_then_tables(home, capsys):
    cmd_read_cv(None, Namespace(cv=None))
    assert capsys.readouterr().out.splitlines() == [
        "[Normal] Alex Dupont",
        "[Heading 1] Senior Engineer, C++ and API platforms.",
        "[Normal] 2025 — Product Builder No-Code, École Cube (RNCP Niveau 6)",
        "--- TABLE 0 ---",
        "Langages | C++, Python (scripts)",
        "Familier / a approfondir | Docker",
    ]


def test_read_cv_missing_cv_exits_2(tmp_path):
    with pytest.raises(SystemExit) as e:
        cmd_read_cv(None, Namespace(cv=str(tmp_path / "missing.docx")))
    assert e.value.code == 2


def _cold_linkedin(connection: str, direct: str) -> dict:
    return {"outreach_type": "cold", "variants": [
        {"target": "hiring_manager", "contact_name": "Jo Martin", "subject_hint": "Connection request",
         "message": connection},
        {"target": "hiring_manager", "contact_name": "Jo Martin",
         "subject_hint": "Direct message — post-acceptance", "message": direct},
    ]}


def test_gate_linkedin_passes_messages_within_limits(tmp_path, home, capsys):
    run = _run(tmp_path, {"linkedin.json": _cold_linkedin("x" * 300, "y" * 700)})
    code, out = _gate("linkedin", run, capsys)
    assert code == 0, out
    assert "[PASS] linkedin message lengths" in out


def test_gate_linkedin_fails_over_the_cold_limits(tmp_path, home, capsys):
    run = _run(tmp_path, {"linkedin.json": _cold_linkedin("x" * 301, "y" * 750)})
    code, out = _gate("linkedin", run, capsys)
    assert code == 1
    assert "variants[0] (Jo Martin, connection request): 301 characters, limit 300 - cut 1" in out
    assert "variants[1] (Jo Martin, direct message): 750 characters, limit 700 - cut 50" in out


def test_gate_linkedin_offer_messages_only_warn_over_500(tmp_path, home, capsys):
    run = _run(tmp_path, {"linkedin.json": _linkedin("z" * 620)})
    code, out = _gate("linkedin", run, capsys)
    assert code == 0, out
    assert "[WARN] linkedin message lengths (non-blocking)" in out
    assert "620 characters - the prompt prefers at most 500" in out


def _interview_md(*, fit: str = "72", banner: str = "## Fit Score: {fit}% — GOOD",
                  quick: str = "## Quick Reference", sections: int = 10, filler: int = 600,
                  gaps_line: str | None = "Required skills missing: 0") -> str:
    parts = ["# Interview Preparation", quick, "- **Job offer**: https://example.com/job",
             banner.format(fit=fit), "Direct matches: 2 | Transferable: 1 | Gaps: 0"]
    if gaps_line is not None:
        parts.append(gaps_line)
    for i in range(sections):
        parts += [f"## Section {i}", "x" * filler]
    return "\n\n".join(parts) + "\n"


def _interview_run(tmp_path: Path, md: str | None, fit_pct: float = 72.4) -> Path:
    ma = load_fixture("sample_match_analysis.json")
    ma["match_summary"]["overall_fit_pct"] = fit_pct
    run = _run(tmp_path, {"match_analysis.json": ma})
    if md is not None:
        (run / "_prep" / "interview_prep.md").write_text(md, encoding="utf-8")
    return run


def test_gate_interview_passes_a_complete_prep(tmp_path, home, capsys):
    code, out = _gate("interview", _interview_run(tmp_path, _interview_md()), capsys)
    assert code == 0, out
    assert "[PASS] interview prep completeness" in out


def test_gate_interview_accepts_french_headings_and_decimal_fit(tmp_path, home, capsys):
    md = _interview_md(fit="72,4", banner="## Score d'adéquation : {fit} % — BON",
                       quick="## Références rapides")
    code, out = _gate("interview", _interview_run(tmp_path, md), capsys)
    assert code == 0, out


def test_gate_interview_fails_when_the_file_is_missing(tmp_path, home, capsys):
    code, out = _gate("interview", _interview_run(tmp_path, None), capsys)
    assert code == 1
    assert "interview_prep.md not found" in out


def test_gate_interview_reports_every_sign_of_truncation(tmp_path, home, capsys):
    md = _interview_md(quick="## Overview", sections=3, filler=50)
    code, out = _gate("interview", _interview_run(tmp_path, md), capsys)
    assert code == 1
    assert "characters - a complete prep is 6,000+" in out
    assert "5 '## ' sections, expected at least 8" in out
    assert "no Quick Reference section" in out


def test_gate_interview_fails_on_a_fit_score_from_another_run(tmp_path, home, capsys):
    code, out = _gate("interview", _interview_run(tmp_path, _interview_md(fit="58"), fit_pct=72.4), capsys)
    assert code == 1
    assert "fit score banner says 58% but match_analysis.json says 72.4%" in out


def test_gate_interview_fails_without_a_fit_banner(tmp_path, home, capsys):
    md = _interview_md(banner="## Summary")
    code, out = _gate("interview", _interview_run(tmp_path, md), capsys)
    assert code == 1
    assert "no fit score banner" in out


def _required_gaps_run(tmp_path: Path, md: str) -> Path:
    """A run whose matches[] rate two required skills `gap`; match_summary is
    left as the fixture has it (no required_gap_count), as before `gate match`."""
    run = _interview_run(tmp_path, md)
    ma = json.loads((run / "_prep" / "match_analysis.json").read_text(encoding="utf-8"))
    ma["matches"] += [{"requirement": r, "category": "required_skill", "match_type": "gap", "evidence": ""}
                      for r in ("Kubernetes", "Master's degree")]
    (run / "_prep" / "match_analysis.json").write_text(json.dumps(ma), encoding="utf-8")
    return run


@pytest.mark.parametrize("line", [
    "Required skills missing: 2 (Kubernetes, Master's degree)",
    "**Compétences requises manquantes : 2** (Kubernetes, Master)",
])
def test_gate_interview_checks_the_required_skills_missing_line(tmp_path, home, capsys, line):
    code, out = _gate("interview", _required_gaps_run(tmp_path, _interview_md(gaps_line=line)), capsys)
    assert code == 0, out


def test_gate_interview_fails_on_a_missing_or_wrong_required_gaps_line(tmp_path, home, capsys):
    code, out = _gate("interview", _required_gaps_run(tmp_path, _interview_md(gaps_line=None)), capsys)
    assert code == 1 and "no 'Required skills missing: 2' line" in out
    md = _interview_md(gaps_line="Required skills missing: 0")
    code, out = _gate("interview", _required_gaps_run(tmp_path / "b", md), capsys)
    assert code == 1 and "banner says 0 required skills missing but match_analysis.json says 2" in out


def test_gate_interview_counts_required_gaps_from_the_rows_not_the_stored_summary(tmp_path, home, capsys):
    # The result must not depend on whether `gate match` has written required_gap_count yet.
    md = _interview_md(gaps_line=None)
    run = _interview_run(tmp_path, md)  # fixture summary has no required_gap_count
    code, out = _gate("interview", run, capsys)
    assert code == 1 and "no 'Required skills missing: 0' line" in out
    _gate("match", run, capsys)  # whatever it writes, the interview result is the same
    code2, out2 = _gate("interview", run, capsys)
    assert code2 == code and "no 'Required skills missing: 0' line" in out2
