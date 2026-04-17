---
name: job-application-tailor
description: Generate a complete, tailored application pack (CV, motivation letter, short letter, LinkedIn messages, interview prep with fit score) from a job offer and a master CV. Triggers whenever the user provides a job offer URL, pastes a job description, asks to apply for a position, wants to check their fit for a role, or requests any combination of tailored CV, cover letter, or application materials. Also triggers for "prepare my application", "help me apply", "write a cover letter", "match my CV to this offer", "tailor my CV", "how well do I fit this job", "prepare my candidature", or any request in French or English involving a specific job posting and the user's CV. Does NOT trigger for editing an existing CV without a target job, general interview coaching, salary research, job searching/scraping, or writing job descriptions.
argument-hint: [job-offer-text-or-url]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Agent
---

# Skill: job-application-tailor

## How it works

This skill takes a job offer and your master CV, then produces a complete application pack: tailored CV (DOCX + PDF), motivation letter, LinkedIn messages with real contact names, and an interview prep guide with fit score. Every claim in the output is grounded in the source CV — nothing is invented.

## Directory layout

**`PROJECT_ROOT`** (current working directory) holds your data:
- `resources/MASTER_CV.docx` — source CV
- `resources/cv_fact_base.json` + `.cv_hash` — cached extraction (auto-managed)
- `output/` — generated packs, named `[fit_level]-[date]-[job-slug]/`

**`SKILL_BASE`** (`.claude/skills/job-application-tailor`) holds reusable infrastructure:
- `prompts/` — step-by-step instructions for each generation task
- `schemas/` — JSON schemas that validate every intermediate file
- `scripts/` — Python for DOCX generation, validation, caching
- `config/` — formatting, naming rules, language labels, fit thresholds
- `references/commands.md` — exact bash commands for every operation

Resolve both at the start. See `references/commands.md` § Setup.

## Hard rules

These exist because recruiters and hiring managers spot fabrications instantly, and a single invented skill or inflated title can disqualify an otherwise strong application:

- **Truthfulness first** — never invent experience, tools, certifications, domains, or achievements
- **Recent timeline is complete** — every role from the cutoff year (configurable in `config/settings.default.yaml` → `behaviour.experience_compression_cutoff_year`) onward appears in the output. Roles that ended before that cutoff may be consolidated into a single dateless "Earlier experience" line — *unless* they are load-bearing for the target job, in which case they are kept fully. See `prompts/tailor_cv.md` § Earlier-experience compression. The goal is to respect recruiter attention span on senior profiles while never dropping evidence the job actually relies on.
- **Chronological integrity** — strict reverse-chronological order, no reordering
- **Honest gap handling** — if a requirement isn't evidenced, de-emphasise it, surface adjacent experience truthfully, or acknowledge a learning trajectory
- **Structural consistency** — CV formatting derived from the master CV (contact labels, skills section granularity, experience line order, education date format, languages format) must be identical across all runs. Only content emphasis changes between applications, never the structural layout. See `prompts/tailor_cv.md` § Structural consistency for details.

## Infrastructure

The skill bundles Python scripts, JSON schemas, and prompt files. Use them — they exist because earlier runs without them produced inconsistent output:

- **Prompt files** (`prompts/*.md`) — read each one and follow its instructions for the corresponding step. They define the exact output format by referencing the schema files.
- **Schema validation** (`scripts/validate.py`) — run after generating each JSON file. Don't proceed if validation fails — fix and re-validate. This catches malformed output before it reaches DOCX generation.
- **DOCX generation** (`scripts/generate_outputs.py`) — the single path for producing final files. It validates inputs against schemas, generates DOCX with professional styling matching the master CV, and auto-converts to PDF.
- **CV caching** — the fact base extraction is expensive, so it's cached in `resources/`. The cache is keyed on the CV file's SHA-256 hash — if the CV hasn't changed, the cached extraction is reused.

## Workflow

### Step 0 — Pre-flight

Verify dependencies and read config (`config/settings.default.yaml` merged with the optional user override at `<user-data-dir>/settings.yaml`, plus `config/naming_rules.yaml`).

