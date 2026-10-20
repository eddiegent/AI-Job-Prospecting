---
name: job-application-tailor
description: Generate a complete, tailored application pack (CV, motivation letter, short letter, LinkedIn messages, interview prep with fit score) from a job offer and a master CV. Triggers whenever the user provides a job offer URL, pastes a job description, asks to apply for a position, wants to check their fit for a role, or requests any combination of tailored CV, cover letter, or application materials. Also triggers for "prepare my application", "help me apply", "write a cover letter", "match my CV to this offer", "tailor my CV", "how well do I fit this job", "prepare my candidature", or any request in French or English involving a specific job posting and the user's CV. Does NOT trigger for editing an existing CV without a target job, general interview coaching, salary research, job searching/scraping, or writing job descriptions.
argument-hint: "[job-offer-text-or-url]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Agent
---

# Skill: job-application-tailor

## How it works

This skill takes a job offer and your master CV, then produces a complete application pack: tailored CV (DOCX + PDF), motivation letter, LinkedIn messages with real contact names, and an interview prep guide with fit score. Every claim in the output is grounded in the source CV — nothing is invented.

## Directory layout

**`PROJECT_ROOT`** (current working directory) holds your data:
- `resources/MASTER_CV.docx` — source CV (or wherever preflight's `master_cv_path` points)
- `resources/cv_fact_base.json` + `.cv_hash` — cached extraction (auto-managed)
- `output/` — generated packs, named `[fit_level]-[date]-[job-slug]/`

**`SKILL_BASE`** (`.claude/skills/job-application-tailor`) holds reusable infrastructure:
- `prompts/` — instructions for each generation step (`cv_rules.md` holds the CV rules shared with the cold flow)
- `schemas/` — JSON schemas for every intermediate file
- `scripts/` — Python: `cli.py` (all commands), DOCX/PDF generation, caching, guards
- `config/` — formatting, naming rules, language labels, fit thresholds
- `references/commands.md` — the bash for each step · `references/cli.md` — every flag · `references/troubleshooting.md` — DB, PDF, permission and verification problems

Every command below runs as `cd "$SKILL_BASE" && python scripts/cli.py …`. Quote every path — they may contain spaces.

## Hard rules

These exist because recruiters and hiring managers spot fabrications instantly, and a single invented skill or inflated title can disqualify an otherwise strong application:

- **Truthfulness first** — never invent experience, tools, certifications, domains, or achievements
- **Recent timeline is complete** — every role from the cutoff year (`config/settings.default.yaml` → `behaviour.experience_compression_cutoff_year`) onward appears in the output. Older roles may be consolidated into a single dateless "Earlier experience" line — *unless* they are load-bearing for the target job, in which case they are kept fully. See `prompts/cv_rules.md` § Earlier-experience compression.
- **Chronological integrity** — strict reverse-chronological order, no reordering
- **Honest gap handling** — if a requirement isn't evidenced, de-emphasise it, surface adjacent experience truthfully, or acknowledge a learning trajectory
- **Structural consistency** — CV formatting derived from the master CV (contact labels, skills section granularity, experience line order, education date format, languages format) is identical across all runs. Only content emphasis changes. See `prompts/cv_rules.md` § Structural consistency.

## Gates

After writing each intermediate file, run its gate — one command that runs every deterministic check for that stage (schema validation plus the stage's guards) and reports all problems at once:

```bash
cd "$SKILL_BASE" && python scripts/cli.py gate <stage> "$OUTPUT_DIR"
```

Exit 0 = continue. Exit 1 = fix the file and re-run the gate; never continue past a failing gate. Each guard exists because it caught a real failure the prompts alone did not prevent: fabricated tech in the fact base, miscounted fit scores, false "direct" matches, forbidden title labels, over-claimed skills, job-posting technologies leaking into the CV.

**Fix the output, never the source.** When a gate fails, change the generated wording. Do not edit the master CV, the addendum or `.cv_hash` to make a gate pass.

## Workflow

### Steps 0–2.5 — CV preparation (delegated)

Read `job-prep-cv/SKILL.md` — a sibling of this skill's folder (`.claude/skills/job-prep-cv/` in the repo, `$CLAUDE_PLUGIN_ROOT/skills/job-prep-cv/` when installed as a plugin) — and follow it with:

- `$FLOW = "offer"` (folder `[date]-[slug]/`; Step 4 adds the fit-level prefix)
- `$INPUT_SEED = $ARGUMENTS` (the offer text, URL, or title hint — seeds a placeholder slug)
- `$EARLY_BLACKLIST_NAME` unset — the blacklist check happens in Step 3.5 with the canonical company name.

It returns with `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR` (= `$SKILL_BASE` for this flow), `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION` set and the fact base verified.

### Step 3 — Analyse the job offer

If `$ARGUMENTS` is a URL, run `probe-url` first (`references/commands.md` § URL Probe) — some French aggregators return 403 to automated requests. If it prints `BLOCKED`, skip WebFetch and ask the user to paste the offer text or share a local file.

Otherwise fetch with WebFetch. **WebFetch's summariser can silently translate a non-English posting into English**, which produces a pack in the wrong language — so always put in the WebFetch prompt: *"Return the full job posting text EXACTLY as it appears on the page, preserving the ORIGINAL LANGUAGE — do NOT translate."* The cross-checks in `prompts/analyze_job_offer.md` § *Language mis-detection cross-check* are the final safety net.

Save the raw text (fetched or pasted) with `cache-raw-offer` before analysing (`references/commands.md` § Cache Raw Offer) — it is the audit trail if the posting is pulled. Then follow `prompts/analyze_job_offer.md`, write `job_offer_analysis.json`, and run **`gate offer`**. `detected_language` drives the language of every later output.

**Platform vs. real employer.** Job boards (Free-Work, Indeed, LinkedIn… — `config/settings.default.yaml` → `aggregators.known_platforms`) post for real clients, and a pack tailored to the board is wasted. If the analysis didn't already set `company_is_aggregator: true` or `source_platform`, run `detect-platform "$OUTPUT_DIR"`; a printed name means it is a platform. When flagged, ask: *"`<company_name>` looks like a platform, not usually the employer. Who's the real client? (blank = keep it, or 'force' to confirm you really mean this company.)"*
- Real client named → `company_name` = client, `source_platform` = old name, `company_is_aggregator: false`.
- `force` → keep `company_name`, set `company_is_aggregator: false`, omit `source_platform`.
- Blank → leave the file as produced (the flags stay for the history record).

Re-run `gate offer` after any edit.

### Step 3.5 — Duplicate & history check

```bash
cd "$SKILL_BASE" && python scripts/cli.py check-duplicate "$PREP_DIR" --url "<job-url>"
```

- Exit 1, duplicate → show the previous application (id, fit, date, folder) and ask whether to proceed. Never continue silently.
- Exit 1, output starts `[!] BLACKLIST` → stop unless the user explicitly overrides.
- Exit 0 with an `Other applications to …` block → mention the earlier applications as context ("You applied to X on [date] for [title], [fit]% fit — this is a different role") and continue.

### Step 3.6 — Research the company

Skip if `behaviour.skip_company_research` is `true`, or if WebSearch is unavailable (note it; LinkedIn messages then use placeholder names like "Hiring Manager"; everything else works). Otherwise use **WebSearch in the foreground** (background agents can't get web-tool approval) for size, ownership, recent news, culture signals, tech stack, and **key contacts** (names, titles, LinkedIn URLs of recruiters, hiring managers, tech leads).

Save `$PREP_DIR/company_research.md` with a `## Contacts` section. If research reveals a company size the offer didn't state, update `company_size` in `job_offer_analysis.json` — CV tailoring uses it (small companies value versatility, large ones depth).

### Step 3.9 — Build the merged fact base (never skip)

```bash
cd "$SKILL_BASE" && python scripts/claims_guard.py merge "$PREP_DIR"
```

Writes `$PREP_DIR/cv_fact_base_merged.json`: cached fact base + addendum bullets + skill-calibration notes + the master CV's familiar-only skills. **Every later step reads this file** — it is what "the fact base" means from here on. An earlier run skipped the addendum and over-claimed skills; this file makes that impossible to do silently. It is per-run: never write it back to `resources/`.

### Step 4 — Match/gap analysis

Follow `prompts/match_analysis.md` to produce a requirement-by-requirement matrix (direct / transferable / gap), then run **`gate match`**. The gate recounts `match_summary` from `matches[]` (the model regularly miscounts it), validates, and rejects any `direct` match whose technology isn't in the fact base — a false direct inflates the fit score past the 50% gate and the CV inherits the claim. On a grounding failure, downgrade the flagged requirements to `transferable` (with a concrete `notes`) or `gap`, and re-run.

Then rename the folder — this adds the fit-level prefix (`low` / `medium` / `good` / `very_good`, thresholds in settings) and rebuilds the slug from `job_title` + `company_name`:

```bash
cd "$SKILL_BASE" && python scripts/cli.py rename-with-fit "$OUTPUT_DIR"
```

Set `$OUTPUT_DIR` to the printed path and `$PREP_DIR` to `$OUTPUT_DIR/_prep`.

**If `overall_fit_pct` is below 50%, stop.** Tell the user the score, summarise the key gaps, and explain why no pack was generated. The analysis and renamed folder are kept for review.

**Dry run** — if `behaviour.dry_run` is `true`, or the user said "dry run" / "just the score", stop here after showing the fit score and match summary, then record the application (Step 10). Useful for scanning several offers before committing to full generation.

### Step 5 — Tailor the CV

Follow `prompts/tailor_cv.md` (it starts by loading `prompts/cv_rules.md`). Pass it the merged fact base, the match analysis, the company research, `$CUSTOMIZATION["prefs"]`, and the `experience_compression_cutoff_year` from settings. Write `tailored_cv.json` and run **`gate cv`** (schema + forbidden title labels from `user_prefs.yaml` + claims check). Build no DOCX/PDF until it passes.

### Steps 6, 7 — Letter and LinkedIn (parallel agents)

Once the CV passes its gate these two are independent. **Spawn two Agent subagents at the same time.** Give each the paths to the merged fact base, `job_offer_analysis.json`, `match_analysis.json`, `company_research.md`, `$SKILL_BASE` and `$OUTPUT_DIR`, plus `$CUSTOMIZATION["prefs"]` and `$CUSTOMIZATION["addendum"]` (the letter honours `tone_directives` and `team_context_companies`; LinkedIn honours `tone_directives`).

- **Subagent 1 — letters.** Follow `prompts/generate_motivation_letter.md` → `letter.json`. Then `prompts/generate_short_letter.md` with the full letter as context → `short_letter.json` (body 500–750 characters). Run **`gate letters`**.
- **Subagent 2 — LinkedIn.** Follow `prompts/generate_linkedin_message.md` (use the Contacts section) → `linkedin.json`. Run **`gate linkedin`**.

Each subagent returns only once its gate passes. Wait for both, then **run `gate letters` and `gate linkedin` yourself** — don't take a subagent's word for it, and never build files from JSON that hasn't passed its gate in this context. If a subagent couldn't write into `_prep/`, see `references/troubleshooting.md`.

### Step 8 — Interview prep (foreground)

Generate this in the main context, not a background agent — background agents can hit permission issues that fail silently, and this step has no gate to catch it. Follow `prompts/generate_interview_prep.md` with all the context above. Include a quick reference block (job URL from `$ARGUMENTS`, output folder path, application date), the fit score banner, and a company context section. Save `$PREP_DIR/interview_prep.md`; Step 9 renders it as mobile-friendly HTML.

### Step 9 — Build the output files

```bash
cd "$SKILL_BASE" && python scripts/cli.py regenerate-outputs "$OUTPUT_DIR"
```

Reads everything it needs from `_prep/` (title and language from `job_offer_analysis.json`) and produces the CV DOCX + PDF, letter DOCX, short-letter and LinkedIn TXT, interview-prep HTML and `run_summary.json`. The same command rebuilds a pack later. If it reports missing inputs, `--check` lists them.

### Step 10 — Record in job history

```bash
cd "$SKILL_BASE" && python scripts/cli.py record-application "$OUTPUT_DIR"
```

Stores company, title, skills, fit score and folder so future runs detect duplicates and surface history. Tell the user the output folder and the application id (for `/job-status` updates).

## Output

All files land in `$PROJECT_ROOT/output/[fit_level]-[date]-[job-slug]/`:

| File | Format |
|------|--------|
| CV | DOCX + PDF |
| Motivation letter | DOCX |
| Short motivation letter | TXT (500-750 chars, for online forms) |
| LinkedIn messages | TXT (with contact names and LinkedIn URLs) |
| Interview prep | HTML (responsive; quick reference links and fit score banner) |
| Run summary | JSON (fit %, match counts, file paths) |

Filenames are language-aware (FR: `Lettre_de_motivation_...`, EN: `Cover_letter_...`) — see `config/naming_rules.yaml`.

## Re-running one step

When the user asks to redo one output ("redo the LinkedIn messages", "regenerate the letter for Acme"), don't re-run the pipeline — every step's inputs are in `_prep/`. ("Regenerate the pack" with no specific output means the full pipeline.)

1. Find the folder — ask, or take the most recent one in `output/` matching their description. Set `$OUTPUT_DIR` and `$PREP_DIR`.
2. If `cv_fact_base_merged.json` is missing (older packs), run Step 3.9 first. If another input the step needs is missing, tell the user which earlier step must run.
3. Re-run the step from its prompt using the existing `_prep/` files, then its gate:

| Request mentions | Step | Writes | Gate |
|---|---|---|---|
| CV, resume | 5 | `tailored_cv.json` | `cv` |
| letter, cover letter, motivation letter | 6 | `letter.json` + `short_letter.json` | `letters` |
| short letter, short version | 6 (short part) | `short_letter.json` | `letters` |
| LinkedIn, messages, InMail | 7 | `linkedin.json` | `linkedin` |
| interview, prep | 8 | `interview_prep.md` | — |
| "all outputs", "everything" (files only) | — | — | — |

4. Run Step 9 (`regenerate-outputs`) to rebuild the files.

For anything that fails outside the gates (DB errors, no PDF, DOCX build errors), read `references/troubleshooting.md`.
