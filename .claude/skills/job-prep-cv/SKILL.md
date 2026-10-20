---
name: job-prep-cv
description: Internal sub-skill — prepares the CV fact base, customization layer, and output folder for an application run. Invoked by the job-application-tailor and job-cold-prospect orchestrators only. Not user-facing.
disable-model-invocation: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Skill: job-prep-cv

## Role

The shared first steps of every application-pack run. `job-application-tailor` (offer flow) and `job-cold-prospect` (cold flow) read this file, follow it, then continue with their own Step 3.

## Inputs the caller sets

- **`$FLOW`** — `offer` or `cold`. Controls the output folder prefix.
- **`$INPUT_SEED`** — the user's input (job text/URL, or company name/URL). Seeds a placeholder folder slug, which each flow renames once it knows the real title/company.
- **`$EARLY_BLACKLIST_NAME`** *(optional)* — a company name already known now. When set, the blacklist is checked before the folder is created.

## Step 0 — Preflight (one command)

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE_TAILOR="$PROJECT_ROOT/.claude/skills/job-application-tailor"   # dev/repo layout
if [ ! -d "$SKILL_BASE_TAILOR" ] && [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_BASE_TAILOR="$CLAUDE_PLUGIN_ROOT/skills/job-application-tailor"   # installed plugin
fi
cd "$SKILL_BASE_TAILOR" && python -m scripts.preflight \
  --flow "<offer|cold>" \
  --input "<INPUT_SEED>" \
  ${EARLY_BLACKLIST_NAME:+--early-blacklist-name "$EARLY_BLACKLIST_NAME"}
```

If neither directory exists, stop: the job-application-tailor skill is not installed correctly. Preflight checks dependencies, resolves the user data dir, initialises the history DB, loads the customization layer, creates the output folder and `_prep/`, and — when the cache is valid — copies and verifies the cached fact base. It prints one JSON object:

| Field | Use |
|---|---|
| `status` | `ok` · `cache_stale` · `first_run` · `blacklisted` · `error` |
| `project_root`, `skill_base_tailor` | Assign to `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR` (prefer these over the guesses above — they are correct in any layout) |
| `master_cv_path` | Assign to `$MASTER_CV` — never assume `resources/MASTER_CV.docx` |
| `customization` | `{"addendum": {...}, "prefs": {...}}` — assign to `$CUSTOMIZATION` |
| `output_dir`, `prep_dir` | Assign to `$OUTPUT_DIR`, `$PREP_DIR` (already created) |
| `next_steps`, `blacklist_hit`, `message`, `fact_base_verify_message` | Shown per status below |

- **`ok`** — cache hit, fact base already in `$PREP_DIR` and verified. Show any warnings in `fact_base_verify_message` (non-blocking), skip Steps 1–2.5 and hand back.
- **`cache_stale`** — the master CV changed (or there is no cache). Do Steps 1–2.5.
- **`first_run`** — there was no `MASTER_CV.docx`; preflight seeded the user data dir with templates and an example CV. Show `next_steps` verbatim and stop. Never generate a pack from the example CV.
- **`blacklisted`** — show `blacklist_hit` and stop unless the user explicitly overrides.
- **`error`** — show `message` and stop. If it reports a missing dependency, tell the user to run `pip install -r "$SKILL_BASE_TAILOR/requirements.txt"`.

## Step 1 — Read the master CV (`cache_stale` only)

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py read-cv --cv "$MASTER_CV"
```

## Step 2 — Extract the fact base (`cache_stale` only)

Follow `$SKILL_BASE_TAILOR/prompts/extract_cv_data.md` and write `$PREP_DIR/cv_fact_base.json`. Re-extract from the current CV — never reuse the previous fact base and re-bless it.

## Step 2.5 — Verify, then cache (`cache_stale` only; never skip)

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py gate factbase "$OUTPUT_DIR" --cv "$MASTER_CV"
```

The gate validates the schema and compares the fact base with the raw CV. It exists because the model can contaminate the fact base with keywords from later context (the job offer, the company research). That is also why this step must finish **before** any offer text or company research enters the conversation.

- **`[technologies]` / `[methodologies]` failure** — the item was fabricated; remove it.
- **`[metric]` failure** — a figure drifted from the CV (e.g. fact base "40+", CV "100+"). Re-extract the figure from the current CV; never just delete the number.
- **Skill warnings** are non-blocking — often valid abstractions of role descriptions; review them.

Re-run until it passes, then save the cache (shared by both flows, so the next run returns `ok`):

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py save-cv-cache "$OUTPUT_DIR"
```

`save-cv-cache` re-runs the consistency check and refuses to write `.cv_hash` while the fact base disagrees with the CV. Never refresh `.cv_hash` by hand.

## Hand back

`$PROJECT_ROOT`, `$SKILL_BASE_TAILOR`, `$MASTER_CV`, `$OUTPUT_DIR`, `$PREP_DIR` and `$CUSTOMIZATION` are set and `$PREP_DIR/cv_fact_base.json` is verified. Return to the caller's Step 3.
