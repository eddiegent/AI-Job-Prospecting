---
name: job-prep-cv
description: Internal sub-skill — prepares the CV fact base, customization layer, and output folder for an application run. Invoked by the job-application-tailor and job-cold-prospect orchestrators only. Not user-facing.
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Skill: job-prep-cv

## Role

Shared preamble for any application-pack run. Both `job-application-tailor` (offer flow) and `job-cold-prospect` (cold flow) invoke this skill before their divergent middle steps. It owns:

- Pre-flight (config, dependencies, master CV check, init, history DB init, customization load)
- Output folder + `_prep/` creation (flow-aware naming)
- Master CV read
- Fact base extract + cache
- Fact base verification

After it completes, the orchestrator continues with its own flow-specific steps (offer analysis vs company research, etc.).

## Inputs the caller must provide

The orchestrator sets these before reading this skill's body:

- **`$FLOW`** — `offer` or `cold`. Controls output folder prefix.
- **`$INPUT_SEED`** — the user-supplied input string (job text/URL for offer flow, company name/URL for cold flow). Used to generate the initial folder slug.
- **`$EARLY_BLACKLIST_NAME`** *(optional)* — a company name already known at this point (e.g. parsed from the URL). When set, this sub-skill checks the blacklist before creating the folder. If unset, the orchestrator handles the blacklist check later, once the canonical name is known.

## Outputs this skill leaves set

- **`$OUTPUT_DIR`** — absolute path to the run's output folder
- **`$PREP_DIR`** — `$OUTPUT_DIR/_prep`
- **`$CUSTOMIZATION`** — dict from `load_customization_context()` with `addendum` and `prefs` keys
- **`$PROJECT_ROOT`**, **`$SKILL_BASE_TAILOR`** — resolved infrastructure paths

The fact base lives at `$PREP_DIR/cv_fact_base.json` and has been verified against the raw master CV. The cache at `resources/cv_fact_base.json` is up to date.

## Resolve paths

