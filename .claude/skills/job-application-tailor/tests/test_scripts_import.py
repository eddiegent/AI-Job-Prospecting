"""Smoke test: every module under scripts/ must import cleanly.

This is the Phase T baseline test. It has no assertions about behavior —
it only catches import-time errors (syntax, missing deps, bad relative
imports, side-effect crashes). If this test fails, nothing else in the
skill can be trusted to run.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"

# Modules we intentionally skip:
# - __pycache__ is not a module
# - create_cv_template is a one-off dev helper that writes to disk on import
#   in some revisions; if it imports cleanly we still want to catch it, so
#   we leave it in. Add names here only if a module has unavoidable import
#   side effects (e.g. argparse.parse_args at top level).
SKIP: set[str] = set()


def _discover_modules() -> list[str]:
    names = []
    for path in sorted(SCRIPTS_DIR.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        if path.stem in SKIP:
            continue
        names.append(f"scripts.{path.stem}")
    return names


@pytest.mark.parametrize("module_name", _discover_modules())
def test_script_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)
