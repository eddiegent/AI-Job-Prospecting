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
- **Complete timeline** — every role and training period from the master CV appears in the output (compressed if less relevant, but never removed) so there are no visible gaps
- **Chronological integrity** — strict reverse-chronological order, no reordering
- **Honest gap handling** — if a requirement isn't evidenced, de-emphasise it, surface adjacent experience truthfully, or acknowledge a learning trajectory

## Infrastructure

The skill bundles Python scripts, JSON schemas, and prompt files. Use them — they exist because earlier runs without them produced inconsistent output:

- **Prompt files** (`prompts/*.md`) — read each one and follow its instructions for the corresponding step. They define the exact output format by referencing the schema files.
- **Schema validation** (`scripts/validate.py`) — run after generating each JSON file. Don't proceed if validation fails — fix and re-validate. This catches malformed output before it reaches DOCX generation.
- **DOCX generation** (`scripts/generate_outputs.py`) — the single path for producing final files. It validates inputs against schemas, generates DOCX with professional styling matching the master CV, and auto-converts to PDF.
- **CV caching** — the fact base extraction is expensive, so it's cached in `resources/`. The cache is keyed on the CV file's SHA-256 hash — if the CV hasn't changed, the cached extraction is reused.

## Workflow

### Step 0 — Pre-flight

Verify dependencies and read config (`config/settings.yaml`, `config/naming_rules.yaml`).

**Check for master CV** — if `resources/MASTER_CV.docx` does not exist, do not proceed. Instead, guide the user:
> "No master CV found. To get started, save your CV as a `.docx` file at `resources/MASTER_CV.docx`, then run this command again. See `resources/README.md` for details."
Stop here until the file is in place.

Once confirmed, create the output folder with `_prep/` subfolder. Language defaults to `auto` (detected from the job offer later). See `references/commands.md` § Setup.

**Initialise the job history database** — ensure `resources/job_history.db` exists. Only run the backfill script if the database is empty AND the `output/` folder exists and contains subdirectories with `_prep/job_offer_analysis.json` files. For a fresh install with no prior output, skip backfill entirely. See `references/commands.md` § Job History Database.

**Check company blacklist** — if the company name is already known (e.g. from the URL or user input), check the blacklist before proceeding. If blacklisted, inform the user and stop unless they explicitly override. See `references/commands.md` § Company Lists.

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

If `$ARGUMENTS` is a URL, fetch it with WebFetch first. Read `prompts/analyze_job_offer.md`, produce `job_offer_analysis.json`, validate against `schemas/job_offer_analysis.schema.json`. Note the `detected_language` — it drives the language of all subsequent output.

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

Check `config/settings.yaml` → `behaviour.skip_company_research`. If `true`, skip this step entirely and proceed to Step 4. If WebSearch is unavailable (user hasn't granted permission), skip gracefully and note it in the output — the rest of the pipeline works fine without company research, just without personalised contact names in LinkedIn messages.

If a company name was found and research is enabled, use **WebSearch in the foreground** (background agents can't get approval for web tools) to find:
- Size, ownership, recent news, culture signals, tech stack
- **Key contacts** — names, titles, LinkedIn URLs for recruiters, hiring managers, tech leads

Save as `$PREP_DIR/company_research.md` with a `## Contacts` section. If the research reveals company size that the job offer didn't mention, update the `company_size` field in `job_offer_analysis.json` — this feeds into CV tailoring (small companies value versatility, large ones value depth).

### Step 4 — Match/gap analysis

Read `prompts/match_analysis.md`. Produce a requirement-by-requirement matrix (direct / transferable / gap). Validate against `schemas/match_analysis.schema.json`.

After validation, **rename the output folder** with a fit-level prefix (`low` / `medium` / `good` / `very_good`) based on `overall_fit_pct`. Thresholds are in `config/settings.yaml`. See `references/commands.md` § Folder Rename. Update `$OUTPUT_DIR` and `$PREP_DIR`.

**If `overall_fit_pct` is below 50%, STOP here.** Do not proceed to CV tailoring or any further steps. Inform the user of the fit score, summarise the key gaps, and explain why the application was not generated. The match analysis and renamed output folder are kept so the user can review the assessment.

**Dry-run mode**: check `config/settings.yaml` → `behaviour.dry_run`. If `true`, stop here after displaying the fit score and match summary — do not generate CV, letters, or any output files. This is useful for quickly scanning multiple job offers to assess fit before committing to full generation. The match analysis is still saved and the application is still recorded in the database. The user can also trigger dry-run by including "dry run" or "just the score" in their request.

### Step 5 — Tailor the CV

Read `prompts/tailor_cv.md`. Use the match analysis and company research to guide emphasis. The prompt includes company-size awareness rules — small companies get expanded versatility bullets, large companies get focused technical depth. Validate against `schemas/tailored_cv.schema.json`.

### Steps 6, 7 — Letter and LinkedIn (parallel agents)

These two steps are independent once the tailored CV exists. **Spawn two Agent subagents simultaneously** to generate them in parallel:

**Subagent 1 — Motivation letter:**
Read `prompts/generate_motivation_letter.md`. Use the CV fact base, job offer analysis, match analysis, and company research as context. Save as `$PREP_DIR/letter.json`. Validate against `schemas/letter.schema.json`. Then generate the **short version** (500-750 characters body): read `prompts/generate_short_letter.md`, pass it the full letter as context, save as `$PREP_DIR/short_letter.json`. Validate against the same schema.

**Subagent 2 — LinkedIn messages:**
Read `prompts/generate_linkedin_message.md`. Use the CV fact base, job offer analysis, match analysis, and company research (especially the Contacts section) as context. Save as `$PREP_DIR/linkedin.json`. Validate against `schemas/linkedin.schema.json`.

Wait for both subagents to complete before proceeding to Step 8.

### Step 8 — Interview prep (foreground)

**Do not use a background agent for this step.** Interview prep is markdown-only (no schema validation via Bash), and background agents can encounter permission issues that silently fail. Generate this in the main context instead.

Read `prompts/generate_interview_prep.md`. Use all available context (CV fact base, job offer analysis, match analysis, company research). Include a quick reference block (job URL from `$ARGUMENTS`, output folder path, application date), fit score banner, and company context section. Save as `$PREP_DIR/interview_prep.md`.

### Step 9 — Generate output files

Run `scripts/generate_outputs.py` with `--output-dir` pointing to `$OUTPUT_DIR`. The script validates all JSON inputs against schemas before generating anything, then produces DOCX (with professional styling), PDF (via Microsoft Word if available), TXT, and MD files plus `run_summary.json`. See `references/commands.md` § Generate Final Output Files.

### Step 10 — Record in job history

After all output files are generated, record this application in the database. See `references/commands.md` § Record Application. This stores the company, title, skills, fit score, and output folder path so future runs can detect duplicates and surface history.

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
