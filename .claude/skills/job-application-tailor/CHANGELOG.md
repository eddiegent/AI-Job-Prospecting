# Changelog

## [Unreleased] - 2026-05-07

### Added — CLI signature drift protection
- **`scripts/gen_cli_reference.py`** — auto-generates `references/cli.md` from the `cli.py` argparse parser. Imports `build_parser()` directly so the reference is always in lockstep with the source. Output is byte-stable (alphabetised, no timestamps). `--check` flag exits non-zero when the on-disk file would change, used by the pre-commit hook to detect drift.
- **`scripts/lint_cli_usage.py`** — scans markdown for `python … cli.py … <subcommand>` invocations inside fenced code blocks and verifies every `--flag` exists for that subcommand. Stitches backslash line continuations. Skips prose mentions outside code fences and placeholder syntax (`<subcommand>`). Catches the failure mode where docs reference flags that were renamed, removed, or never existed (e.g. `update-status --id 50 --status applied` when the real signature is `update-status <id> <status>`).
- **`.githooks/pre-commit`** — repo-level hook that regenerates `references/cli.md` when `scripts/cli.py` is staged, lints staged `*.md` files, and verifies the reference is in sync via `--check`. POSIX shell so it works under Git for Windows' bash. Auto-detects `python` / `py` / `python3`. One-time install: `git config core.hooksPath .githooks`.
- **`references/cli.md`** — auto-generated reference covering all 17 subcommands. Each section: signature, args table (positional / required / optional / flag), and choices/defaults pulled from argparse. Marked do-not-edit at the top.
- **Cross-link + routing rules**: `job-stats/SKILL.md` and `job-status/SKILL.md` now point to `references/cli.md` as the authoritative signature reference; `job-stats/SKILL.md` adds a routing rule that status mutations belong to `/job-status`.
- **CLAUDE.md** documents the system + hook setup; SETUP.md adds the one-line `git config core.hooksPath .githooks` step for fresh clones.

### Why
Three incidents in three weeks, same root cause: composing a CLI/SQL/Python invocation from convention rather than reading the actual signature. Memory entries reminded me to check, but only reactively — by the time I'd composed the call, I'd already committed to a syntax. The fix moves the canonical signatures into a single auto-generated file (so the right answer is one Read away) and adds a pre-commit linter so any documented flag that doesn't exist fails the commit.

## [1.9.0] - 2026-05-07

### Added — `record-application` CLI wrapper
- **`scripts/cli.py record-application <output-dir-or-id>`**. Step 10 was the last DB-touching step still doing inline Python (`db.add_application(**kwargs)` composed by hand from the offer JSON + match summary + folder prefix), and it failed exactly the way every other inline-DB step has historically failed — wrong kwarg names composed from intuition. The new subcommand reads the appropriate `_prep/` artefacts, derives `fit_level` from the folder prefix, and constructs the kwargs dict in one place. Auto-detects offer vs. cold flow from the folder prefix (`cold-…` → cold), with `--source` available as an explicit override. Flags: `--url` (override `source_url` when the offer JSON / company profile lacks one), `--language` (cold-flow language code, default `fr` — the offer flow reads `detected_language` from `job_offer_analysis.json` directly), `--dry-run` (print kwargs JSON, no DB write), and integer-id resolution against the DB. SKILL.md Step 10 (offer + cold) and `references/commands.md § Record Application` collapse to a single one-line invocation.
- **Aggregator URL probe in Step 3** (`references/commands.md § URL Probe`). Lesjeudis returns 403 on automated requests; WebFetch consumed a round-trip before the manual-paste fallback kicked in. A 5 s HEAD probe with `Mozilla/5.0` UA fails fast on `401/403/429/451` so the fallback fires immediately. SKILL.md Step 3 invokes the probe before WebFetch.
- **Extended `aggregators.known_platforms`** with `Lesjeudis`, `RegionsJob`, `Cadremploi`, `Choose Your Boss`, `Talent.io`. The `matched_aggregator` regex is case-insensitive with word boundaries, so "lesjeudis.com posting" resolves to `Lesjeudis` and "Talent.io Sourcing" resolves to `Talent.io`.
- **Compound-phrase rule in `prompts/match_analysis.md`**. Pre-empts the false-direct class the runtime grounding check caught during the Speechify run — comma-list concept phrases like `"OOP, design patterns, data structures, algorithms"` read as soft-skill prose but contain tech-shaped acronyms, so the existing "Direct ≠ partial" rule (built around `"C# / Kubernetes"`) didn't fire. New bullet applies the same all-or-nothing grounding rule to comma-lists. Belt-and-braces — `check_match_grounding.py` is still the runtime mechanism.

