"""Shared test configuration for job-application-tailor.

Adds the skill root to sys.path so `scripts.*` imports resolve the same way
they do when the skill runs in production (where the CWD is the skill base).
Fixtures for fact bases, match analyses, and tailored CVs live as JSON
files under ``tests/fixtures/`` and are loaded by the ``load_fixture``
helper here so tests don't repeat the Path boilerplate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def sample_fact_base() -> dict[str, Any]:
    return load_fixture("sample_fact_base.json")


@pytest.fixture
def sample_match_analysis() -> dict[str, Any]:
    return load_fixture("sample_match_analysis.json")
