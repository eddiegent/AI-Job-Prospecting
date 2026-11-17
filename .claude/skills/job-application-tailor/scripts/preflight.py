"""Consolidated preflight for the job-prep-cv sub-skill.

Replaces five separate one-liners (deps check, master CV check, DB
init/count, customization load, output folder creation) and the
cache-hot path of Steps 1/2/2.5 (read CV, copy cached fact base, verify
fact base) with a single Python invocation that prints a JSON state blob
the orchestrator consumes.

Usage:
    python -m scripts.preflight --flow {offer,cold} --input "<seed>"
                                [--early-blacklist-name "<name>"]
    python -m scripts.preflight --flow {offer,cold} --reuse-dir "<pack>"

``--reuse-dir`` reruns an existing pack in place: no new folder, same JSON,
``output_dir``/``prep_dir`` pointing at the pack. The fact-base rules are
unchanged — a valid cache is copied over ``_prep/cv_fact_base.json`` and
verified; a stale cache still returns ``cache_stale`` (re-extract), and the
pack's old fact base is renamed to ``cv_fact_base.prev.json`` so it can't be
mistaken for a current one.

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

if __package__ in (None, ""):  # direct run: make `scripts.*` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.common import (  # noqa: E402
    auto_slug,
    copy_cached_cv_fact_base,
    current_date_ddmmyyyy,
    cv_cache_is_valid,
    ensure_dir,
    force_utf8_stdio,
    slug_for_filename,
)
from scripts.job_history_db import JobHistoryDB  # noqa: E402
from scripts.paths import (  # noqa: E402
    git_toplevel,
    resolve_project_root,
    resolve_user_data_dir,
)
from scripts.user_customization import load_customization_context  # noqa: E402

SKILL_BASE = Path(__file__).resolve().parent.parent


def _git_toplevel() -> Path | None:
    """Return `git rev-parse --show-toplevel` for the cwd, or None.

    Kept as a module-level seam so tests can stub git out."""
    return git_toplevel()


def _resolve_project_root(
    skill_base: Path | None = None, home: Path | None = None
) -> Path:
    """Return the directory the run's ``output/`` folder lives under.

    Thin wrapper over :func:`scripts.paths.resolve_project_root` (the rules
    live there, shared with the history CLI's folder lookup)."""
    return resolve_project_root(
        skill_base=skill_base or SKILL_BASE,
        home=home,
        toplevel=_git_toplevel(),
        use_git=False,
    )


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


def _reuse_dir_problem(folder: Path, flow: str) -> str | None:
    """Why ``folder`` can't be rerun in place under ``flow``, or None.

    A rerun reuses the pack's ``_prep/`` inputs (raw offer, research), so a
    folder without one isn't a pack. The ``cold-`` prefix is how every later
    command tells the flows apart, so a mismatch would build the wrong pack.
    """
    if not folder.is_dir():
        return f"--reuse-dir: folder does not exist: {folder}"
    if not (folder / "_prep").is_dir():
        return f"--reuse-dir: no _prep/ under {folder} — not an application pack"
    is_cold = folder.name.startswith("cold-")
    if is_cold != (flow == "cold"):
        kind = "a cold pack" if is_cold else "an offer pack"
        return f"--reuse-dir: {folder.name} is {kind}; rerun it with --flow {'cold' if is_cold else 'offer'}"
    return None


def _set_aside_previous_fact_base(prep_dir: Path) -> Path | None:
    """Rename a reused pack's old ``cv_fact_base.json`` to ``.prev.json``.

    Called only when the cache is stale (the master CV changed since that run):
    the old file was extracted from a CV that no longer exists, and leaving it
    in place under its usual name invites exactly the reuse-and-re-bless
    shortcut CLAUDE.md forbids. Renamed rather than deleted so nothing is lost.
    """
    old = prep_dir / "cv_fact_base.json"
    if not old.exists():
        return None
    dst = prep_dir / "cv_fact_base.prev.json"
    old.replace(dst)
    return dst


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
    parser.add_argument("--input", default=None, help="Input seed string (URL / company / pasted offer)")
    parser.add_argument(
        "--early-blacklist-name",
        default=None,
        help="If set, check the blacklist on this name before creating the folder (cold flow uses this).",
    )
    parser.add_argument(
        "--reuse-dir",
        default=None,
        help="Rerun an existing pack in place: prepare this folder (which must hold _prep/) "
        "instead of creating a new one. Replaces --input.",
    )
    args = parser.parse_args(argv)
    if not args.input and not args.reuse_dir:
        parser.error("one of --input or --reuse-dir is required")

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
        from scripts.init import init_user_data

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
    if args.reuse_dir:
        output_dir = Path(args.reuse_dir)
        problem = _reuse_dir_problem(output_dir, args.flow)
        if problem:
            print(json.dumps({"status": "error", "message": problem}, ensure_ascii=False))
            return 1
        state["reused"] = True
    else:
        output_dir = _build_initial_folder(project_root, args.flow, args.input)
    prep_dir = output_dir / "_prep"
    ensure_dir(prep_dir)
    state["output_dir"] = str(output_dir)
    state["prep_dir"] = str(prep_dir)

    cache_valid = cv_cache_is_valid(master_cv)
    if args.reuse_dir and not cache_valid:
        previous = _set_aside_previous_fact_base(prep_dir)
        if previous:
            state["previous_fact_base"] = str(previous)

    # --- Cache-hot fact base path (collapses Steps 1/2/2.5) ---
    if cache_valid:
        copy_cached_cv_fact_base(master_cv, prep_dir)
        fact_base_path = prep_dir / "cv_fact_base.json"
        ok, verify_msg = _verify_fact_base_cached(master_cv, fact_base_path)
        # Defense-in-depth: verify_fact_base.py already blocks on metric drift,
        # but run the consistency check in-process too so the cache-stale
        # downgrade does not depend solely on the child's exit code.
        try:
            from scripts.factbase_consistency import check as _fb_check

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
    force_utf8_stdio()
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SystemExit:
        raise
    except Exception:
        # Uncaught exceptions are surfaced as JSON so the orchestrator can parse.
        print(json.dumps({"status": "error", "message": traceback.format_exc()}, ensure_ascii=False))
        raise SystemExit(1)
