# Changelog

## [1.5.0] - 2026-04-22

### Changed
- **`prompts/tailor_cv.md` — CV truthfulness guardrails.** Added three sections and extended the Forbidden list to close gaps caught on a real run (K8s/OpenShift flagged as `gap` in the match analysis were still bridged in the CV summary as "en apprentissage", and `match_analysis.notes` qualifiers like "Docker used for CI/CD builds, not production orchestration" were contradicted by CV phrasing):
  - **§ Summary sourcing** — every clause in `summary_paragraphs` and `tagline` must be traceable to `cv_fact_base.summary`, `experience[*].details`, `transition_signals`, or addendum. Untraceable clauses must be dropped.
  - **§ Gap honesty** — `match_analysis` rows with `match_type: "gap"` cannot be bridged with learning-language unless the technology is named in `transition_signals`. Qualifiers in `match_analysis.notes` must be honoured verbatim.
  - **§ Final self-check** — four pre-output checks (gap, qualifier, summary traceability, adjective audit) the model runs before returning JSON.
  - **Forbidden list additions** — injecting adjectives not in the fact base, relabeling experience to mirror job-offer vocabulary, claiming active learning for gap tech, contradicting `match_analysis.notes`.

### Fixed
- **`cmd_regenerate_outputs` filename slug mismatch.** `regenerate-outputs` passed the raw `job_title` from `job_offer_analysis.json` through to `generate_outputs.py`, which re-sanitised it via `slug_for_filename()` and produced a UTF-8 slug (e.g. `Ingénieur_en_développement_NET_confirmé`) that didn't match the folder's original ASCII slug (e.g. `Ingenieur-Developpement-NET-Cardiweb`). The result was a duplicate file set alongside the originals on every regenerate. Fix extracts the existing slug from the folder name via `_split_folder_prefix()` and reuses it for filename generation (`slug_for_filename` is idempotent on its own output, so downstream sanitisation is a no-op).

## [1.4.0] - 2026-04-20

### Added
- **Schema v2 on `job_history.db`** — new `applications.source` column (`'offer'` default, `'cold'` for speculative applications from the `job-cold-prospect` skill) and `applications.company_profile_snapshot` column (compact JSON subset of the researched company profile). Migration runs automatically on first open via `ALTER TABLE ADD COLUMN`; legacy rows default to `source='offer'` with no backfill script required. `schema_version` advances to 2 only after the upgrade succeeds.
- **`add_application()` accepts `source` + `company_profile_snapshot`** keyword arguments. `source` is validated against `{'offer', 'cold'}`. Defaults keep the offer-flow call sites unchanged.
- **`_upgrade_schema(from_version)`** helper on `JobHistoryDB` — extension point for future incremental migrations. v1→v2 is the first clause.

### Verified
- Existing 104-test suite still green.
- Ad-hoc round-trip test against a hand-rolled v1 DB confirms migration adds both columns, leaves legacy rows with `source='offer'`, accepts cold inserts, and rejects unknown `source` values.

## [1.3.0] - 2026-04-17

### Added
- **Optional LinkedIn + interview inputs in `generate_outputs.py`** — `--linkedin-json` and `--interview-markdown` are now optional (were required). Lets sibling skills like `job-cold-prospect` produce CV + letter-only packs without stubbing unused artefacts. Run summary correctly reports `null` for absent files. The standard tailor-skill path is unchanged: it still passes both flags and gets the full 5-file pack.
- **Optional `letter_type` field in `letter.schema.json`** — enum `standard | speculative`. Backwards-compatible (existing tailor letters omit the field and validate fine). Lets the cold-prospect skill tag speculative letters for downstream audit.

## [1.2.0] - 2026-04-17

### Breaking
- **Schema rename** — `experience[]` fields in `tailored_cv.schema.json` renamed `company_role_line` → `role_line`, `date_line` → `metadata_line`. Semantics changed: `role_line` carries only the role title; `metadata_line` carries `"Company | Location | Month YYYY – Month YYYY"`. Old tailored CV JSON files (pre-1.2.0) no longer validate — `regenerate-outputs` on a legacy `_prep/` folder will fail until the JSON is migrated.

### Changed
- **Centered header block** — Name (19pt blue), Title (16pt blue), Tagline (10.5pt italic gray, intentionally subtler), Contact (11pt dark gray) — all centered
- **Date format standardised** — every date in the experience section now uses `Month YYYY – Month YYYY` with full month names and an en-dash
- **Summary section heading** — EN label renamed `Professional Profile` → `Summary` for cleaner ATS keyword matching (FR stays `Profil professionnel`)
- **Section headings** — bumped 12pt → 14pt, matching ATS-friendly hierarchy (body 11pt, headings 14pt, name 19pt)
- **Contact line auto-split** — when the contact string has 4+ pipe-separated items, the generator now emits two centered lines (e.g. `Email | Tel` / `LinkedIn | Location`) so long contact lines no longer wrap awkwardly at the page edge
- **Filename slug** — `slug_for_filename()` now strips `()[]{}.` so job titles like `Backend Developer (.Net Core)` produce `Backend_Developer_Net_Core` in output filenames instead of `Backend_Developer_(.Net_Core)`

### Added
- `TitleStyle`, `MetaStyle` paragraph styles in `create_cv_template.py`
- `_set_keep_with_next()` helper — Role and Metadata lines are glued to the next paragraph so Word can't orphan a role header at a page break
- `_split_contact_lines()` helper in `docx_generator.py` — mid-pipe split for long contact strings

### Fixed
- **Ampersand bug in docxtpl render** — rendered text was silently dropping `&` characters (and surrounding spaces) because docxtpl's default Jinja environment lacks XML autoescape. `generate_cv_docx()` now passes a `jinja_env=Environment(autoescape=True)` into `tpl.render()`. Text like `R&D Engineer`, `Platforms & Frameworks`, `JFC Informatique & Média` now renders correctly.

### Migration
- If you have pre-1.2.0 `_prep/tailored_cv.json` files you want to regenerate, rename the fields per the schema rename above. The tailoring prompt (`prompts/tailor_cv.md`) now documents the new contract.

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
