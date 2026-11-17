"""Tests for scripts/check_match_grounding.py — the offer-flow Step 4 guard
against `direct` match claims whose tech tokens aren't actually in the fact base.

Mirrors the cold-prospect skill's test_role_grounding.py in shape; same
synonym map and vocab logic via _grounding_common.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_match_grounding import check  # type: ignore  # via conftest


def _fact_base() -> dict:
    return {
        "summary": "Ingénieur logiciel avec 35 ans d'expérience en C# / .NET.",
        "skills": ["Architecture de services", "Reverse engineering"],
        "technologies": ["C#", ".NET", ".NET Core", "SQL Server", "Dapper", "WPF", "WinForms", "gRPC"],
        "methodologies": ["Clean Architecture", "SOLID", "Agile"],
        "experience": [
            {
                "company": "Oodrive",
                "details": [
                    "Migration .NET Remoting / WCF vers gRPC, puis migration vers .NET Core multi-OS.",
                    "POC Blazor WebAssembly pour découpler UI client et service backend.",
                ],
            }
        ],
    }


def _offer_with_kubernetes() -> dict:
    return {
        "job_title": "Senior .NET Engineer",
        "company_name": "Acme",
        "required_skills": ["C#", ".NET Core", "Kubernetes"],
        "preferred_skills": ["Docker", "Entity Framework"],
        "responsibilities": ["Build services", "Lead architecture"],
        "technologies": ["WPF", "Blazor", "Kubernetes", "Entity Framework"],
        "ats_keywords": ["c#", "kubernetes"],
    }


def _other(messages: list[str]) -> list[str]:
    """Messages other than the missing-technology gap-row one (tested on its own
    below). Tests here use partial match lists, so that check would fire on
    every one of them; since 2026-11-17 it is an error, not a warning."""
    return [m for m in messages if "offer technology" not in m]


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Clean cases
# ---------------------------------------------------------------------------


def test_all_directs_grounded_passes(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 3, "transferable_count": 0, "gap_count": 2, "overall_fit_pct": 60},
        "matches": [
            {"requirement": "C#", "category": "required_skill", "match_type": "direct", "evidence": "15 ans"},
            {"requirement": ".NET Core", "category": "required_skill", "match_type": "direct", "evidence": "Oodrive"},
            {"requirement": "Blazor", "category": "technology", "match_type": "direct", "evidence": "POC chez Oodrive"},
            {"requirement": "Kubernetes", "category": "required_skill", "match_type": "gap", "evidence": ""},
            {"requirement": "Entity Framework", "category": "preferred_skill", "match_type": "gap", "evidence": ""},
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert _other(errors) == []


def test_transferable_with_notes_passes(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 0, "transferable_count": 1, "gap_count": 0, "overall_fit_pct": 50},
        "matches": [
            {
                "requirement": "Docker",
                "category": "preferred_skill",
                "match_type": "transferable",
                "notes": "Conteneurisation Docker chez Oodrive (CI/CD)",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert _other(errors) == []
    assert _other(warnings) == []


# ---------------------------------------------------------------------------
# Failing cases
# ---------------------------------------------------------------------------


def test_false_direct_kubernetes_fails(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {
                "requirement": "Kubernetes",
                "category": "required_skill",
                "match_type": "direct",
                "evidence": "",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert len(_other(errors)) == 1
    assert "Kubernetes" in errors[0].lower() or "kubernetes" in errors[0].lower()


def test_false_direct_ef_fails(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {
                "requirement": "Entity Framework",
                "category": "preferred_skill",
                "match_type": "direct",
                "evidence": "",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert len(_other(errors)) == 1
    assert "entity framework" in errors[0].lower()


def test_compound_requirement_partial_grounding_flags_only_ungrounded(tmp_path):
    """A direct match for 'C# / Kubernetes' grounds C# but not Kubernetes — must still flag."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {
                "requirement": "C# / Kubernetes",
                "category": "required_skill",
                "match_type": "direct",
                "evidence": "",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert len(_other(errors)) == 1
    assert "kubernetes" in errors[0].lower()
    # Make sure C# alone wouldn't be flagged
    assert "'c#'" not in errors[0].lower()


