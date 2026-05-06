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
    assert errors == []


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
    assert errors == []
    assert warnings == []


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
    assert len(errors) == 1
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
    assert len(errors) == 1
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
    assert len(errors) == 1
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
    assert errors == []
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
    assert errors == []


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
    assert errors == []


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
    assert errors == []


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
    assert errors == []
    assert len(warnings) == 1
    assert "Docker" in warnings[0]


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
    assert errors == []


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
    assert errors == []
