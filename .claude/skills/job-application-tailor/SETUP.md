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
python -c "import docx, yaml, jsonschema; print('OK')"
```

## Step 2 — Add your master CV

Save your CV as a `.docx` file at:

```
resources/MASTER_CV.docx
```

This is the source document the skill reads from. Include everything — all roles, education, skills, certifications. The skill handles trimming and emphasis for each application.

If your CV has a different name, you can configure the filename keyword in `config/settings.yaml` under `behaviour.cv_filename_keyword`.

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

All settings live in `.claude/skills/job-application-tailor/config/settings.yaml`:

| Setting | Default | What it does |
|---------|---------|-------------|
| `default_language` | `auto` | Language detection (auto/fr/en) |
| `behaviour.skip_company_research` | `false` | Skip web research (faster) |
| `behaviour.dry_run` | `false` | Score only, no file generation |
| `paths.database` | `resources/job_history.db` | Where to store application history |
| `fit_levels.very_good` | `85` | Threshold for "very good" fit |
| `fit_levels.good` | `70` | Threshold for "good" fit |
| `fit_levels.medium` | `50` | Below this = "low", generation stops |

## Troubleshooting

**"No DOCX CV file found"** — make sure your CV is saved as `.docx` (not `.pdf` or `.doc`) in the `resources/` folder.

**No PDF generated** — install `docx2pdf` (`pip install docx2pdf`) and make sure Microsoft Word is installed. On macOS/Linux without Word, you'll get DOCX only.

**WebSearch fails** — the company research step needs web access. If you haven't granted permission, the skill skips it gracefully. You can also disable it permanently with `skip_company_research: true`.

**Validation errors** — the skill validates all intermediate JSON against schemas. If validation fails, it will show the specific error and re-generate. This is normal — it self-corrects.
