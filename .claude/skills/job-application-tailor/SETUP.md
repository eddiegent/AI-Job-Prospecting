# First-Time Setup

Get up and running in 5 minutes.

## Prerequisites

- **Claude Code** installed and working
- **Python 3.10+** installed
- **Microsoft Word** (optional, for PDF conversion — works without it, you just won't get PDFs)

## Step 1 — Install Python dependencies

```bash
pip install -r .claude/skills/job-application-tailor/requirements.txt
```

Verify it worked:
```bash
python -c "import docx, docxtpl, yaml, jsonschema; print('OK')"
```

If you cloned the repo (rather than installing the plugin bundle), enable the pre-commit hook that keeps `references/cli.md` in sync with `cli.py` and lints docs for stale invocations:

```bash
git config core.hooksPath .githooks
```

## Step 2 — Add your master CV

Save your CV as a `.docx` file at:

```
resources/MASTER_CV.docx
```

This is the source document the skill reads from. Include everything — all roles, education, skills, certifications. The skill handles trimming and emphasis for each application.

The file must be named exactly `MASTER_CV.docx`.

## Step 3 — Run your first application

```
/job-application-tailor https://example.com/some-job-posting
```

Or paste a job description directly:

```
/job-application-tailor [paste the full job description here]
```

The skill will:
1. Extract and cache your CV data (first run only — cached for future runs)
2. Analyse the job offer
3. Score your fit (and stop if below 50%)
4. Generate a tailored CV, cover letters, LinkedIn messages, and interview prep
5. Save everything to `output/[fit_level]-[date]-[job-slug]/`

## Step 4 — Track your applications

After generating packs, use these commands:

```
/job-status attineos applied      # mark as applied
/job-status #3 interview          # mark by ID
/job-stats                        # see your dashboard
/job-stats export                 # export to CSV
```

## Configuration

Defaults live in `.claude/skills/job-application-tailor/config/settings.default.yaml`. To change one, put just that key in an optional `settings.yaml` in your user data directory — it is applied on top of the defaults:

| Setting | Default | What it does |
|---------|---------|-------------|
| `behaviour.skip_company_research` | `false` | Skip web research (faster) |
| `behaviour.dry_run` | `false` | Score only, no file generation |
| `behaviour.experience_compression_cutoff_year` | `2005` | Roles ending before this year may be consolidated into one "Earlier experience" line (`null` disables) |
| `fit_levels.very_good` | `85` | Threshold for "very good" fit |
| `fit_levels.good` | `70` | Threshold for "good" fit |
| `fit_levels.medium` | `50` | Below this = "low", generation stops |

The output language is detected from the job offer. To force one, set `default_language: fr` or `en` in `user_prefs.yaml` (default `auto`). The history database location is resolved automatically (`JOB_TAILOR_HOME`, then the repo's legacy `resources/` folder, then the OS data directory); the CLI's `--db` flag targets another file.

## Troubleshooting

**"CV template not found"** — the CV template needs to be generated once. Run: `python .claude/skills/job-application-tailor/scripts/create_cv_template.py`

**"No DOCX CV file found"** — make sure your CV is saved as `.docx` (not `.pdf` or `.doc`) in the `resources/` folder.

**No PDF generated** — install `docx2pdf` (`pip install docx2pdf`) and make sure Microsoft Word is installed. On macOS/Linux without Word, you'll get DOCX only.

**WebSearch fails** — the company research step needs web access. If you haven't granted permission, the skill skips it gracefully. You can also disable it permanently with `skip_company_research: true`.

**Gate failures** — after each intermediate file the skill runs `cli.py gate <stage>`, which validates the JSON against its schema and runs that stage's truthfulness checks. If a gate fails, it shows every problem at once, fixes the generated file and re-runs the gate. This is normal — it self-corrects.

For anything else (database errors, no PDF, DOCX build errors, subagent permission prompts), see `references/troubleshooting.md`.
