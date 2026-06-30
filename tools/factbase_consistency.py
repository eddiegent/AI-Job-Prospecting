"""Standalone entry point for the fact-base consistency guardrail.

The real implementation is the skill's canonical copy at
``.claude/skills/job-application-tailor/scripts/factbase_consistency.py``. This
file is a thin shim that re-exports it so the logic lives in exactly one place
(no two copies that can silently drift). The CLI, the pre-commit hook, and
CLAUDE.md all keep calling ``python tools/factbase_consistency.py …`` unchanged:

    python tools/factbase_consistency.py resources/MASTER_CV.docx resources/cv_fact_base.json --check-hash
"""
from __future__ import annotations

import sys
from pathlib import Path

_SKILL_SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "job-application-tailor" / "scripts"
)
if str(_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SKILL_SCRIPTS))

# Re-export the public API so `from tools.factbase_consistency import check`
# (and find_metric_drift, etc.) still resolves to the canonical implementation.
from factbase_consistency import (  # noqa: E402,F401
    check,
    extract_cv_text,
    file_sha256,
    find_metric_drift,
    main,
)


if __name__ == "__main__":
    main()