**Check for master CV** — if `<user-data-dir>/MASTER_CV.docx` does not exist, trigger first-run onboarding instead of stopping cold:

```bash
python -m scripts.init
```

`scripts/init.py` resolves the user data dir (via `scripts/paths.py::resolve_user_data_dir`, which honours `JOB_TAILOR_HOME`, the legacy `resources/` layout, or the OS-standard app data dir), creates the directory and its `output/` subfolder, and copies three files from `samples/`:

- `MASTER_CV.example.docx` — a fictional neutral CV the user can open in Word to see the section headers, skills-table structure, and date formats the extractor expects.
- `cv_addendum.template.md` — a commented template for the per-run enrichment layer (Phase 1).
- `user_prefs.template.yaml` — a commented template with every available preference key.

Init is idempotent and **never** overwrites an existing `MASTER_CV.docx`, `cv_addendum.md`, or `user_prefs.yaml`. After running it, surface the printed "Next steps" to the user and stop until they save their real CV as `<user-data-dir>/MASTER_CV.docx`. Do not attempt to generate an application pack from the example CV — it is a reference, not a substitute.

Once confirmed, create the output folder with `_prep/` subfolder. Language defaults to `auto` (detected from the job offer later). See `references/commands.md` § Setup.

**Initialise the job history database** — ensure `resources/job_history.db` exists. Only run the backfill script if the database is empty AND the `output/` folder exists and contains subdirectories with `_prep/job_offer_analysis.json` files. For a fresh install with no prior output, skip backfill entirely. See `references/commands.md` § Job History Database.

**Check company blacklist** — if the company name is already known (e.g. from the URL or user input), check the blacklist before proceeding. If blacklisted, inform the user and stop unless they explicitly override. See `references/commands.md` § Company Lists.

**Load user customization layer** — read the optional user-owned files `resources/cv_addendum.md` and `resources/user_prefs.yaml` via `scripts/user_customization.py`:

```python
from scripts.user_customization import load_customization_context
ctx = load_customization_context("resources")  # -> {"addendum": {...}, "prefs": {...}}
```

Both files are optional; missing files return typed empty defaults. Store the returned dict as `$CUSTOMIZATION` for later steps. This is the canonical place for:

- **Addendum** — additional experience bullets, hidden skills, off-CV facts. Merged into the in-memory fact base by `merge_addendum_into_fact_base()` at Step 5 (tailor_cv). The addendum is a per-run in-memory layer only — it never mutates `resources/cv_fact_base.json`.
- **User prefs** — `preferred_title_labels`, `forbidden_title_labels`, `tone_directives`, `team_context_companies`, `default_language`. Passed into tailor_cv (Step 5), the motivation letter (Step 6), and LinkedIn messages (Step 7). Replaces what used to live in user-specific Claude memories.

Store `$OUTPUT_DIR` and `$PREP_DIR` for later steps.

### Step 1 — Read the master CV

Extract text from the DOCX. See `references/commands.md` § CV Caching for the read command.

### Step 2 — Extract CV fact base (cached)

Check the cache first. If valid, copy `cv_fact_base.json` into `$PREP_DIR` and skip ahead. If stale, read `prompts/extract_cv_data.md`, generate the fact base, validate against `schemas/cv_fact_base.schema.json`, then save the cache for future runs. See `references/commands.md` § CV Caching.

### Step 2.5 — Verify fact base against raw CV

**This step is mandatory and must not be skipped.** It exists because the LLM can unconsciously contaminate the fact base with keywords from the job offer, especially when both are processed in the same context window.

Run `scripts/verify_fact_base.py` with the master CV and the fact base. See `references/commands.md` § Verify Fact Base Against Raw CV.

- **If verification fails** (exit code 1): technologies or methodologies were fabricated. Remove the flagged items from `cv_fact_base.json`, re-run verification, and only proceed once it passes. If the cache was just saved, re-save it after fixing.
- **Warnings** about skills are non-blocking — review them but they are often valid abstractions of role descriptions.