The shared infrastructure (scripts/, schemas/, config/, references/commands.md) lives in the `job-application-tailor` skill. Both flows import from it.

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE_TAILOR="$PROJECT_ROOT/.claude/skills/job-application-tailor"
```

## Step 0 — Pre-flight

Verify dependencies and read config (`config/settings.default.yaml` merged with the optional user override at `<user-data-dir>/settings.yaml`, plus `config/naming_rules.yaml`).

**Check for master CV** — if `<user-data-dir>/MASTER_CV.docx` does not exist, trigger first-run onboarding instead of stopping cold:

```bash
cd "$SKILL_BASE_TAILOR" && python -m scripts.init
```

`scripts/init.py` resolves the user data dir (via `scripts/paths.py::resolve_user_data_dir`, which honours `JOB_TAILOR_HOME`, the legacy `resources/` layout, or the OS-standard app data dir), creates the directory and its `output/` subfolder, and copies three files from `samples/`:

- `MASTER_CV.example.docx` — a fictional neutral CV the user can open in Word to see the section headers, skills-table structure, and date formats the extractor expects.
- `cv_addendum.template.md` — a commented template for the per-run enrichment layer (Phase 1).
- `user_prefs.template.yaml` — a commented template with every available preference key.

Init is idempotent and **never** overwrites an existing `MASTER_CV.docx`, `cv_addendum.md`, or `user_prefs.yaml`. After running it, surface the printed "Next steps" to the user and stop until they save their real CV as `<user-data-dir>/MASTER_CV.docx`. Do not attempt to generate an application pack from the example CV — it is a reference, not a substitute.

**Initialise the job history database** — ensure `resources/job_history.db` exists. Only run the backfill script if the database is empty AND the `output/` folder exists and contains subdirectories with `_prep/job_offer_analysis.json` files. For a fresh install with no prior output, skip backfill entirely. See `$SKILL_BASE_TAILOR/references/commands.md` § Job History Database.

**Early blacklist check (optional).** If `$EARLY_BLACKLIST_NAME` is set, check the blacklist before creating the output folder. If blacklisted, stop unless the user explicitly overrides. See `$SKILL_BASE_TAILOR/references/commands.md` § Company Lists. The cold flow uses this to catch obvious hits on the user's input string before research; the offer flow leaves `$EARLY_BLACKLIST_NAME` unset and lets Step 3.5 (`check-duplicate`) handle the blacklist as part of its bundled check.

**Load user customization layer** — read the optional user-owned files `resources/cv_addendum.md` and `resources/user_prefs.yaml`:

```python
from scripts.user_customization import load_customization_context
ctx = load_customization_context("resources")  # -> {"addendum": {...}, "prefs": {...}}
```

Both files are optional; missing files return typed empty defaults. Store the returned dict as `$CUSTOMIZATION` for later steps. This is the canonical place for:

- **Addendum** — additional experience bullets, hidden skills, off-CV facts. Merged into the in-memory fact base by `merge_addendum_into_fact_base()` at the orchestrator's CV-tailoring step. The addendum is a per-run in-memory layer only — it never mutates `resources/cv_fact_base.json`.
- **User prefs** — `preferred_title_labels`, `forbidden_title_labels`, `tone_directives`, `team_context_companies`, `default_language`. Passed into CV tailoring, the motivation letter, and LinkedIn messages by the orchestrator.

## Step 0d — Create the output folder

Folder naming is flow-aware:

| `$FLOW` | Initial folder name | Notes |
|---|---|---|
| `offer` | `output/[date]-[slug]/` | The offer orchestrator renames it after match analysis to `[fit_level]-[date]-[slug]/`. |
| `cold` | `output/cold-[date]-[slug]/` | The `cold-` prefix segments cold packs visually. The cold orchestrator may rename the slug once the canonical company name is resolved during research. |

```bash
cd "$SKILL_BASE_TAILOR" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.common import slug_for_filename, ensure_dir, current_date_ddmmyyyy
from pathlib import Path
date = current_date_ddmmyyyy()
slug = slug_for_filename('<INPUT_SEED-replaced-by-orchestrator>')
flow = '<offer-or-cold>'
prefix = 'cold-' if flow == 'cold' else ''
folder = Path('$PROJECT_ROOT/output') / f'{prefix}{date}-{slug}'
ensure_dir(folder / '_prep')
print(folder)
"
```

Capture the printed path as `$OUTPUT_DIR`, and set `$PREP_DIR="$OUTPUT_DIR/_prep"`.

## Step 1 — Read the master CV

Extract text from the DOCX. See `$SKILL_BASE_TAILOR/references/commands.md` § CV Caching for the read command.

## Step 2 — Extract CV fact base (cached)

Check the cache first. If valid, copy `cv_fact_base.json` into `$PREP_DIR` and skip ahead. If stale, read `$SKILL_BASE_TAILOR/prompts/extract_cv_data.md`, generate the fact base, validate against `$SKILL_BASE_TAILOR/schemas/cv_fact_base.schema.json`, then save the cache for future runs. See `$SKILL_BASE_TAILOR/references/commands.md` § CV Caching.

The fact base cache is shared across both flows — if the master CV has not changed, the cached extraction is reused regardless of which flow ran last.

## Step 2.5 — Verify fact base against raw CV

**This step is mandatory and must not be skipped.** It exists because the LLM can unconsciously contaminate the fact base with keywords from later context (job offer for the offer flow, company research for the cold flow), especially when both are processed in the same context window.

Run `scripts/verify_fact_base.py` with the master CV and the fact base. See `$SKILL_BASE_TAILOR/references/commands.md` § Verify Fact Base Against Raw CV.

- **If verification fails** (exit code 1): technologies or methodologies were fabricated. Remove the flagged items from `cv_fact_base.json`, re-run verification, and only proceed once it passes. If the cache was just saved, re-save it after fixing.
- **Warnings** about skills are non-blocking — review them but they are often valid abstractions of role descriptions.

This step must complete **before** any external context (job offer or company research) enters the window, so the fact base is locked before keywords from those sources can contaminate it.

## Hand back to the orchestrator

At this point: `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR`, `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION` are all set, and `$PREP_DIR/cv_fact_base.json` is verified. Return control to the orchestrator (`job-application-tailor` continues at Step 3, `job-cold-prospect` continues at Step 3).