### Tests
- 12 new tests for `record-application`: offer-flow happy path; offer-flow without match analysis (fit columns NULL); offer-flow `low` fit fallback when no known prefix; `--url` override; cold-flow happy path (`source='cold'`, snapshot round-trips, `fit_*`/`job_skills` empty); cold `--language` override; `--dry-run` (no DB write); `--source offer` override on a cold-prefixed folder; missing `_prep/` files exit 2 with a clean error; missing `selected_role.json` likewise; integer-id resolution writes a new row using the seed row's `output_folder`; unknown integer id exits 1.
- Tailor full suite: **163 pass / 2 skip** (was 151).

## [1.8.0] - 2026-05-06

### Added — false-direct match guard
- **`scripts/check_match_grounding.py` + `scripts/_grounding_common.py`**. Step 4's match analysis would occasionally mark JD requirements as `match_type: "direct"` without any evidence in the fact base (e.g. JD lists Kubernetes → LLM marks it direct → `overall_fit_pct` inflates → role passes the 50% gate → tailored CV inherits the unfounded claim). The new deterministic post-check rejects any `direct` match whose tech tokens appear in the JD but not in `cv_fact_base.{technologies, skills, methodologies}` or `experience[*].details`. SKILL.md Step 4 invokes the script after the schema validate; non-zero exit means regenerate Step 4 with the offending requirements surfaced to the prompt. Soft-skill direct-match issues become non-blocking warnings (cross-language matching of plain phrases is too unreliable to gate on); tech tokens (acronyms, CamelCase, `.`/`#`/`/`/`+`-shaped, or in the synonym map) block. `_grounding_common.py` is shared with `check_role_grounding.py` so the synonym map and tokenizer can never drift between the offer and cold flows.
- **Prompt-level guardrails in `prompts/match_analysis.md`** — adds a "No false directs" rule with concrete failures to avoid (Kubernetes when fact base only has Docker; Entity Framework when fact base only has Dapper) and a "Direct ≠ partial" rule for compound requirements like "C# / Kubernetes" (all tokens must be grounded for `direct`; otherwise downgrade with an explicit `notes` explanation).
- **JD-stack contagion check in `prompts/tailor_cv.md`** — Step-5 self-check #5 forbids promoting a tech named in `job_offer_analysis.{required_skills, technologies, ats_keywords}` into `summary_paragraphs`, `tagline`, `skills_sections`, or `experience[*].bullets` unless that tech (or close synonym) is in `cv_fact_base` or `experience[*].details`. Last line of defence after the Step-4 grounding check.

### Tests
- 14 new tests for `check_match_grounding.py`: clean directs; transferable with notes; false-direct Kubernetes; false-direct Entity Framework; compound-requirement partial grounding (only ungrounded token flagged); soft-skill direct warns instead of blocks; soft-skill grounded via `skills` array passes; tech grounded via prose passes; synonym match (`dotnet` ↔ `.NET`); transferable without notes warns; versioned tech grounded by unversioned fact base; tech-shape gate (acronym, CamelCase) blocks when ungrounded; gap matches never flagged.
- Tailor full suite: **151 pass / 2 skip** (was 135).

## [1.7.0] - 2026-05-04

### Added — determinism wins
- **`scripts/recount_match_summary.py` + `common.recount_match_summary()`** (D1). The match-analysis step's LLM authors both `matches[]` and `match_summary` and the two regularly drift (counts and `overall_fit_pct` get miscounted; the recount-and-correct loop was a recurring tax on every run). The summary is now computed deterministically from the matches array. SKILL.md Step 4 invokes the script after writing `match_analysis.json` and before validation. Idempotent — `OK (already correct)` when the LLM happened to produce consistent figures, `Updated match_summary: <before> -> <after>` when it didn't. 7 unit tests, including a regression case for the real INGELINE 16/8/7=65% drift.
- **`common.auto_slug(job_title, company)`** (D2, public). Same algorithm `cli.py rename-application` was using locally. Centralised so the fit-time rename can also use it.
- **`scripts/preflight.py`** (D3) — one Python invocation that replaces four-to-five separate one-liners (deps check, master CV check with init fallback, DB init, customization load, output folder creation) and the cache-hot path of Steps 1/2/2.5 (read CV, copy cached fact base, verify). Prints a single JSON state blob the orchestrator parses. `status` field tells the orchestrator whether to continue (`ok`), do LLM extraction (`cache_stale`), surface onboarding (`first_run`), surface a blacklist hit (`blacklisted`), or stop on error. Forces `PYTHONIOENCODING=utf-8` in the verify_fact_base subprocess so non-ASCII output doesn't crash the decode on Windows. Resolves the project root via `git rev-parse` then `.git`/`.claude` markers, never via the legacy `resources/` path (the user-data path stays funnelled through `paths.py`).