This step must complete **before** the job offer is analysed, so the fact base is locked before job-offer keywords enter the context.

### Step 3 — Analyse the job offer

If `$ARGUMENTS` is a URL, fetch it with WebFetch first. **Cache the raw offer text** to `$PREP_DIR/raw_offer.md` before analysis — write the full WebFetch response (or the pasted text if the user supplied one) as-is. This gives an audit trail and survives the posting being pulled. See `references/commands.md` § Cache Raw Offer.

Then read `prompts/analyze_job_offer.md`, produce `job_offer_analysis.json`, validate against `schemas/job_offer_analysis.schema.json`. Note the `detected_language` — it drives the language of all subsequent output.

### Step 3.5 — Duplicate & history check

After the job offer analysis is complete (company name and required skills are known), check the job history database for duplicates. See `references/commands.md` § Duplicate Detection.

The check uses three layers:
1. **Exact URL match** — same source URL used before
2. **Company + title match** — normalised comparison (case-insensitive, common abbreviations unified)
3. **Fuzzy skill match** — same company but different title: if >80% of required skills overlap, flag as likely duplicate

**If a duplicate is found**: show the user the previous application details (date, fit score, output folder path) and ask whether to proceed or skip. Do not silently continue.

**If no duplicate but same company**: surface previous applications as context — "You applied to [Company] on [date] for [title] ([fit]% fit). This is a different role." This informs but doesn't block.

**Check company blacklist** — if the company was identified in Step 3, verify it's not blacklisted. If blacklisted, inform the user (include the reason if one was stored) and stop unless they explicitly override.

### Step 3.6 — Research the company

