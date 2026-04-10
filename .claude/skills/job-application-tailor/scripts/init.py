"""First-run onboarding for job-application-tailor (Phase 4).

Seeds a fresh user data directory with the sample CV, the addendum
template, and the user-prefs template, so a brand-new user can go from
``install`` to ``generate an application pack`` in a few minutes.

The CLI entry point is intentionally tiny — all real work happens in
:func:`init_user_data`, which takes the target dir and samples dir as
arguments so tests can drive it with synthetic inputs.

Invariants (pinned by tests/test_init.py):

1. Never overwrite an existing file in the target. In particular: never
   create or touch ``MASTER_CV.docx`` — only the user does that.
2. Copy the fictional CV as ``MASTER_CV.example.docx`` so there is no
   way to accidentally ship the sample as the real thing.
3. Idempotent: a second run is a no-op.
4. Always create ``output/`` alongside the data files.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from scripts.paths import SKILL_ROOT, resolve_user_data_dir


SAMPLE_CV_NAME = "MASTER_CV.example.docx"
ADDENDUM_TEMPLATE = "cv_addendum.template.md"
PREFS_TEMPLATE = "user_prefs.template.yaml"

_SEEDED_FILES = (SAMPLE_CV_NAME, ADDENDUM_TEMPLATE, PREFS_TEMPLATE)


def init_user_data(
    *,
    user_data_dir: Path | None = None,
    samples_dir: Path | None = None,
) -> dict[str, Any]:
    """Seed ``user_data_dir`` with the sample CV and templates.

    Returns a report dict ``{"user_data_dir": str, "created": [...],
    "skipped": [...]}``. ``created`` lists absolute paths that were newly
    written, ``skipped`` lists absolute paths that already existed and
    were left untouched. Production callers pass nothing and the function
    resolves both paths from ``SKILL_ROOT``.
    """
    if user_data_dir is None:
        user_data_dir = resolve_user_data_dir()
    if samples_dir is None:
        samples_dir = SKILL_ROOT / "samples"

    user_data_dir = Path(user_data_dir)
    samples_dir = Path(samples_dir)

    user_data_dir.mkdir(parents=True, exist_ok=True)
    (user_data_dir / "output").mkdir(parents=True, exist_ok=True)

    created: list[str] = []
    skipped: list[str] = []

    for name in _SEEDED_FILES:
        source = samples_dir / name
        target = user_data_dir / name
        if target.exists():
            skipped.append(str(target))
            continue
        if not source.exists():
            # Missing source in a test fixture that only seeded a subset
            # is legal; production always has all three.
            continue
        shutil.copy2(source, target)
        created.append(str(target))

    return {
        "user_data_dir": str(user_data_dir),
        "created": created,
        "skipped": skipped,
    }


def _format_report(report: dict[str, Any]) -> str:
    lines = [f"job-application-tailor — user data dir: {report['user_data_dir']}"]
    if report["created"]:
        lines.append("")
        lines.append("Created:")
        for path in report["created"]:
            lines.append(f"  + {path}")
    if report["skipped"]:
        lines.append("")
        lines.append("Already present (left untouched):")
        for path in report["skipped"]:
            lines.append(f"  = {path}")

    target = Path(report["user_data_dir"])
    real_cv = target / "MASTER_CV.docx"
    lines.append("")
    if real_cv.exists():
        lines.append("Your master CV is in place. You can run the skill on a job offer.")
    else:
        lines.append("Next steps:")
        lines.append(
            f"  1. Open {target / SAMPLE_CV_NAME} in Word or LibreOffice to see the"
        )
        lines.append("     structure the extractor expects (section headers, skills")
        lines.append("     table, dates). Use it as a reference for your own CV.")
        lines.append(
            f"  2. Save your real CV as {real_cv} (same filename, any content)."
        )
        lines.append(
            "  3. (Optional) Rename cv_addendum.template.md to cv_addendum.md"
        )
        lines.append("     and user_prefs.template.yaml to user_prefs.yaml, then")
        lines.append("     edit the parts you care about.")
        lines.append("  4. Re-run the skill on a job offer.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    report = init_user_data()
    print(_format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
