"""Tests for scripts/check_role_grounding.py — the post-Step-4 guard against
company tech_stack_hints leaking into candidate-side emphasis_areas / rationale.

The script lives in the sibling job-application-tailor skill so both flows
can call it; conftest.py adds that skill root to sys.path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.check_role_grounding import check  # type: ignore  # via conftest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fact_base() -> dict:
    """A minimal but realistic fact base — Eddie's stack: SQL Server + Dapper, no EF."""
    return {
        "summary": "Ingénieur logiciel avec 35 ans d'expérience en C# / .NET.",
        "skills": ["Architecture de services", "Reverse engineering"],
        "technologies": ["C#", ".NET", ".NET Core", "SQL Server", "Dapper", "WPF", "WinForms"],
        "methodologies": ["Clean Architecture", "SOLID"],
        "experience": [
            {
                "company": "Oodrive",
                "details": [
                    "Migration .NET Remoting / WCF vers gRPC, puis migration vers .NET Core multi-OS."
                ],
            }
        ],
    }


def _company_with_ef() -> dict:
    return {
        "company_name": "agap2",
        "canonical_url": "https://www.agap2.fr",
        "size_band": "enterprise",
        "mission_statement": "x",
        "products_services": ["consulting"],
        "research_gaps": [],
        "sources": [{"url": "https://www.agap2.fr/", "fetched_at": "2026-05-06T00:00:00Z"}],
        "generated_at": "2026-05-06T00:00:00Z",
        "input_raw": "agap2",
        "tech_stack_hints": [
            "C# / .NET / .NET Core / WPF / WinForms / Blazor",
            "SQL Server / Entity Framework",
            "Azure DevOps, Git",
        ],
    }


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Clean cases
# ---------------------------------------------------------------------------


