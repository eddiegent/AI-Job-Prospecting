"""Shared test configuration for job-cold-prospect.

The cold-prospect skill imports scripts and shared schemas from the sibling
``job-application-tailor`` skill. These tests mirror that layout: the tailor
skill root is added to sys.path so ``from scripts.validate import validate``
resolves the same way it does when the skill runs in production.

The cold-prospect skill's own schemas live alongside this file — both
schema roots are surfaced as fixtures so individual tests don't need to
recompute paths.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

COLD_ROOT = Path(__file__).resolve().parent.parent
TAILOR_ROOT = COLD_ROOT.parent / "job-application-tailor"

if str(TAILOR_ROOT) not in sys.path:
    sys.path.insert(0, str(TAILOR_ROOT))


@pytest.fixture(scope="session")
def cold_schemas_dir() -> Path:
    return COLD_ROOT / "schemas"


@pytest.fixture(scope="session")
def tailor_schemas_dir() -> Path:
    return TAILOR_ROOT / "schemas"
