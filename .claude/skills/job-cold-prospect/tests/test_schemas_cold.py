"""Schema validation tests for the cold-prospect skill.

Covers the three schemas that live under this skill's own ``schemas/``
directory (``company_profile``, ``role_candidates``, ``selected_role``)
plus the Phase-E extensions to the tailor skill's shared
``linkedin.schema.json`` (``outreach_type`` + ``target_role``).

Validation goes through ``scripts.validate.validate`` so these tests also
exercise the exact code path the SKILL.md bash steps use in production.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate import validate  # type: ignore  # resolved via conftest sys.path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(tmp_path: Path, data: dict, schema_path: Path) -> list[str]:
    p = tmp_path / "data.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return validate(p, schema_path)


def _company_profile_min() -> dict:
    """Smallest valid company_profile.json per the schema's `required` list."""
    return {
        "company_name": "Acme SAS",
        "canonical_url": "https://acme.example",
        "size_band": "scaleup",
        "mission_statement": "Build useful robots.",
        "products_services": ["Robot arms", "Control software"],
        "research_gaps": [],
        "sources": [
            {"url": "https://acme.example/about", "fetched_at": "2026-04-20T10:00:00Z"}
        ],
        "generated_at": "2026-04-20T10:00:00Z",
        "input_raw": "acme",
    }


def _role_candidates_min() -> dict:
    return {
        "candidates": [
            {
                "title": "Tech Lead .NET — Desktop & Services",
                "rationale": "Maps Eddie's long WPF / services tenure to Acme's stated desktop tooling focus.",
                "seniority_band": "lead",
                "emphasis_areas": ["WPF Desktop", "service architecture"],
            }
        ],
        "generated_at": "2026-04-20T10:00:00Z",
        "company_name": "Acme SAS",
    }


def _selected_role_min() -> dict:
    return {
        "title": "Tech Lead .NET — Desktop & Services",
        "source": "candidate_pick",
        "seniority_band": "lead",
        "generated_at": "2026-04-20T10:00:00Z",
        "company_name": "Acme SAS",
    }


# ---------------------------------------------------------------------------
# company_profile.schema.json
# ---------------------------------------------------------------------------


def test_company_profile_minimum_valid(tmp_path, cold_schemas_dir):
    errors = _run(tmp_path, _company_profile_min(), cold_schemas_dir / "company_profile.schema.json")
    assert errors == []


def test_company_profile_rejects_unknown_size_band(tmp_path, cold_schemas_dir):
    data = _company_profile_min()
    data["size_band"] = "massive"
    errors = _run(tmp_path, data, cold_schemas_dir / "company_profile.schema.json")
    assert any("size_band" in e for e in errors), errors


def test_company_profile_rejects_missing_input_raw(tmp_path, cold_schemas_dir):
    """`input_raw` is the audit of the user's original input — it is required
    so we can always trace a profile back to what was asked for."""
    data = _company_profile_min()
    del data["input_raw"]
    errors = _run(tmp_path, data, cold_schemas_dir / "company_profile.schema.json")
    assert any("input_raw" in e for e in errors), errors


def test_company_profile_source_requires_url_and_fetched_at(tmp_path, cold_schemas_dir):
    data = _company_profile_min()
    data["sources"] = [{"url": "https://acme.example/about"}]  # missing fetched_at
    errors = _run(tmp_path, data, cold_schemas_dir / "company_profile.schema.json")
    assert any("fetched_at" in e for e in errors), errors


def test_company_profile_leadership_requires_source_url(tmp_path, cold_schemas_dir):
    """Leadership names without a citable source are exactly what we want to
    keep out of the dossier — the schema enforces that."""
    data = _company_profile_min()
    data["leadership"] = [{"name": "Marie Durand", "role": "CTO"}]  # no source_url
    errors = _run(tmp_path, data, cold_schemas_dir / "company_profile.schema.json")
    assert any("source_url" in e for e in errors), errors


# ---------------------------------------------------------------------------
# role_candidates.schema.json
# ---------------------------------------------------------------------------


def test_role_candidates_minimum_valid(tmp_path, cold_schemas_dir):
    errors = _run(tmp_path, _role_candidates_min(), cold_schemas_dir / "role_candidates.schema.json")
    assert errors == []