Check `config/settings.default.yaml` → `behaviour.skip_company_research`. If `true`, skip this step entirely and proceed to Step 4. If WebSearch is unavailable (user hasn't granted permission), skip gracefully and note it in the output — the rest of the pipeline works fine without company research, just without personalised contact names in LinkedIn messages.

If a company name was found and research is enabled, use **WebSearch in the foreground** (background agents can't get approval for web tools) to find:
- Size, ownership, recent news, culture signals, tech stack
- **Key contacts** — names, titles, LinkedIn URLs for recruiters, hiring managers, tech leads

Save as `$PREP_DIR/company_research.md` with a `## Contacts` section. If the research reveals company size that the job offer didn't mention, update the `company_size` field in `job_offer_analysis.json` — this feeds into CV tailoring (small companies value versatility, large ones value depth).

### Step 4 — Match/gap analysis

Read `prompts/match_analysis.md`. Produce a requirement-by-requirement matrix (direct / transferable / gap). Validate against `schemas/match_analysis.schema.json`.

After validation, **rename the output folder** with a fit-level prefix (`low` / `medium` / `good` / `very_good`) based on `overall_fit_pct`. Thresholds are in `config/settings.default.yaml`. See `references/commands.md` § Folder Rename. Update `$OUTPUT_DIR` and `$PREP_DIR`.

**If `overall_fit_pct` is below 50%, STOP here.** Do not proceed to CV tailoring or any further steps. Inform the user of the fit score, summarise the key gaps, and explain why the application was not generated. The match analysis and renamed output folder are kept so the user can review the assessment.

**Dry-run mode**: check `config/settings.default.yaml` → `behaviour.dry_run`. If `true`, stop here after displaying the fit score and match summary — do not generate CV, letters, or any output files. This is useful for quickly scanning multiple job offers to assess fit before committing to full generation. The match analysis is still saved and the application is still recorded in the database. The user can also trigger dry-run by including "dry run" or "just the score" in their request.

### Step 5 — Tailor the CV

Read `prompts/tailor_cv.md`. Use the match analysis and company research to guide emphasis. The prompt includes company-size awareness rules — small companies get expanded versatility bullets, large companies get focused technical depth. It also includes an "Earlier-experience compression" rule: before invoking the prompt, read `config/settings.default.yaml` → `behaviour.experience_compression_cutoff_year` and pass it to the tailoring step as the cutoff year. The prompt explains how the tailoring step uses the cutoff to decide whether each pre-cutoff role stays full or gets folded into a consolidated line. Validate against `schemas/tailored_cv.schema.json`.

**Before invoking the prompt**, merge the user's addendum into the in-memory fact base and pass the user prefs in as context:

```python
from scripts.user_customization import merge_addendum_into_fact_base
fact_base_for_tailoring = merge_addendum_into_fact_base(fact_base, $CUSTOMIZATION["addendum"])
# Pass to the prompt: fact_base_for_tailoring, $CUSTOMIZATION["prefs"]
```

The merged fact base must NOT be written back to `resources/cv_fact_base.json`. It's used only for this tailoring run.

After the tailored CV is produced, optionally run the invariant checker from `scripts/user_customization.py` to catch forbidden title labels the model might have slipped through:

```python
from scripts.user_customization import find_forbidden_title_label_violations
violations = find_forbidden_title_label_violations(tailored_cv, $CUSTOMIZATION["prefs"])
# if violations: surface them and regenerate
```

### Steps 6, 7 — Letter and LinkedIn (parallel agents)

These two steps are independent once the tailored CV exists. **Spawn two Agent subagents simultaneously** to generate them in parallel. Both subagents must receive `$CUSTOMIZATION["prefs"]` and `$CUSTOMIZATION["addendum"]` as additional context — the letter generator honours `tone_directives` and `team_context_companies`, the LinkedIn generator honours `tone_directives`.

**Subagent 1 — Motivation letter:**
Read `prompts/generate_motivation_letter.md`. Use the CV fact base, job offer analysis, match analysis, and company research as context. Save as `$PREP_DIR/letter.json`. Validate against `schemas/letter.schema.json`. Then generate the **short version** (500-750 characters body): read `prompts/generate_short_letter.md`, pass it the full letter as context, save as `$PREP_DIR/short_letter.json`. Validate against the same schema.

**Subagent 2 — LinkedIn messages:**
Read `prompts/generate_linkedin_message.md`. Use the CV fact base, job offer analysis, match analysis, and company research (especially the Contacts section) as context. Save as `$PREP_DIR/linkedin.json`. Validate against `schemas/linkedin.schema.json`.

Wait for both subagents to complete before proceeding to Step 8.

**Write permission note:** subagents need to write JSON into `$PREP_DIR`. The project's `.claude/settings.local.json` pre-approves `Write(output/**)` for exactly this reason. If you ever see a subagent report "Write permission denied" for `output/**/_prep/*.json`:
1. Confirm the allow rule is still present in `.claude/settings.local.json`.
2. If a subagent returned the generated JSON in its final message instead of saving it, save it yourself from the main context and continue — don't re-run the subagent.

### Step 8 — Interview prep (foreground)

**Do not use a background agent for this step.** Interview prep is markdown-only (no schema validation via Bash), and background agents can encounter permission issues that silently fail. Generate this in the main context instead.

Read `prompts/generate_interview_prep.md`. Use all available context (CV fact base, job offer analysis, match analysis, company research). Include a quick reference block (job URL from `$ARGUMENTS`, output folder path, application date), fit score banner, and company context section. Save as `$PREP_DIR/interview_prep.md`.

### Step 9 — Generate output files

Run `scripts/generate_outputs.py` with `--output-dir` pointing to `$OUTPUT_DIR`. The script validates all JSON inputs against schemas before generating anything, then produces DOCX (with professional styling), PDF (via Microsoft Word if available), TXT, and MD files plus `run_summary.json`. See `references/commands.md` § Generate Final Output Files.

When regenerating outputs for an existing folder (not the first run), prefer `scripts/cli.py regenerate-outputs` — it reads `job_title` and `detected_language` from `_prep/job_offer_analysis.json` and assembles the 10-flag invocation automatically. See `references/commands.md` § Regenerate Outputs.

### Step 10 — Record in job history

After all output files are generated, record this application in the database. See `references/commands.md` § Record Application. This stores the company, title, skills, fit score, and output folder path so future runs can detect duplicates and surface history.

## Error recovery & fallbacks

1. **Company research unavailable** — If WebSearch is denied or fails, skip Step 3.6 gracefully. LinkedIn messages will use placeholder names (e.g. "Hiring Manager"). All other outputs work normally without company research data.

2. **Schema validation failure** — Fix the JSON and re-validate. Do not proceed to the next step until validation passes. Common causes: missing required fields, wrong enum values, malformed arrays.

3. **Fact base verification failure** — Remove flagged items from `cv_fact_base.json` and re-verify. If the cache was just saved, re-save it after fixing. This usually means job offer keywords leaked into the fact base during extraction.

4. **Database missing or corrupted** — If `job_history.db` doesn't exist, it's created automatically on first run. If corrupted, delete it and re-run — the backfill script can reimport from existing output folders.

5. **DOCX generation failure** — Check that all required JSON files exist in `_prep/`. Common cause: missing `letter.json` or `linkedin.json`. Re-run the missing step before retrying Step 9.

6. **PDF conversion failure** — PDF generation requires Microsoft Word. If unavailable, DOCX files are still generated successfully. The user can convert manually.

## Output

All files land in `$PROJECT_ROOT/output/[fit_level]-[date]-[job-slug]/`:

| File | Format |
|------|--------|
| CV | DOCX + PDF |
| Motivation letter | DOCX |
| Short motivation letter | TXT (500-750 chars, for online forms) |
| LinkedIn messages | TXT (with contact names and LinkedIn URLs) |
| Interview prep | MD (with quick reference links and fit score banner) |
| Run summary | JSON (fit %, match counts, file paths) |

Filename patterns are language-aware (FR: `Lettre_de_motivation_...`, EN: `Cover_letter_...`) — configured in `config/naming_rules.yaml`.

## Re-running individual steps

If the user asks to regenerate a specific output (e.g. "redo the LinkedIn messages", "regenerate the letter for Eddyfi"), you don't need to re-run the full pipeline. Each step's inputs and outputs are in `$PREP_DIR` (`$OUTPUT_DIR/_prep`).

### Input/output mapping

| Step | Reads from `_prep/` | Writes to `_prep/` |
|------|---------------------|---------------------|
| 5 — Tailor CV | cv_fact_base.json, job_offer_analysis.json, match_analysis.json, company_research.md | tailored_cv.json |
| 6 — Letter | cv_fact_base.json, job_offer_analysis.json, match_analysis.json, company_research.md | letter.json, short_letter.json |
| 7 — LinkedIn | cv_fact_base.json, job_offer_analysis.json, match_analysis.json, company_research.md | linkedin.json |
| 8 — Interview prep | All of the above | interview_prep.md |

### Detecting which step to re-run

Parse the user's request for keywords:
- "CV", "resume", "tailored CV" -> Step 5
- "letter", "cover letter", "motivation letter" -> Step 6
- "short letter", "short version" -> Step 6 (short letter part only)
- "LinkedIn", "messages", "InMail" -> Step 7
- "interview", "prep", "preparation" -> Step 8
- "all outputs", "everything" -> Step 9 only (re-generate DOCX/PDF from existing JSON)

### How to re-run a step

1. **Find the output folder** — ask the user which application, or find the most recent folder in `output/` matching their description.
2. Set `$OUTPUT_DIR` to that folder and `$PREP_DIR` to `$OUTPUT_DIR/_prep`.
3. **Read the required input files** from `$PREP_DIR` — if any are missing, inform the user which earlier step needs to run first.
4. **Read the prompt file** for the target step (e.g. `prompts/generate_motivation_letter.md`) and follow its instructions using the existing `_prep/` files as context.
5. **Validate** the generated JSON against its schema (same as the original step).
6. **Re-run Step 9** to produce updated DOCX/PDF/TXT files from the new JSON. Use `scripts/cli.py regenerate-outputs <app-folder-or-id>` — it reads job title and language from `_prep/job_offer_analysis.json` and assembles the full `generate_outputs.py` invocation. See `references/commands.md` § Regenerate Outputs.