### Changed — single-rename folder naming (D2)
- **`common.rename_folder_with_fit`** now accepts optional `job_title=` and `company=` kwargs. When supplied, the helper rebuilds the trailing slug via `auto_slug` at the same time as it adds the fit prefix, collapsing the historical "create folder with placeholder slug → fit-rename at Step 4 → optional `rename-application` later" dance into a single rename to the final `[fit_level]-[date]-[job_title-company]/` path. Backwards-compatible: the existing zero-kwarg call path (used by the cold flow) is unchanged. SKILL.md Step 4 and `references/commands.md § Folder Rename` both updated to pass the new kwargs.
- **`cli.py`** drops the local `_auto_slug` helper in favour of `common.auto_slug` (single source of truth for the slug algorithm).

### Tests
- 9 tests for `auto_slug` + `rename_folder_with_fit` covering the new single-rename path, the backward-compatible cold-flow path, and the no-double-prefix invariant.
- 7 tests for `recount_match_summary` covering basic counts, edge cases (only-direct, only-gaps, empty), unknown match_type defensiveness, the real-world INGELINE drift, and rounding.
- Tailor full suite: **135 pass / 2 skip** (was 117). Cold-prospect **17 pass** (unchanged).

## [1.6.1] - 2026-05-04

### Fixed
- **`rename-application` left stale old-slug deliverables in the folder.** When a rename triggered a slug change, `regenerate-outputs` wrote new-slug filenames but did not remove the pre-rename ones, so the folder ended up with two copies of every deliverable (CV, letter, LinkedIn, interview prep). New helper `scripts.common.delete_stale_slug_deliverables` is invoked before the regenerate step; it scans the folder root only (so `_prep/*.json` is never touched), matches `*_<old_slug>.<ext>`, and removes those files. No-op when the slug is unchanged or the rename was DB-only.
- **Bare `python -c` blocks that print non-ASCII** (paths with accents, em-dashes in messages) crashed on Windows with `UnicodeEncodeError` because `cp1252` is the default console codepage. Fixed three such blocks in `references/commands.md` and `job-cold-prospect/SKILL.md` by adding the `python -u -c` + `io.TextIOWrapper(..., encoding='utf-8')` preamble already used by other blocks. Pure-ASCII one-liners (e.g. `print('OK')`) were left as-is.

### Tests
- Added `tests/test_rename_cleanup.py` — 5 tests for `delete_stale_slug_deliverables` covering: removing top-level deliverables, leaving `_prep/` alone, no-op on slug match, no-op on empty old slug, and slugs with `.`/`#` chars.
- Full suite: tailor **117 pass / 2 skip** (was 112), cold-prospect **17 pass** (unchanged).

## [1.6.0] - 2026-05-04

### Changed
- **Steps 0–2.5 extracted to a shared `job-prep-cv` sub-skill.** The pre-flight, master-CV read, fact-base extract, and fact-base verification used to live verbatim in this `SKILL.md` and were referenced by `job-cold-prospect` via "follow tailor SKILL.md § Step X" pointers. They now live once at `.claude/skills/job-prep-cv/SKILL.md` (`disable-model-invocation: true`, orchestrators only — never user-facing). Both flows delegate to it via a single block that passes `$FLOW` (`offer` / `cold`), `$INPUT_SEED`, and an optional `$EARLY_BLACKLIST_NAME`. The sub-skill returns with `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR`, `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION` set and `$PREP_DIR/cv_fact_base.json` verified. Folder naming (`[date]-[slug]/` for offer, `cold-[date]-[slug]/` for cold) is the only flow-aware branch inside the sub-skill.
- **Shared infrastructure unchanged.** `scripts/`, `schemas/`, `config/`, and `references/commands.md` still live in this skill. `job-prep-cv` and `job-cold-prospect` both import via `$SKILL_BASE_TAILOR` — same pattern cold-prospect already used. No Python touched.

### Verified
- Full test suites green: tailor **112 pass / 2 skip**, cold-prospect **17 pass** — same as before the refactor (no behaviour change).

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