def test_role_candidates_rejects_empty_list(tmp_path, cold_schemas_dir):
    data = _role_candidates_min()
    data["candidates"] = []
    errors = _run(tmp_path, data, cold_schemas_dir / "role_candidates.schema.json")
    assert any("candidates" in e for e in errors), errors


def test_role_candidates_rejects_more_than_three(tmp_path, cold_schemas_dir):
    """We cap at 3 so the interactive picker is navigable."""
    data = _role_candidates_min()
    base = data["candidates"][0]
    data["candidates"] = [base, base, base, base]
    errors = _run(tmp_path, data, cold_schemas_dir / "role_candidates.schema.json")
    assert any("candidates" in e for e in errors), errors


def test_role_candidates_rejects_unknown_seniority(tmp_path, cold_schemas_dir):
    data = _role_candidates_min()
    data["candidates"][0]["seniority_band"] = "wizard"
    errors = _run(tmp_path, data, cold_schemas_dir / "role_candidates.schema.json")
    assert any("seniority_band" in e for e in errors), errors


# ---------------------------------------------------------------------------
# selected_role.schema.json
# ---------------------------------------------------------------------------


def test_selected_role_minimum_valid(tmp_path, cold_schemas_dir):
    errors = _run(tmp_path, _selected_role_min(), cold_schemas_dir / "selected_role.schema.json")
    assert errors == []


def test_selected_role_accepts_generalist_path(tmp_path, cold_schemas_dir):
    data = _selected_role_min()
    data.update(
        title="Senior .NET — Desktop & Services, open to scope",
        source="generalist",
        seniority_band="senior",
        candidate_index=None,
    )
    errors = _run(tmp_path, data, cold_schemas_dir / "selected_role.schema.json")
    assert errors == []


def test_selected_role_accepts_user_override(tmp_path, cold_schemas_dir):
    data = _selected_role_min()
    data.update(
        title="Architecte logiciel — Desktop",
        source="user_override",
        seniority_band="unspecified",
        rationale="User wanted to steer the conversation toward architecture.",
    )
    errors = _run(tmp_path, data, cold_schemas_dir / "selected_role.schema.json")
    assert errors == []


def test_selected_role_rejects_unknown_source(tmp_path, cold_schemas_dir):
    data = _selected_role_min()
    data["source"] = "llm_guess"
    errors = _run(tmp_path, data, cold_schemas_dir / "selected_role.schema.json")
    assert any("source" in e for e in errors), errors


def test_selected_role_rejects_missing_company_name(tmp_path, cold_schemas_dir):
    """Without company_name we can't sanity-check that the role was picked
    for the company we actually researched."""
    data = _selected_role_min()
    del data["company_name"]
    errors = _run(tmp_path, data, cold_schemas_dir / "selected_role.schema.json")
    assert any("company_name" in e for e in errors), errors


# ---------------------------------------------------------------------------
# linkedin.schema.json — Phase E extensions must stay backwards-compatible
# ---------------------------------------------------------------------------


def test_linkedin_schema_accepts_legacy_offer_shape(tmp_path, tailor_schemas_dir):
    """Existing offer-flow LinkedIn JSONs omit outreach_type / target_role —
    they must continue to validate exactly as before."""
    data = {
        "variants": [
            {"target": "recruiter", "message": "Hi there, short message."},
            {"target": "hiring_manager", "message": "Hello, another message."},
        ]
    }
    errors = _run(tmp_path, data, tailor_schemas_dir / "linkedin.schema.json")
    assert errors == []


def test_linkedin_schema_accepts_cold_extensions(tmp_path, tailor_schemas_dir):
    data = {
        "outreach_type": "cold",
        "target_role": "Tech Lead .NET — Desktop & Services",
        "variants": [
            {
                "target": "hiring_manager",
                "contact_name": "Marie Durand",
                "linkedin_url": "https://www.linkedin.com/in/marie-durand/",
                "subject_hint": "Connection request",
                "message": "Bonjour Marie, …",
            }
        ],
    }
    errors = _run(tmp_path, data, tailor_schemas_dir / "linkedin.schema.json")
    assert errors == []


def test_linkedin_schema_rejects_unknown_outreach_type(tmp_path, tailor_schemas_dir):
    data = {
        "outreach_type": "speculative_v2",  # not in the enum
        "variants": [{"target": "hiring_manager", "message": "Hi."}],
    }
    errors = _run(tmp_path, data, tailor_schemas_dir / "linkedin.schema.json")
    assert any("outreach_type" in e for e in errors), errors