def test_clean_candidates_no_violations(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _write(tmp_path, "cp.json", _company_with_ef())
    candidates = {
        "candidates": [
            {
                "title": "Consultant Senior C#/.NET",
                "rationale": "Stack agap2IT (.NET Core, WPF, WinForms, SQL Server) recouvre les 15 ans d'Eddie.",
                "seniority_band": "senior",
                "emphasis_areas": [
                    "C#/.NET / .NET Core / WPF / WinForms",
                    "SQL Server",
                    "Architecture de services",
                ],
            }
        ],
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "rc.json", candidates)
    issues = check(target, "candidates", cp, fb)
    assert issues == []


def test_domain_phrase_does_not_false_positive(tmp_path):
    """'Architecture de services' isn't in tech_stack_hints — must not be flagged."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _write(tmp_path, "cp.json", _company_with_ef())
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": ["Architecture de services et migration legacy → moderne"],
        "rationale": "Composition typique de clients industriels.",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    assert check(target, "selected", cp, fb) == []


def test_synonym_matches_dotnet_against_dot_net(tmp_path):
    """Company says 'dotnet'; candidate fact base has '.NET'. Same canonical form."""
    fb = _fact_base()
    cp = _company_with_ef()
    cp["tech_stack_hints"] = ["dotnet, dotnet core"]
    fbp = _write(tmp_path, "fb.json", fb)
    cpp = _write(tmp_path, "cp.json", cp)
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": [".NET / .NET Core"],
        "rationale": "y",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    assert check(target, "selected", cpp, fbp) == []


# ---------------------------------------------------------------------------
# Failing cases — exactly the agap2 leak
# ---------------------------------------------------------------------------


def test_ef_in_emphasis_areas_fails(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _write(tmp_path, "cp.json", _company_with_ef())
    candidates = {
        "candidates": [
            {
                "title": "Consultant Senior C#/.NET",
                "rationale": "Stack alignée.",
                "seniority_band": "senior",
                "emphasis_areas": ["SQL Server / Entity Framework"],
            }
        ],
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "rc.json", candidates)
    issues = check(target, "candidates", cp, fb)
    assert len(issues) == 1
    assert "Entity Framework" in issues[0]
    assert "[emphasis_areas]" in issues[0]


def test_ef_in_rationale_fails(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _write(tmp_path, "cp.json", _company_with_ef())
    candidates = {
        "candidates": [
            {
                "title": "Consultant Senior C#/.NET",
                "rationale": (
                    "agap2IT publie une offre dont la stack — C#, .NET Core, "
                    "WPF, Winforms, SQL Server, Entity Framework, Azure DevOps "
                    "— recouvre presque ligne pour ligne le parcours d'Eddie."
                ),
                "seniority_band": "senior",
                "emphasis_areas": ["C#/.NET"],
            }
        ],
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "rc.json", candidates)
    issues = check(target, "candidates", cp, fb)
    rationale_issues = [i for i in issues if "[rationale]" in i]
    # The rationale lists multiple ungrounded company techs; we care that EF is
    # among them — additional flags (e.g. Azure DevOps when not in fact base)
    # are legitimate and we must not over-constrain the count.
    assert any("entity framework" in i.lower() for i in rationale_issues)


def test_selected_role_emphasis_leak_fails(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _write(tmp_path, "cp.json", _company_with_ef())
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": ["SQL Server", "Entity Framework"],
        "rationale": "y",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    issues = check(target, "selected", cp, fb)
    assert len(issues) == 1
    assert "Entity Framework" in issues[0]
    assert "selected_role.emphasis_areas" in issues[0]


def test_user_override_with_leaked_tech_caught(tmp_path):
    """Free-form user override that mentions a tech they don't have."""
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _write(tmp_path, "cp.json", _company_with_ef())
    selected = {
        "title": "Senior Engineer — Entity Framework expert",
        "source": "user_override",
        "seniority_band": "senior",
        "emphasis_areas": ["Entity Framework"],
        "rationale": "user override",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    issues = check(target, "selected", cp, fb)
    assert any("Entity Framework" in i for i in issues)


def test_blazor_in_company_only_caught(tmp_path):
    """Blazor is in company stack but not in fact base → must be flagged when claimed."""
    fb = _fact_base()
    fb["technologies"] = ["C#", ".NET", "SQL Server"]  # no Blazor
    cp = _company_with_ef()
    fbp = _write(tmp_path, "fb.json", fb)
    cpp = _write(tmp_path, "cp.json", cp)
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": ["Blazor / WPF"],
        "rationale": "y",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    issues = check(target, "selected", cpp, fbp)
    assert any("Blazor" in i or "blazor" in i for i in issues)
    # WPF is not flagged because it's not in this fact base's tech list either,
    # but it IS in company hints… so it should also be flagged. Check explicitly:
    flagged = " ".join(issues).lower()
    assert "blazor" in flagged
    assert "wpf" in flagged


def test_blazor_when_in_fact_base_passes(tmp_path):
    fb = _fact_base()
    fb["technologies"] = fb["technologies"] + ["Blazor"]  # add Blazor
    cp = _company_with_ef()
    fbp = _write(tmp_path, "fb.json", fb)
    cpp = _write(tmp_path, "cp.json", cp)
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": ["Blazor / WPF / WinForms"],
        "rationale": "y",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    assert check(target, "selected", cpp, fbp) == []


def test_grounded_in_prose_not_arrays(tmp_path):
    """A tech mentioned only in experience.details prose still grounds the candidate."""
    fb = _fact_base()
    fb["technologies"] = ["C#", ".NET", "SQL Server"]  # no Blazor in arrays
    fb["experience"][0]["details"].append(
        "POC Blazor WebAssembly pour découpler UI client et service backend."
    )
    cp = _company_with_ef()
    fbp = _write(tmp_path, "fb.json", fb)
    cpp = _write(tmp_path, "cp.json", cp)
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": ["Blazor"],
        "rationale": "y",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    assert check(target, "selected", cpp, fbp) == []


def test_company_with_no_tech_hints_is_noop(tmp_path):
    fb = _write(tmp_path, "fb.json", _fact_base())
    cp = _company_with_ef()
    cp["tech_stack_hints"] = []
    cpp = _write(tmp_path, "cp.json", cp)
    selected = {
        "title": "x",
        "source": "candidate_pick",
        "seniority_band": "senior",
        "emphasis_areas": ["Entity Framework"],
        "rationale": "y",
        "generated_at": "2026-05-06T00:00:00Z",
        "company_name": "agap2",
    }
    target = _write(tmp_path, "sr.json", selected)
    assert check(target, "selected", cpp, fb) == []
