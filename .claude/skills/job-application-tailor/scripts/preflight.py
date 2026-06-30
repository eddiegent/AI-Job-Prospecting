"""Consolidated preflight for the job-prep-cv sub-skill.

Replaces five separate one-liners (deps check, master CV check, DB
init/count, customization load, output folder creation) and the
cache-hot path of Steps 1/2/2.5 (read CV, copy cached fact base, verify
fact base) with a single Python invocation that prints a JSON state blob
the orchestrator consumes.

Usage:
    python -m scripts.preflight --flow {offer,cold} --input "<seed>"
                                [--early-blacklist-name "<name>"]

Exit codes:
    0 — preflight succeeded; the JSON ``status`` field tells the
        orchestrator what to do next:
          * ``ok``           — fact base cache hit, fully verified, ready
                               for Step 3.
          * ``cache_stale``  — folder is created and customization is
                               loaded, but the orchestrator must extract
                               and verify the fact base via the LLM
                               (Steps 1/2/2.5 in the prompt).
          * ``first_run``    — MASTER_CV is missing; ``init.py`` was run
                               and the user must save their CV. The
                               orchestrator surfaces ``next_steps`` and
                               stops.
          * ``blacklisted``  — ``--early-blacklist-name`` matched the
                               blacklist. The orchestrator stops unless
                               the user explicitly overrides.
    1 — fatal error (deps missing, IO failure, bad args).

The JSON shape is intentionally flat — each downstream step reads the
keys it needs without any post-processing.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import traceback
from pathlib import Path

# Allow importing siblings when run directly (python scripts/preflight.py)
# as well as via module path (python -m scripts.preflight) — same pattern
# as scripts/init.py.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (
    auto_slug,
    copy_cached_cv_fact_base,
    current_date_ddmmyyyy,
    cv_cache_is_valid,
    ensure_dir,
    slug_for_filename,
)
from job_history_db import JobHistoryDB
from paths import resolve_user_data_dir
from user_customization import load_customization_context

SKILL_BASE = Path(__file__).resolve().parent.parent


def _resolve_project_root() -> Path:
    """Return the user's project root.

    The orchestrator may invoke this from the skill base after a ``cd``,
    so ``Path.cwd()`` would point inside the skill rather than at the
    project. Prefer ``git rev-parse --show-toplevel`` when available, fall
    back to walking up from the skill base looking for ``resources/`` or
    ``.git/``, and finally fall back to ``Path.cwd()``.
    """
    import os
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        if result.returncode == 0:
            top = result.stdout.strip()
            if top:
                return Path(top)
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Walk up from the skill base looking for a project marker. We use
    # ``.git`` and ``.claude`` rather than the legacy ``resources/`` dir
    # so the user-data path stays funnelled through resolve_user_data_dir.
    for parent in SKILL_BASE.parents:
        if (parent / ".git").exists() or (parent / ".claude").exists():
            return parent

    return Path.cwd()


def _check_dependencies() -> None:
    """Raise ImportError if a required Python package is missing."""
    import docx  # noqa: F401
    import jsonschema  # noqa: F401
    import yaml  # noqa: F401


def _build_initial_folder(project_root: Path, flow: str, input_seed: str) -> Path:
    """Compute the initial output folder. Slug is a placeholder for the
    offer flow (Step 4 will rebuild it from the analysed offer); for the
    cold flow it stays as the canonical ``cold-`` prefix."""
    date = current_date_ddmmyyyy()
    slug = slug_for_filename(input_seed) or "untitled"
    prefix = "cold-" if flow == "cold" else ""
    return project_root / "output" / f"{prefix}{date}-{slug}"


def _verify_fact_base_cached(cv_path: Path, fact_base_path: Path) -> tuple[bool, str]:
    """Run verify_fact_base.py against the cached fact base. Returns
    (ok, message). ``ok=True`` means the orchestrator can proceed
    directly to Step 3; ``ok=False`` means the fact base needs
    re-extraction (orchestrator falls back to the LLM Step 2 path).

    ``PYTHONIOENCODING=utf-8`` forces the child to emit UTF-8 regardless
    of the Windows console codepage — verify_fact_base.py doesn't wrap
    its own stdout, so without this the subprocess decode crashes on any
    non-ASCII byte the script prints (e.g. UTF-8 quote chars in skill
    names).
    """
    import os
    import subprocess

    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL_BASE / "scripts" / "verify_fact_base.py"),
            str(cv_path),
            str(fact_base_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    message = ((result.stdout or "") + (result.stderr or "")).strip()
    return result.returncode == 0, message


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="preflight")
    parser.add_argument("--flow", required=True, choices=["offer", "cold"])
    parser.add_argument("--input", required=True, help="Input seed string (URL / company / pasted offer)")
    parser.add_argument(
        "--early-blacklist-name",
        default=None,
        help="If set, check the blacklist on this name before creating the folder (cold flow uses this).",
    )
    args = parser.parse_args(argv)

    state: dict[str, object] = {"status": "ok", "flow": args.flow}

    try:
        _check_dependencies()
    except ImportError as exc:
        print(json.dumps({"status": "error", "message": f"Missing dependency: {exc}"}, ensure_ascii=False))
        return 1

    project_root = _resolve_project_root()
    state["project_root"] = str(project_root)
    state["skill_base_tailor"] = str(SKILL_BASE)

    # --- Master CV check (with init fallback) ---
    user_data_dir = resolve_user_data_dir()
    master_cv = user_data_dir / "MASTER_CV.docx"
    state["master_cv_path"] = str(master_cv)
    state["user_data_dir"] = str(user_data_dir)

    if not master_cv.exists():
        # First-run onboarding: run init.py and tell the orchestrator to stop.
        from init import init_user_data

        try:
            init_user_data()
        except Exception as exc:
            print(json.dumps({"status": "error", "message": f"init failed: {exc}"}, ensure_ascii=False))
            return 1
        state["status"] = "first_run"
        state["next_steps"] = (
            f"Save your real CV as {master_cv}. Optionally edit "
            f"{user_data_dir / 'cv_addendum.md'} and {user_data_dir / 'user_prefs.yaml'}, "
            "then re-run the skill."
        )
        print(json.dumps(state, ensure_ascii=False))
        return 0

    # --- Job history DB init / count ---
    # The DB lives next to the master CV in the user data dir (same dir
    # resolve_user_data_dir() returned above), so it works for both the
    # legacy <project>/resources/ layout and the plugin layout.
    db_path = user_data_dir / "job_history.db"
    state["db_path"] = str(db_path)
    db = JobHistoryDB(str(db_path))
    state["db_count"] = db.total_count()

    # --- Early blacklist check (cold flow uses this on the user's input name) ---
    if args.early_blacklist_name:
        hit = db.check_company_list(args.early_blacklist_name)
        if hit and hit.get("list_type") == "blacklist":
            db.close()
            state["status"] = "blacklisted"
            state["blacklist_hit"] = hit
            print(json.dumps(state, ensure_ascii=False))
            return 0
    db.close()

    # --- Customization layer ---
    # cv_addendum.md and user_prefs.yaml live in the user data dir.
    customization = load_customization_context(str(user_data_dir))
    state["customization"] = customization

    # --- Output folder ---
    output_dir = _build_initial_folder(project_root, args.flow, args.input)
    prep_dir = output_dir / "_prep"
    ensure_dir(prep_dir)
    state["output_dir"] = str(output_dir)
    state["prep_dir"] = str(prep_dir)

    # --- Cache-hot fact base path (collapses Steps 1/2/2.5) ---
    if cv_cache_is_valid(master_cv):
        copy_cached_cv_fact_base(master_cv, prep_dir)
        fact_base_path = prep_dir / "cv_fact_base.json"
        ok, verify_msg = _verify_fact_base_cached(master_cv, fact_base_path)
        # Defense-in-depth: verify_fact_base.py already blocks on metric drift,
        # but run the consistency check in-process too so the cache-stale
        # downgrade does not depend solely on the child's exit code.
        try:
            from factbase_consistency import check as _fb_check

            drift_errs, _ = _fb_check(master_cv, fact_base_path)
        except Exception:
            drift_errs = []
        if drift_errs:
            ok = False
            verify_msg = (verify_msg + "\n" + "\n".join(drift_errs)).strip()
        state["fact_base_path"] = str(fact_base_path)
        state["fact_base_verified"] = ok
        state["fact_base_verify_message"] = verify_msg
        if not ok:
            # Verification flagged contamination or metric drift — orchestrator
            # must re-extract via LLM, same as cache_stale.
            state["status"] = "cache_stale"
    else:
        state["status"] = "cache_stale"

    print(json.dumps(state, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # Wrap stdout once at the entry point so non-ASCII (paths, addendum
    # content with em-dashes / arrows) survive Windows cp1252 default.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        # Uncaught exceptions are surfaced as JSON so the orchestrator can parse.
        print(json.dumps({"status": "error", "message": traceback.format_exc()}, ensure_ascii=False))
        raise SystemExit(1)
