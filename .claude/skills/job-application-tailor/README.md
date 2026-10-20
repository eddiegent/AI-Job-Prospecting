```
     _       _       _        _ _
    (_) ___ | |__   | |_ __ _(_) | ___  _ __
    | |/ _ \| '_ \  | __/ _` | | |/ _ \| '__|
    | | (_) | |_) | | || (_| | | | (_) | |
   _/ |\___/|_.__/   \__\__,_|_|_|\___/|_|
  |__/
```

# job-tailor

A Claude Code plugin that takes a job offer and a master CV, then generates a complete, tailored application pack. Every claim in the output is grounded in the source CV — nothing is invented.

## What it produces

| File | Format | Purpose |
|------|--------|---------|
| Tailored CV | DOCX + PDF | CV restructured to emphasise relevant experience |
| Motivation letter | DOCX | Full cover letter (3-4 paragraphs) |
| Short motivation letter | TXT | Concise version (500-750 chars) for online forms |
| LinkedIn messages | TXT | Personalised messages with real contact names and LinkedIn URLs |
| Interview prep | HTML | Fit score, company context, anticipated questions, talking points |
| Run summary | JSON | Fit %, match counts, file paths |

Output folders are prefixed with the fit level: `very_good-`, `good-`, `medium-`, or `low-`.

## Hard rule

**Never invent experience, skills, certifications, achievements, or responsibilities that are not in the source CV.** Gaps are handled honestly — de-emphasised, bridged with adjacent experience, or acknowledged as a learning trajectory.

## How it works

The skill runs a ~10-step pipeline (step numbers as in `SKILL.md`):

- **Steps 0–2.5 — CV preparation** (shared `job-prep-cv` sub-skill) — preflight (dependencies, history DB, customization, output folder); on a cache miss, read the master CV (`cli.py read-cv`), extract the fact base, verify it against the CV, and cache it by file hash
- **Step 3 — Analyse job offer** — extract requirements, skills, signals, detect language, flag job boards posting for a real client
- **Step 3.5 — Duplicate & history check** — query the SQLite database (URL match, company+title match, 80% skill overlap) and the blacklist
- **Step 3.6 — Research company** — web search for size, culture, tech stack, key contacts
- **Step 3.9 — Merged fact base** — `claims_guard.py merge` writes the per-run `cv_fact_base_merged.json` (CV + addendum + skill calibration + familiar-only skills); every later step reads it
- **Step 4 — Match/gap analysis** — requirement-by-requirement matrix, fit score. Below 50% = stop
- **Step 5 — Tailor CV** — restructure emphasis based on match analysis and company size (`prompts/tailor_cv.md` + the shared `prompts/cv_rules.md`)
- **Steps 6, 7 — Letter + short letter, LinkedIn messages** (two parallel subagents)
- **Step 8 — Interview prep**
- **Step 9 — Generate output files** — `cli.py regenerate-outputs`: CV rendered from a DOCX template via `docxtpl`; letters, LinkedIn, interview prep via Python scripts. The same command rebuilds a pack later
- **Step 10 — Record in database** — store for future duplicate detection and reporting

After writing each intermediate file the skill runs `cli.py gate <stage>` — one command that runs every deterministic check for that stage (schema, match recount and grounding, forbidden title labels, and the claims check that blocks over-claimed skills and unsourced wording in the CV, letters and LinkedIn messages) and reports all failures at once. It never continues past a failing gate.

## Job history database

Applications are tracked in `resources/job_history.db` (SQLite). This enables:

- **Duplicate detection** — prevents reprocessing the same job (matches by URL, company+title, or 80% skill overlap)
- **Re-application context** — surfaces previous applications to the same company
- **Status tracking** — track each application through: `generated` > `applied` > `interview` > `offer` / `rejected`
- **Company blacklist/whitelist** — block or prioritise specific companies
- **Reporting** — stats by fit level, status, domain, skill gap trends
- **CSV export** — dump all applications for external use

### Related commands

- `/job-status` — update application status, manage company lists
- `/job-stats` — dashboard, reports, skill trends, CSV export

## Folder structure

```
job-application-tailor/
├── SKILL.md                    # Main skill instructions (read by Claude)
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── config/
│   ├── settings.default.yaml   # Formatting, fit thresholds, behaviour flags (override in <user-data-dir>/settings.yaml)
│   ├── naming_rules.yaml       # Output filename patterns (FR/EN)
│   └── languages.yaml          # Section labels by language
├── prompts/
│   ├── extract_cv_data.md      # CV fact base extraction
│   ├── analyze_job_offer.md    # Job offer analysis
│   ├── match_analysis.md       # Requirement-by-requirement matching
│   ├── cv_rules.md             # CV rules shared by the offer and cold flows
│   ├── tailor_cv.md            # Offer-flow CV tailoring (loads cv_rules.md)
│   ├── generate_motivation_letter.md
│   ├── generate_short_letter.md
│   ├── generate_linkedin_message.md
│   └── generate_interview_prep.md
├── schemas/                    # JSON Schema validation for every intermediate file
│   ├── cv_fact_base.schema.json
│   ├── job_offer_analysis.schema.json
│   ├── match_analysis.schema.json
│   ├── tailored_cv.schema.json
│   ├── letter.schema.json
│   └── linkedin.schema.json
├── scripts/
│   ├── generate_outputs.py     # DOCX/PDF/TXT/HTML generation (driven by `cli.py regenerate-outputs`)
│   ├── docx_generator.py       # CV (template-based) and letter DOCX generation
│   ├── create_cv_template.py   # Generates the CV .docx templates (run once or to refresh design)
│   ├── validate.py             # JSON schema validation
│   ├── claims_guard.py         # Per-run merged fact base + anti-exaggeration check on generated material
│   ├── common.py               # Shared utilities (caching, naming, fit levels)
│   ├── job_history_db.py       # SQLite database for application tracking
│   ├── backfill_history.py     # Import existing output folders into database
│   ├── cli.py                  # Operational CLI (gate, regenerate-outputs, record-application, list, update-status, stats, …)
│   ├── commands/               # cli.py subcommand registry (gate.py = the per-stage checks)
│   ├── gen_cli_reference.py    # Auto-generates references/cli.md from cli.py argparse
│   └── lint_cli_usage.py       # Lints markdown for stale cli.py invocations
├── templates/
│   ├── cv_template_fr.docx     # French CV template (generated by create_cv_template.py)
│   ├── cv_template_en.docx     # English CV template (generated by create_cv_template.py)
│   └── interview_prep_template.md
└── references/
    ├── commands.md             # Exact bash commands for every operation
    ├── cli.md                  # Auto-generated: every cli.py subcommand signature (do not edit)
    └── troubleshooting.md      # DB salvage, PDF converters, subagent permissions, fact-base verification
```

### CLI reference & drift protection

`cli.py` is the operational entry point for the history database (used by `/job-status`, `/job-stats`, the tailoring pipeline's record-application step, and friends). Its argparse parser is the single source of truth — never compose flags from convention.

- **`references/cli.md`** is auto-generated from `cli.py`. Read it before composing any subcommand, or run `python scripts/cli.py <subcommand> --help`.
- **`scripts/gen_cli_reference.py`** regenerates `references/cli.md`. The `--check` flag exits non-zero on drift.
- **`scripts/lint_cli_usage.py`** scans markdown for `cli.py <subcommand>` invocations in fenced code blocks and verifies every `--flag` exists for that subcommand.
- A repo-level pre-commit hook (`.githooks/pre-commit`) regenerates the reference when `cli.py` is staged and lints staged `*.md` files. One-time setup: `git config core.hooksPath .githooks`.

## Project-level layout

The skill expects this structure in the project root:

```
project/
├── resources/
│   ├── MASTER_CV.docx          # Your source CV
│   ├── cv_fact_base.json       # Cached extraction (auto-managed)
│   ├── .cv_hash                # Cache key (auto-managed)
│   └── job_history.db          # Application history database (auto-managed)
├── output/
│   ├── very_good-23032026-Job-Title-Company/
│   │   ├── CV_Name_Title.docx
│   │   ├── CV_Name_Title.pdf
│   │   ├── Lettre_de_motivation_Name_Title.docx
│   │   ├── Lettre_courte_Name_Title.txt
│   │   ├── LinkedIn_message_Name_Title.txt
│   │   ├── Interview_prep_Name_Title.html
│   │   ├── run_summary.json
│   │   └── _prep/              # Intermediate JSON files
│   └── ...
└── .claude/skills/job-application-tailor/   # This skill
```

## Dependencies

```
python-docx>=1.1.2
docxtpl>=0.18.0
pyyaml>=6.0.2
jsonschema>=4.21.0
docx2pdf>=0.1.8
```

Install with: `pip install -r .claude/skills/job-application-tailor/requirements.txt`

## Usage

Invoke via Claude Code:

```
/job-application-tailor https://example.com/job-posting
```

Or paste a job description directly:

```
/job-application-tailor <paste job description text>
```

The skill auto-detects language (FR/EN) from the job offer and generates all output in the matching language.

## Fit levels

| Level | Threshold | What happens |
|-------|-----------|-------------|
| very_good | 85%+ | Full pack generated |
| good | 70-84% | Full pack generated |
| medium | 50-69% | Full pack generated |
| low | <50% | **Stops after match analysis** — no CV/letter generated |

## CV template

CVs are generated from a pre-styled DOCX template using [`docxtpl`](https://docxtpl.readthedocs.io/) (Jinja2 inside Word). The template defines all visual formatting — fonts, colours, spacing, section borders — while the generator fills in the data.

**Template design:**
- ATS-compliant: single-column, Calibri font, no tables/text boxes/images
- Centered header block: Name (19pt blue) → Title (16pt blue) → Tagline (10.5pt italic subtle gray, intentionally subtler than the title) → Contact (11pt dark gray, centered)
- Contact line auto-splits into two centered paragraphs when it has 4+ pipe-separated items, so long contact strings never wrap mid-item at the page edge
- Section layout — French: Profil professionnel → Compétences → Expérience professionnelle → Formation → Langues; English: Summary → Skills → Professional Experience → Education → Languages
- Section headings 14pt bold blue (`#1F4E79`) with a thin bottom border
- Each experience entry renders as: `Role` on its own bold line, then `Company | Location | Month YYYY – Month YYYY` on a 10pt italic gray `MetaStyle` line below; the two are glued with `keep_with_next` so Word can't orphan a role header at a page break
- Clickable email and LinkedIn hyperlinks in the contact line
- Compact spacing optimised for 2-page CVs

**Templates live in** `templates/cv_template_fr.docx` and `templates/cv_template_en.docx`.

**To customise the design:**
1. Edit `scripts/create_cv_template.py` (fonts, colours, spacing, borders)
2. Re-run it: `python scripts/create_cv_template.py`
3. No changes to the generator needed

Alternatively, open a generated template directly in Word, adjust formatting visually, and save — the Jinja2 tags survive as literal text.
