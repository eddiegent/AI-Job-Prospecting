# Changelog

## [1.1.0] - 2026-04-09

### Changed
- **Template-based CV generation** — CVs are now rendered from a pre-styled DOCX template (`docxtpl`) instead of being built programmatically. All formatting (fonts, colours, spacing, borders) lives in the template file, not in code.
- **ATS-compliant design** — single-column layout, Calibri font, paragraph borders (no tables/text boxes/images), standard French section order
- **Visual improvements** — blue section heading borders, compact contact line, optimised spacing for 2-page fit

### Added
- `scripts/create_cv_template.py` — generates the CV DOCX templates (run once or to refresh design)
- `templates/cv_template_fr.docx` / `cv_template_en.docx` — pre-styled CV templates with Jinja2 tags
- `docxtpl>=0.18.0` dependency

### Fixed
- **CV tailoring prompt** — title/headline must now stay grounded in the master CV's identity, not be replaced with job offer language (e.g. "Backend" when the CV says "Services & Intégration")
- **Skill section preservation** — dedicated sections from the master CV (e.g. "Développement assisté par IA") can no longer be dropped during tailoring
- **Spaces-in-paths bug** — satellite skills (`/job-status`, `/job-stats`) no longer use `$CLI` variable pattern that broke with paths containing spaces; all commands now use inline `python scripts/cli.py --db "$DB_PATH"` with proper quoting

### Notes
- The `generate_cv_docx()` function signature is unchanged — no changes needed in calling code
- To customise the CV design: edit `create_cv_template.py` and re-run, or open the template in Word directly

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
