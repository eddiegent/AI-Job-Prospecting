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

## One consolidated invocation

The shared infrastructure (`scripts/`, `schemas/`, `config/`, `references/commands.md`) lives in the `job-application-tailor` skill. The new `scripts/preflight.py` collapses what used to be four to five separate one-liners — deps check, master CV check, DB init, customization load, output folder creation — plus the cache-hot path of Steps 1/2/2.5 (read CV, copy cached fact base, verify) into a single Python invocation that prints a JSON state blob.

```bash
SKILL_BASE_TAILOR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)/.claude/skills/job-application-tailor"
cd "$SKILL_BASE_TAILOR" && python -m scripts.preflight \
  --flow "<offer|cold>" \
  --input "<INPUT_SEED>" \
  ${EARLY_BLACKLIST_NAME:+--early-blacklist-name "$EARLY_BLACKLIST_NAME"}
```

Parse the printed JSON. Top-level fields:

| Field | Meaning |
|---|---|
| `status` | `ok` · `cache_stale` · `first_run` · `blacklisted` · `error` |
| `project_root` | Resolved git toplevel (or skill-base parent fallback) |
| `skill_base_tailor` | The tailor skill's path — assign to `$SKILL_BASE_TAILOR` |
| `master_cv_path`, `user_data_dir` | Resolved CV / data dir |
| `db_path`, `db_count` | History DB path and current row count |
| `customization` | `{"addendum": {...}, "prefs": {...}}` — assign to `$CUSTOMIZATION` |
| `output_dir`, `prep_dir` | Output folder and `_prep/` (already created) |
| `fact_base_path`, `fact_base_verified`, `fact_base_verify_message` | Present when cache hit |

### Status handling

- **`ok`** — fact base cache hit, fully verified. Skip Steps 1, 2, 2.5; jump straight to the orchestrator's Step 3. The fact base file is already in `$PREP_DIR`.
- **`cache_stale`** — output folder is ready, customization is loaded, but the fact base needs LLM extraction. Continue to Steps 1–2.5 below; the verification step is still mandatory.
- **`first_run`** — `MASTER_CV.docx` was missing; `init.py` ran and seeded the user data dir with templates and the example CV. Surface the `next_steps` field to the user verbatim and stop. Do **not** generate a pack from the example CV.
- **`blacklisted`** — `$EARLY_BLACKLIST_NAME` matched the blacklist. Surface the `blacklist_hit` payload and stop unless the user explicitly overrides.
- **`error`** — surface the `message` field and stop.

### What the script does (for reference)

- Verifies `docx`, `yaml`, `jsonschema` import. Exits 1 with a clean error message if a dep is missing.
- Resolves the user data dir via `scripts/paths.py::resolve_user_data_dir` (honours `JOB_TAILOR_HOME`, legacy `resources/` layout, or the OS-standard app data dir).
- If the master CV is missing, runs `scripts.init` (which copies `MASTER_CV.example.docx`, `cv_addendum.template.md`, `user_prefs.template.yaml` into the user data dir without ever overwriting an existing `MASTER_CV.docx`, `cv_addendum.md`, or `user_prefs.yaml`) and returns `status: first_run`.
- Initialises `resources/job_history.db` (creates if missing). Reports `db_count` for telemetry; backfill is a separate concern handled by Phase F migrations on the v1→v2 path.
- Loads customization via `scripts/user_customization.py::load_customization_context`. Returns the typed-empty defaults when the user files are absent.
- Creates the output folder. The slug is **a placeholder** in both flows: the offer flow rebuilds it from `job_title` + `company_name` in Step 4 once the offer is analysed; the cold flow rebuilds it from `company_profile.company_name` in Step 3 once research has resolved the canonical name. The `cold-` prefix is preserved by the rename — only the trailing slug changes.
- For the cache-hot path: copies the cached fact base into `$PREP_DIR` and runs `scripts/verify_fact_base.py` against it (forcing UTF-8 in the child process so non-ASCII output doesn't crash the subprocess decode on Windows). Returns the script's stdout in `fact_base_verify_message` so warnings are still visible.

## Step 1 — Read the master CV (only when `cache_stale`)

Skip when `status == "ok"`. Otherwise, extract text from the DOCX. See `$SKILL_BASE_TAILOR/references/commands.md` § CV Caching for the read command.

## Step 2 — Extract CV fact base (only when `cache_stale`)

Skip when `status == "ok"`. Read `$SKILL_BASE_TAILOR/prompts/extract_cv_data.md`, generate the fact base, validate against `$SKILL_BASE_TAILOR/schemas/cv_fact_base.schema.json`, then save the cache for future runs. See `$SKILL_BASE_TAILOR/references/commands.md` § CV Caching.

The fact base cache is shared across both flows — once you save it here, the next run on the same `MASTER_CV.docx` returns `status: ok` from preflight directly.

## Step 2.5 — Verify fact base against raw CV (only when `cache_stale`)

Skip when `status == "ok"` (preflight already verified). When `cache_stale`, **this step is mandatory and must not be skipped.** It exists because the LLM can unconsciously contaminate the fact base with keywords from later context (job offer for the offer flow, company research for the cold flow), especially when both are processed in the same context window.

Run `scripts/verify_fact_base.py` with the master CV and the fact base. See `$SKILL_BASE_TAILOR/references/commands.md` § Verify Fact Base Against Raw CV.

- **If verification fails** (exit code 1): technologies or methodologies were fabricated. Remove the flagged items from `cv_fact_base.json`, re-run verification, and only proceed once it passes. If the cache was just saved, re-save it after fixing.
- **Warnings** about skills are non-blocking — review them but they are often valid abstractions of role descriptions.

This step must complete **before** any external context (job offer or company research) enters the window, so the fact base is locked before keywords from those sources can contaminate it.

## Hand back to the orchestrator

At this point: `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR`, `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION` are all set, and `$PREP_DIR/cv_fact_base.json` is verified. Return control to the orchestrator (`job-application-tailor` continues at Step 3, `job-cold-prospect` continues at Step 3).
