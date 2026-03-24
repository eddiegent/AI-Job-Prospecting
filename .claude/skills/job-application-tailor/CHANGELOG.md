# Changelog

## [1.0.0] - 2026-03-24

### Features
- **Tailored CV generation** — DOCX + PDF with professional styling matching the master CV
- **Motivation letter** — full cover letter (DOCX) grounded in CV evidence
- **Short motivation letter** — concise 500-750 character version (TXT) for online forms
- **LinkedIn messages** — personalised messages with real contact names from company research
- **Interview prep** — fit score, company context, anticipated questions, talking points (MD)
- **Match/gap analysis** — requirement-by-requirement matrix with fit scoring
- **Company research** — automated web search for company context and key contacts
- **CV caching** — SHA-256 hash-based caching of CV fact base extraction
- **Language detection** — auto-detects FR/EN from job offer, generates all output in matching language
- **Fit-level gating** — stops at match analysis if fit is below 50%

### Job History Database
- **SQLite tracking** — all processed applications stored in `resources/job_history.db`
- **Duplicate detection** — three-layer matching (URL, company+title, 80% skill overlap)
- **Re-application context** — surfaces previous applications to the same company
- **Status tracking** — generated / applied / rejected / interview / offer
- **Company blacklist/whitelist** — block or prioritise specific companies
- **CSV export** — dump all applications for external use
- **Backfill script** — import existing output folders into the database

### Satellite Skills
- **`/job-status`** — update application status, manage company lists
- **`/job-stats`** — dashboard, reports by fit/status/domain, skill gap trends, CSV export

### Configuration
- Configurable fit thresholds, formatting, naming rules, language labels
- Configurable database path (`paths.database`)
- Optional company research (`behaviour.skip_company_research`)
- Dry-run mode (`behaviour.dry_run`) — fit score only, no file generation
- Parallel subagent execution for letter/LinkedIn/interview prep

### Infrastructure
- JSON Schema validation for all intermediate files
- Python DOCX generator with professional styling
- Plugin manifest (`plugin.json`)
- Anonymised example output files
- FR/EN interview prep templates