def test_softskill_direct_match_warns_not_blocks(tmp_path):
    """Soft-skill claims (no tech shape — no '.', '#', '/', no all-caps acronym,
    no CamelCase) become warnings, not blocking errors. Cross-language soft-skill
    matching is too unreliable to gate the pipeline on."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = {
        "job_title": "Lead",
        "company_name": "Acme",
        "required_skills": ["Team leadership"],
        "preferred_skills": [],
        "responsibilities": [],
        "technologies": [],
        "ats_keywords": [],
    }
    offp = _write(tmp_path, "off.json", off)
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {
                "requirement": "Team leadership",
                "category": "required_skill",
                "match_type": "direct",
                "evidence": "",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, offp, fb)
    assert _other(errors) == []
    assert any("team leadership" in w.lower() for w in warnings)


def test_softskill_with_grounding_via_skills_array_passes(tmp_path):
    """Same soft-skill claim but the fact base has the relevant skill — passes."""
    fb = _fact_base()
    fb["skills"] = fb["skills"] + ["Team leadership"]
    fbp = _write(tmp_path, "fb.json", fb)
    off = {
        "job_title": "Lead",
        "company_name": "Acme",
        "required_skills": ["Team leadership"],
        "preferred_skills": [],
        "responsibilities": [],
        "technologies": [],
        "ats_keywords": [],
    }
    offp = _write(tmp_path, "off.json", off)
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {
                "requirement": "Team leadership",
                "category": "required_skill",
                "match_type": "direct",
                "evidence": "Development Manager chez Telmar",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, offp, fbp)
    assert _other(errors) == []


def test_grounded_via_prose_passes(tmp_path):
    """Tech only mentioned in experience details (e.g. Blazor) still grounds the candidate."""
    fb = _fact_base()
    fb["technologies"] = ["C#", ".NET", ".NET Core", "SQL Server"]  # no Blazor in arrays
    fbp = _write(tmp_path, "fb.json", fb)
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {
                "requirement": "Blazor",
                "category": "technology",
                "match_type": "direct",
                "evidence": "POC chez Oodrive",
            }
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, fbp, fbp)  # noqa: just ensures fixtures present
    errors, warnings = check(target, off, fbp)
    assert _other(errors) == []


def test_synonym_match_dotnet_vs_dot_net(tmp_path):
    """Job offer says 'dotnet'; fact base has '.NET'. Same canonical form → grounded."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _offer_with_kubernetes()
    off["required_skills"] = ["dotnet", "dotnet core"]
    offp = _write(tmp_path, "off.json", off)
    ma = {
        "match_summary": {"direct_count": 2, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {"requirement": "dotnet", "category": "required_skill", "match_type": "direct"},
            {"requirement": "dotnet core", "category": "required_skill", "match_type": "direct"},
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, offp, fb)
    assert _other(errors) == []


def test_transferable_without_notes_warns(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 0, "transferable_count": 1, "gap_count": 0, "overall_fit_pct": 50},
        "matches": [
            {"requirement": "Docker", "category": "preferred_skill", "match_type": "transferable"}
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert _other(errors) == []
    assert len(_other(warnings)) == 1
    assert "Docker" in _other(warnings)[0]


def test_versioned_tech_grounded_by_unversioned_fact_base(tmp_path):
    """'.NET 4.8' in JD + '.NET' in fact base → grounded. 'SQL Server 2022' → 'SQL Server'."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _offer_with_kubernetes()
    off["required_skills"] = [".NET 4.8", "SQL Server 2022"]
    offp = _write(tmp_path, "off.json", off)
    ma = {
        "match_summary": {"direct_count": 2, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {"requirement": ".NET 4.8", "category": "required_skill", "match_type": "direct"},
            {"requirement": "SQL Server 2022", "category": "required_skill", "match_type": "direct"},
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, offp, fb)
    assert _other(errors) == []


def test_tech_shape_gate_acronym_caught(tmp_path):
    """Acronym tech (WPF, REST, SQL) is tech-shaped → blocking error if ungrounded."""
    fb = _fact_base()
    fb["technologies"] = ["C#", ".NET"]  # remove WPF
    fbp = _write(tmp_path, "fb.json", fb)
    off = _offer_with_kubernetes()
    off["required_skills"] = ["WPF"]
    offp = _write(tmp_path, "off.json", off)
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {"requirement": "WPF", "category": "required_skill", "match_type": "direct"},
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, offp, fbp)
    assert any("wpf" in e.lower() for e in errors)


def test_tech_shape_gate_camelcase_caught(tmp_path):
    """CamelCase tech (MongoDB, TypeScript) is tech-shaped → error if ungrounded."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _offer_with_kubernetes()
    off["required_skills"] = ["MongoDB"]
    offp = _write(tmp_path, "off.json", off)
    ma = {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [
            {"requirement": "MongoDB", "category": "required_skill", "match_type": "direct"},
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, offp, fb)
    assert any("mongodb" in e.lower() for e in errors)


def test_gap_matches_never_flagged(tmp_path):
    """Even if a gap match's requirement is tech-shaped and ungrounded, it's not an error."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = {
        "match_summary": {"direct_count": 0, "transferable_count": 0, "gap_count": 2, "overall_fit_pct": 0},
        "matches": [
            {"requirement": "Kubernetes", "category": "technology", "match_type": "gap", "evidence": ""},
            {"requirement": "Entity Framework", "category": "preferred_skill", "match_type": "gap", "evidence": ""},
        ],
    }
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert _other(errors) == []


# ---------------------------------------------------------------------------
# Merged fact base (claims_guard merge output)
# ---------------------------------------------------------------------------


def _merged_fact_base() -> dict:
    fb = _fact_base()
    fb["technologies"] = fb["technologies"] + ["ASP .Net Core", "Docker"]
    fb["addendum_hidden_skills"] = ["Kubernetes (cluster perso, k3s)"]
    fb["addendum_off_cv_facts"] = ["Formation Entity Framework suivie en 2024"]
    fb["addendum_skill_calibration"] = ["**WCF** maintenance only"]
    fb["familiar_only_skills"] = ["ASP .Net Core", "Docker", "CI/CD"]
    return fb


def _single_direct(requirement: str) -> dict:
    return {
        "match_summary": {"direct_count": 1, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 100},
        "matches": [{"requirement": requirement, "category": "required_skill",
                     "match_type": "direct", "evidence": "x"}],
    }


def test_merged_fact_base_grounds_addendum_only_skill(tmp_path):
    fb = _write(tmp_path, "fb.json", _merged_fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    target = _write(tmp_path, "ma.json", _single_direct("Kubernetes"))
    errors, _ = check(target, off, fb)
    assert _other(errors) == []


def test_familiar_only_skill_cannot_be_direct(tmp_path):
    fb = _write(tmp_path, "fb.json", _merged_fact_base())
    off = _write(tmp_path, "off.json", {**_offer_with_kubernetes(), "technologies": ["ASP.NET Core", "Docker"]})
    for req in ("ASP.NET Core", "Docker", "CI/CD"):
        target = _write(tmp_path, "ma.json", _single_direct(req))
        errors, _ = check(target, off, fb)
        assert any("familiar-only" in e for e in errors), req


def test_familiar_only_skill_as_transferable_is_fine(tmp_path):
    fb = _write(tmp_path, "fb.json", _merged_fact_base())
    off = _write(tmp_path, "off.json", _offer_with_kubernetes())
    ma = _single_direct("Docker")
    ma["matches"][0].update(match_type="transferable", notes="Docker en usage ponctuel")
    target = _write(tmp_path, "ma.json", ma)
    errors, warnings = check(target, off, fb)
    assert _other(errors) == [] and _other(warnings) == []


# ---------------------------------------------------------------------------
# Alternatives lists ("X, Y ou équivalents")
# ---------------------------------------------------------------------------


def _automation_fact_base() -> dict:
    fb = _merged_fact_base()
    fb["technologies"] = fb["technologies"] + ["Make", "Claude Code", "n8n"]
    fb["familiar_only_skills"] = fb["familiar_only_skills"] + ["n8n"]
    return fb


def _automation_offer() -> dict:
    return {**_offer_with_kubernetes(),
            "technologies": ["Make", "Zapier", "n8n", "Cursor", "Claude Code", "Codex", "Supabase", "Kubernetes"],
            "required_skills": ["Make, Zapier, n8n ou équivalents", "Formation Bac+3 à Bac+5 en informatique"]}


def _direct_errors(tmp_path, requirement: str) -> tuple[list[str], list[str]]:
    fb = _write(tmp_path, "fb.json", _automation_fact_base())
    off = _write(tmp_path, "off.json", _automation_offer())
    return check(_write(tmp_path, "ma.json", _single_direct(requirement)), off, fb)


@pytest.mark.parametrize("requirement", [
    "Make, Zapier, n8n ou équivalents",       # Make covers Zapier; n8n is not the member relied on
    "Cursor, Claude Code, Codex ou équivalents",
    "Zapier or Make",
    "Make ou Zapier",
])
def test_alternatives_list_is_satisfied_by_one_grounded_member(tmp_path, requirement):
    errors, warnings = _direct_errors(tmp_path, requirement)
    assert _other(errors) == [], errors
    assert _other(warnings) == [], warnings


def test_alternatives_list_with_no_grounded_member_still_fails(tmp_path):
    errors, _ = _direct_errors(tmp_path, "Zapier ou Cursor")
    assert len(_other(errors)) == 1 and "'zapier'" in _other(errors)[0] and "'cursor'" in _other(errors)[0]


def test_familiar_only_member_cannot_satisfy_an_alternatives_list(tmp_path):
    errors, _ = _direct_errors(tmp_path, "n8n ou Zapier")
    assert any("'n8n' is familiar-only" in e for e in errors)
    assert any("'zapier'" in e for e in errors)


def test_alternatives_do_not_cross_an_and(tmp_path):
    errors, _ = _direct_errors(tmp_path, "Make ou Zapier, et Supabase")
    assert len(_other(errors)) == 1 and "'supabase'" in _other(errors)[0] and "zapier" not in _other(errors)[0]


def test_unnamed_equivalents_warn_instead_of_blocking(tmp_path):
    errors, warnings = _direct_errors(tmp_path, "Bases de données relationnelles (Supabase ou alternatives)")
    assert _other(errors) == []
    assert any("none of 'supabase' is in cv_fact_base" in w and "accepts equivalents" in w for w in warnings)


def test_degree_level_is_not_a_tech_token(tmp_path):
    errors, warnings = _direct_errors(tmp_path, "Formation Bac+3 à Bac+5 en informatique")
    assert _other(errors) == []
    assert any("bac+3" in w for w in warnings)  # still surfaced, as a soft token


# ---------------------------------------------------------------------------
# A missing offer technology needs its own gap row
# ---------------------------------------------------------------------------


def _rows(*rows) -> dict:
    return {"match_summary": {"direct_count": 0, "transferable_count": 0, "gap_count": 0, "overall_fit_pct": 0},
            "matches": [{"requirement": r, "category": "preferred_skill", "match_type": t, "evidence": "x", "notes": "x"}
                        for r, t in rows]}


def _tech_warnings(tmp_path, offer_techs, *rows) -> list[str]:
    """The missing-technology gap-row messages - errors since 2026-11-17."""
    fb = _write(tmp_path, "fb.json", _automation_fact_base())
    off = _write(tmp_path, "off.json", {**_automation_offer(), "technologies": offer_techs})
    errors, warnings = check(_write(tmp_path, "ma.json", _rows(*rows)), off, fb)
    assert not [w for w in warnings if "offer technology" in w]  # never a mere warning any more
    return [e for e in errors if "offer technology" in e]


def test_missing_tech_folded_into_a_transferable_row_blocks(tmp_path):
    w = _tech_warnings(tmp_path, ["SQL Server", "Edge Functions"],
                       ("SQL Server, Edge Functions, modélisation de données", "transferable"))
    assert len(w) == 1 and "'Edge Functions'" in w[0] and "matches[0] (transferable)" in w[0]


def test_missing_tech_with_its_own_gap_row_is_fine(tmp_path):
    assert _tech_warnings(tmp_path, ["Edge Functions"],
                          ("PostgreSQL, Edge Functions, modélisation de données", "transferable"),
                          ("Edge Functions", "gap")) == []


def test_missing_tech_no_row_at_all_blocks(tmp_path):
    w = _tech_warnings(tmp_path, ["Supabase"], ("Make", "direct"))
    assert len(w) == 1 and "no row assesses it" in w[0]


@pytest.mark.parametrize("tech", ["Make", "REST", "Claude", "n8n"])
def test_held_partially_named_or_familiar_tech_is_not_flagged(tmp_path, tech):
    # Make is held; REST / Claude sit inside "REST APIs" / "Claude Code"; n8n is familiar-only.
    fb = _automation_fact_base()
    fb["technologies"] = fb["technologies"] + ["REST APIs"]
    off = _write(tmp_path, "off.json", {**_automation_offer(), "technologies": [tech]})
    errors, warnings = check(_write(tmp_path, "ma.json", _rows((tech, "transferable"))), off,
                             _write(tmp_path, "fb.json", fb))
    assert not [x for x in errors + warnings if "offer technology" in x]


def test_member_of_a_satisfied_alternatives_list_is_not_flagged(tmp_path):
    assert _tech_warnings(tmp_path, ["Make", "Zapier"], ("Make, Zapier ou équivalents", "direct")) == []


@pytest.mark.parametrize("requirement", [
    "Experience or strong interest in SaaS, cloud platforms and B2B products",
    "Expérience ou fort intérêt pour le SaaS",
])
def test_lead_in_wording_is_not_part_of_the_skill(tmp_path, requirement):
    # "strong interest in SaaS" used to be read as one tech token and block a grounded direct
    fb = _fact_base()
    fb["experience"][0]["details"].append("Projet SaaS cloud-to-cloud B2B.")
    off = _write(tmp_path, "off.json", {**_offer_with_kubernetes(), "required_skills": [requirement]})
    ma = {"match_summary": {}, "matches": [
        {"requirement": requirement, "category": "required_skill", "match_type": "direct", "evidence": "Oodrive"}]}
    errors, _ = check(_write(tmp_path, "ma.json", ma), off, _write(tmp_path, "fb.json", fb))
    assert _other(errors) == []


def test_lead_in_does_not_hide_a_missing_technology(tmp_path):
    req = "Strong experience with Kubernetes"
    off = _write(tmp_path, "off.json", {**_offer_with_kubernetes(), "required_skills": [req]})
    ma = {"match_summary": {}, "matches": [
        {"requirement": req, "category": "required_skill", "match_type": "direct", "evidence": "x"}]}
    errors, _ = check(_write(tmp_path, "ma.json", ma), off, _write(tmp_path, "fb.json", _fact_base()))
    assert any("kubernetes" in e.lower() for e in _other(errors))


# ---------------------------------------------------------------------------
# Lists of examples ("etc.", "e.g.", "such as", "comme") - 2026-11-17
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("requirement", [
    "No-code automation tools (Zapier, n8n, Make, etc.)",
    "Outils d'automatisation (e.g. Zapier, Make)",
    "Automation tools such as Zapier, Make",
    "Outils no-code tels que Zapier, Make",
])
def test_a_list_of_examples_is_satisfied_by_one_grounded_member(tmp_path, requirement):
    errors, warnings = _direct_errors(tmp_path, requirement)
    assert _other(errors) == [], errors


def test_a_list_of_examples_with_no_grounded_member_warns_instead_of_blocking(tmp_path):
    errors, warnings = _direct_errors(tmp_path, "Outils (Zapier, Cursor, etc.)")
    assert _other(errors) == []
    assert any("accepts equivalents" in w for w in warnings)


def test_a_bracketed_list_without_a_marker_still_requires_every_member(tmp_path):
    errors, _ = _direct_errors(tmp_path, "Outils (Zapier, Make)")
    assert any("'zapier'" in e for e in _other(errors))


# ---------------------------------------------------------------------------
# A technology a skill item names has no row of its own (scripts/match_rows.py)
# ---------------------------------------------------------------------------


def _absorbed(tmp_path, match_type: str) -> list[str]:
    off = {**_automation_offer(), "technologies": ["Supabase"],
           "required_skills": ["Bases de données avec Supabase"]}
    ma = {"match_summary": {}, "matches": [{"requirement": "Bases de données avec Supabase",
                                            "category": "required_skill", "match_type": match_type,
                                            "evidence": "SQL Server", "notes": "SQL Server, pas Supabase"}]}
    errors, _ = check(_write(tmp_path, "ma.json", ma), _write(tmp_path, "off.json", off),
                      _write(tmp_path, "fb.json", _automation_fact_base()))
    return errors


def test_missing_tech_named_in_a_skill_item_needs_no_gap_row_of_its_own(tmp_path):
    assert _absorbed(tmp_path, "transferable") == []


def test_missing_tech_named_in_a_skill_item_still_keeps_the_row_off_direct(tmp_path):
    errors = _absorbed(tmp_path, "direct")
    assert any("'supabase'" in e and "at most transferable" in e for e in errors)
    assert not [e for e in errors if "rate its own row" in e or "no row assesses" in e]


def test_absorbed_member_of_a_satisfied_alternatives_list_can_be_direct(tmp_path):
    req = "Vibe coding avec des outils comme Replit ou Claude"  # Claude Code is held, Replit is not
    off = {**_automation_offer(), "technologies": ["Replit", "Claude"], "required_skills": [req]}
    ma = {"match_summary": {}, "matches": [
        {"requirement": req, "category": "required_skill", "match_type": "direct", "evidence": "Claude Code"}]}
    errors, _ = check(_write(tmp_path, "ma.json", ma), _write(tmp_path, "off.json", off),
                      _write(tmp_path, "fb.json", _automation_fact_base()))
    assert errors == []
