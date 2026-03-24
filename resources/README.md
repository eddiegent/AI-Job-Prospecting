# Resources

Place your master CV here as a `.docx` file named `MASTER_CV.docx`.

This is the source document that the skill extracts from and tailors for each application. It should contain your complete, unabridged CV — the skill handles trimming and emphasis.

## Auto-generated files (do not edit)

These files are created and managed by the skill:

| File | Purpose |
|------|---------|
| `cv_fact_base.json` | Structured extraction of your CV (cached) |
| `.cv_hash` | SHA-256 hash to detect CV changes |
| `job_history.db` | SQLite database tracking all processed applications |

## First-time setup

1. Save your CV as `MASTER_CV.docx` in this folder
2. Run `/job-application-tailor` with a job offer — the skill handles the rest
