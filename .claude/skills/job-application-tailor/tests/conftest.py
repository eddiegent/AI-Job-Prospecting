"""Shared test configuration for job-application-tailor.

Adds the skill root to sys.path so `scripts.*` imports resolve the same way
they do when the skill runs in production (where the CWD is the skill base).
Real fixtures (sample CV, fact base, match analysis) will be added in a later
Phase T commit alongside the regression tests that consume them.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent

if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))
