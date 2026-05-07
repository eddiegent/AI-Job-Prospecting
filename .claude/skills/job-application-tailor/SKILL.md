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

### Steps 0–2.5 — CV preparation (delegated)

Read `.claude/skills/job-prep-cv/SKILL.md` and follow its instructions. Pass:

- `$FLOW = "offer"` (selects the `[date]-[slug]/` folder naming used by the offer flow — Step 4 below renames it with a fit-level prefix once the match score is known)
- `$INPUT_SEED = $ARGUMENTS` (the job offer text, URL, or job-title hint — used for the initial folder slug)
- `$EARLY_BLACKLIST_NAME` is **unset** for the offer flow. The blacklist check happens later in Step 3.5 as part of `check-duplicate`, which uses the canonical company name from `job_offer_analysis.json`.

When that sub-skill returns, the following are set: `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR` (= `$SKILL_BASE` for this flow), `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION`, and `$PREP_DIR/cv_fact_base.json` is verified. Continue from Step 3.

For this flow `$SKILL_BASE` is the same path as `$SKILL_BASE_TAILOR` — the rest of this document references `$SKILL_BASE`.

### Step 3 — Analyse the job offer

If `$ARGUMENTS` is a URL, **probe it with a HEAD request first** — French aggregators like Lesjeudis return 403 on automated requests, and a WebFetch round-trip on a blocked host wastes a step before falling back. See `references/commands.md` § URL Probe. If the probe reports `BLOCKED`, skip WebFetch and ask the user to paste the offer text or share a local file path.

Otherwise fetch with WebFetch. **Cache the raw offer text** to `$PREP_DIR/raw_offer.md` before analysis — write the full WebFetch response (or the pasted text if the user supplied one) as-is. This gives an audit trail and survives the posting being pulled. See `references/commands.md` § Cache Raw Offer.

**WebFetch language warning.** WebFetch processes pages through an internal summariser LLM, which can silently **translate** a non-English posting into English before returning it. That breaks language detection downstream and produces an application pack in the wrong language. Always include an explicit instruction in the WebFetch `prompt` like *"Return the full job posting text EXACTLY as it appears on the page, preserving the ORIGINAL LANGUAGE — do NOT translate."* Even with that instruction it may still translate, so the cross-checks in `prompts/analyze_job_offer.md` § *Language mis-detection cross-check* are the final safety net before setting `detected_language`.

Then read `prompts/analyze_job_offer.md`, produce `job_offer_analysis.json`, validate against `schemas/job_offer_analysis.schema.json`. Note the `detected_language` — it drives the language of all subsequent output.

**Platform-vs-client check.** Platforms like Free-Work, Indeed, LinkedIn etc. post on behalf of real employers — tailoring a pack to the platform rather than the real client wastes a run. The full list lives in `config/settings.default.yaml` → `aggregators.known_platforms`.

1. If the LLM already set `company_is_aggregator: true` or `source_platform`, trust it.
2. Otherwise post-annotate: call `scripts.common.matched_aggregator(company_name, known_platforms)`. If it returns a platform name, set `company_is_aggregator: true`. See `references/commands.md` § Platform Detection.
3. When flagged, ask the user: *"`<company_name>` looks like a platform, not usually the employer. Who's the real client? (blank = keep `<company_name>` as-is, or 'force' to confirm you really mean this company.)"*
4. If the user provides a real client name, rewrite `company_name` to that name, set `source_platform` to the original platform value, and set `company_is_aggregator: false`. Re-save and re-validate `job_offer_analysis.json`.
5. If the user replies `force` (or confirms the platform really is the employer — e.g. they work at Free-Work itself), leave `company_name` alone, clear `company_is_aggregator` to `false`, and omit `source_platform`.
6. If the user just presses enter, leave everything as the LLM produced it — the flagged fields stay for the history record.

### Step 3.5 — Duplicate & history check

After the job offer analysis is complete, run the one-shot `check-duplicate` subcommand — it wraps all three history checks, the same-company context surface, and the blacklist lookup in a single call. See `references/commands.md` § Duplicate Detection.

```bash
python scripts/cli.py --db "$PROJECT_ROOT/resources/job_history.db" \
  check-duplicate "$PREP_DIR" --url "<job-url>"
```

Exit code `0` = clear to proceed. Exit code `1` = flagged (duplicate or blacklisted) — stop and surface the output to the user before continuing.

The three duplicate layers:
1. **Exact URL match** — same source URL used before
2. **Company + title match** — normalised comparison (case-insensitive, common abbreviations unified)
3. **Fuzzy skill match** — same company but different title: if >80% of required skills overlap, flag as likely duplicate

**If a duplicate is found**: the subcommand prints the previous application's id, fit score, date, and output folder. Show that to the user and ask whether to proceed or skip. Do not silently continue.

**If no duplicate but same company**: the `Other applications to …` block surfaces previous applications as context — "You applied to [Company] on [date] for [title] ([fit]% fit). This is a different role." This informs but doesn't block.

**Blacklist is part of the same call** — if the company is on the blacklist, the output starts with `[!] BLACKLIST: …` and the reason (if stored). Stop unless the user explicitly overrides.

### Step 3.6 — Research the company

Check `config/settings.default.yaml` → `behaviour.skip_company_research`. If `true`, skip this step entirely and proceed to Step 4. If WebSearch is unavailable (user hasn't granted permission), skip gracefully and note it in the output — the rest of the pipeline works fine without company research, just without personalised contact names in LinkedIn messages.

If a company name was found and research is enabled, use **WebSearch in the foreground** (background agents can't get approval for web tools) to find:
- Size, ownership, recent news, culture signals, tech stack
- **Key contacts** — names, titles, LinkedIn URLs for recruiters, hiring managers, tech leads

Save as `$PREP_DIR/company_research.md` with a `## Contacts` section. If the research reveals company size that the job offer didn't mention, update the `company_size` field in `job_offer_analysis.json` — this feeds into CV tailoring (small companies value versatility, large ones value depth).

### Step 4 — Match/gap analysis

Read `prompts/match_analysis.md`. Produce a requirement-by-requirement matrix (direct / transferable / gap).

**Always run `scripts/recount_match_summary.py` against the produced JSON before validating.** The LLM authors both `matches[]` and `match_summary` and the two regularly drift (counts and `overall_fit_pct` are easy to miscount). The recount script overwrites `match_summary` with the deterministically computed value so downstream steps (folder rename, fit gate, history record) operate on correct figures. See `references/commands.md` § Recount Match Summary.

After the recount, validate against `schemas/match_analysis.schema.json`.

**After validation, run the grounding check.** This is the deterministic guard against false-direct claims — when the LLM marks a JD requirement (e.g. "Kubernetes") as `direct` despite no evidence in the fact base, the inflated `overall_fit_pct` may push a low-fit role through the 50% gate and the tailored CV will inherit the unfounded claim. See `references/commands.md` § Match Grounding Check. If the script exits non-zero, regenerate Step 4 — surface the offending requirements to the prompt and have the LLM downgrade them to `transferable` (with a concrete `notes` explanation) or `gap` before continuing.

After validation, **rename the output folder in one shot** — the helper adds the fit-level prefix (`low` / `medium` / `good` / `very_good`) AND rebuilds the trailing slug from the offer's `job_title` + `company_name`, replacing the placeholder slug that was created at preflight from `$ARGUMENTS`. This collapses two historical renames into one and gives the run a meaningful folder name from this step onward. Thresholds are in `config/settings.default.yaml`. See `references/commands.md` § Folder Rename. Update `$OUTPUT_DIR` and `$PREP_DIR`.

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
