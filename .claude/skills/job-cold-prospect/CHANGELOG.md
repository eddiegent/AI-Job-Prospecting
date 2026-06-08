# Changelog

## 0.10.0 — 2026-05-14

**Cold-flow output folder rebuilds its slug from the canonical company name.**

- Preflight builds the initial folder slug from `$INPUT_SEED` — fine when the user passes a clean company name, but unreadable when the input is a URL (e.g. `https://www.linkedin.com/company/francebillet/` produced `cold-14052026-https-wwwlinkedincom-company-francebillet/`). The rename used to be deferred indefinitely — the `cold-` prefix was treated as canonical and the placeholder slug shipped through to the dossier, `run_summary.json`, and the history-DB row.
- Step 3 now adds a slug-canonicalisation block right after the blacklist re-check, before any downstream artefact is written. It calls the new `scripts/common.py::rename_cold_folder_with_canonical_name` helper, which detects the `cold-DDMMYYYY-` prefix, rebuilds the trailing slug from `company_profile.company_name` via the existing `auto_slug` utility, and renames the folder atomically. The orchestrator reassigns `$OUTPUT_DIR` and `$PREP_DIR` to the new path and continues — `selected_role.json`, the tailored CV, the letters, LinkedIn, the dossier, the DOCX/PDF outputs, the run summary, and the DB insert all land in the renamed folder. No after-the-fact path fix-up needed.
- Idempotent: re-running Step 3 (or running it after a manual rename) returns the same path back. Collision guard: if the target folder already exists from a previous run on the same company, the helper raises `FileExistsError` and surfaces the conflict to the user rather than silently overwriting.

**Tests.**
- 4 new tests in `tests/test_folder_naming.py` (tailor skill, where `common.py` lives): the LinkedIn-URL → canonical-name rename, idempotency when the slug already matches, collision refusal, and the defensive no-op when the input folder lacks a `cold-` prefix. Full folder-naming suite: **13 pass** (was 9).

**Docs.**
- `job-cold-prospect/SKILL.md` Step 3 documents the rename block with the exact shell snippet to capture and reassign `$OUTPUT_DIR` / `$PREP_DIR`.
- `job-prep-cv/SKILL.md` line 79 — flipped the "the cold flow's `cold-` prefix is the canonical naming and is not changed later" sentence; the slug is now described as a placeholder in both flows, with the rename point spelled out for each.

## 0.9.1 — 2026-05-07

**Step 10 collapses to the shared `record-application` wrapper.**

- The cold-flow Step 10 used to compose two inline Python blocks — one to build the company profile snapshot, one to call `db.add_application(...)` with `source='cold'` and a literal `'<fr|en>'` placeholder for `detected_language`. Both are gone; SKILL.md Step 10 is now `python scripts/cli.py … record-application "$OUTPUT_DIR" --language "<fr|en>"` and the wrapper (shipped in tailor 1.9.0) reads `selected_role.json` + `company_profile.json`, builds the snapshot subset, and inserts in a single deterministic call. Removes the same class of "composed-from-memory" failures the offer flow was hit by during the Speechify run.

## 0.9.0 — 2026-05-06

**Stack-mirroring guard for the role inference step.**

- The 4a prompt (`prompts/infer_target_role.md`) was occasionally letting techs from `company_profile.tech_stack_hints` leak into candidate-side fields (`emphasis_areas`, rationale prose) without those techs being in `cv_fact_base`. Concrete failure: agap2's listing requires Entity Framework; the candidate has SQL Server + Dapper but no EF; the candidate's `emphasis_areas` ended up reading `"SQL Server / Entity Framework"`, and the rationale quoted the company's full tech list verbatim — which implies competence the candidate doesn't have, and would propagate into the CV, letters, LinkedIn, and dossier downstream.
- Two prompt-level guardrails added: **No stack mirroring in candidate-side fields** (a tech that appears only in the company hints must not show up as a candidate strength), and **Don't quote the company's stack verbatim in rationale** (the "stack listée — A, B, C, D, E — recouvre ligne pour ligne" pattern is an attractive nuisance that invites copying the company's full tech list).
- Deterministic post-check `scripts/check_role_grounding.py` (lives in the sibling tailor skill so both flows share the synonym map / tokenizer in `_grounding_common.py`). Runs twice in `SKILL.md`: once after Step 4a candidate generation, and once after Step 4b user pick / override (a free-form override can reintroduce a leak after the first check). Each run inspects `emphasis_areas` token-by-token and the rationale prose; flags any tech that is in `tech_stack_hints` and absent from `cv_fact_base.{technologies, skills, methodologies}` or `experience[*].details`. Domain phrases like "Architecture de services" never false-positive because they don't appear in `tech_stack_hints`.
- Tailor skill ships the symmetric guard at 1.8.0 (`check_match_grounding.py`) — different failure mode (false-direct match claims in the offer flow), same shared infrastructure.

**Tests.**
- 11 new tests for `check_role_grounding.py`: clean candidates pass; domain phrase isn't false-flagged; synonym matches (`dotnet` ↔ `.NET`); EF in `emphasis_areas` blocks; EF in rationale blocks; selected_role override leak blocks; user-override free-form leak blocks; Blazor in company hints but not fact base blocks; Blazor blocked previously now passes after fact-base addition; tech grounded via prose-only (experience details) passes; company with no `tech_stack_hints` is no-op.
- Cold-prospect full suite: **28 pass** (was 17). Tailor: **151 pass / 2 skip**.

## 0.8.1 — 2026-05-04

**Windows Unicode fixes in SKILL.md.**

- Two bare `python -c` blocks in `SKILL.md` (the company-name blacklist re-check in Step 3, and the forbidden-label post-check in Step 4b) printed non-ASCII content (em-dashes in messages, role titles with accents) and crashed under Windows' default `cp1252` console codepage with `UnicodeEncodeError`. Fixed by switching them to the `python -u -c` + `io.TextIOWrapper(..., encoding='utf-8')` preamble that the rest of the file already uses.
- No script changes in this skill. Tailor skill carries the matching `delete_stale_slug_deliverables` fix at 1.6.1 (`rename-application` no longer leaves duplicate pre-rename files in the folder).

## 0.8.0 — 2026-05-04

**Steps 0–2.5 delegated to a shared `job-prep-cv` sub-skill.**

- This skill no longer carries its own copy of the pre-flight + CV-prep prose. Steps 0–2.5 now live once at `.claude/skills/job-prep-cv/SKILL.md` (a `disable-model-invocation: true` sub-skill — orchestrators only, never user-facing). The cold flow invokes it with `$FLOW="cold"`, `$INPUT_SEED=$ARGUMENTS`, and `$EARLY_BLACKLIST_NAME=$ARGUMENTS` (the input name early-blacklist check the cold flow needs). The sub-skill returns with `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR`, `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION` set, and `$PREP_DIR/cv_fact_base.json` verified. The cold-flow-specific Steps 3–10 are unchanged.
- The output folder naming (`cold-[date]-[slug]/`) is now produced by `job-prep-cv` based on the `$FLOW` argument, but the on-disk naming convention is identical to before — cold packs still segment cleanly from offer packs in `output/`.
- Removes the verbatim "Follow tailor SKILL.md § Step X" stubs that previously linked back into the tailor skill. The new delegation block is ~10 lines instead of ~60.
- No prompt or schema changes. No Python touched. Tests still **17 pass** in this skill and **112 pass / 2 skip** in the tailor skill.

## 0.7.1 — 2026-04-22

**CV truthfulness guardrails (mirrored from tailor skill 1.5.0).**

- `prompts/tailor_cv_cold.md` picks up the same three sections the tailor skill added: **§ Summary sourcing** (every clause traceable to the fact base), **§ Honesty on technology claims** (inferred `company_profile.tech_stack_hints` are about the company, not the candidate — never reword bullets to echo a hint the candidate hasn't worked with; active-learning phrasing requires `cv_fact_base.transition_signals` to name the technology), and **§ Final self-check** (summary traceability, stack-hint check, learning-language check, adjective audit). Forbidden list also gains four items matching the tailor skill (adjective injection, vocabulary relabeling, unsupported active-learning claims, contradicting stack-hint scope).
- No runtime code changes in this skill — the fix lives entirely in the prompt. Sibling skill `job-application-tailor` ships the matching guardrails and the `regenerate-outputs` filename-slug fix at 1.5.0.

## 0.7.0 — 2026-04-20

**Phase G — Tests + docs. Skill is launch-ready.**

- Added `tests/` under the cold-prospect skill with 17 schema-validation tests covering positive and negative cases for `company_profile`, `role_candidates`, `selected_role`, plus backwards-compatibility + cold-extension behaviour on the shared `linkedin.schema.json`. Tests go through `scripts.validate.validate` so they exercise the exact code path `SKILL.md` uses.
- Added `tests/test_job_history_db_v2.py` to the tailor skill with 8 tests pinning the v1→v2 migration: legacy-row `source='offer'` preservation, cold-insert round-trip (including JSON snapshot), rejection of unknown `source` values, fresh-DB-direct-at-v2, reopen idempotency, and a half-migrated-state recovery case.
- README updated: status block reflects launch-ready Phases A–G, "What it produces" table maps to real filenames, new "Sample run" walkthrough and "Tests" section.
- Full test suite: tailor skill **112 pass / 2 skip** (was 104), cold-prospect skill **17 pass**. No regressions in the tailor flow.

## 0.6.0 — 2026-04-20

**Phase F — History DB integration.**

- Shared `job_history.db` schema bumped to v2. New columns on `applications`: `source TEXT NOT NULL DEFAULT 'offer'` (segments offer-flow from cold-flow rows) and `company_profile_snapshot TEXT` (compact JSON subset of `company_profile.json` for future dashboards). Added in `job-application-tailor/scripts/job_history_db.py` so both skills share the migration path.
- Migration is automatic on first open via `ALTER TABLE ADD COLUMN`. Legacy v1 rows default to `source='offer'` — no backfill script required. The `schema_version` row advances to 2 only after the upgrade succeeds.
- `add_application()` gained `source` (`'offer'` | `'cold'`, rejects anything else) and `company_profile_snapshot` keyword arguments. Defaults preserve offer-flow behaviour unchanged.
- `SKILL.md` Step 10 is now concrete: it builds a snapshot (company_name, canonical_url, industry, size_band, headcount, locations, mission_statement, research_gaps_count) and inserts the cold row with `source='cold'`, `status='generated'`, `job_title = selected_role.title`. `job_skills` is intentionally left empty for cold rows — no JD means no required-skill list. `fit_*` columns stay NULL.
- Verified with a v1-DB round-trip test: legacy row retains `source='offer'`, cold row round-trips correctly, and bad source values are rejected. Tailor skill's 104-test suite still green.
- `/job-cold-prospect <name>` now runs fully end-to-end including history recording. Follow-up in Phase G or later: update `job-stats` queries to optionally segment by `source`.

## 0.5.0 — 2026-04-20

**Phase E — LinkedIn outreach + company dossier.**

- Added `prompts/generate_linkedin_cold.md` — cold-flow LinkedIn messages targeting hiring managers / CTO / tech leads (not recruiters), two variants per contact (≤300-char connection request + ≤700-char post-acceptance direct message), hooks aligned with the motivation letter. Falls back to `[Prénom]` placeholder when `leadership[]` is empty.
- Added `prompts/generate_dossier_cold.md` — merged deliverable replacing the fit-score document. Nine sections: Quick reference, Company at a glance, Why you / why them (narrative angle of approach), Who to contact, Likely objections + answers, Conversation openers, Role-specific interview prep (STAR scaffolds), Transition narrative, Research gaps. Every company fact cites a source URL; inferred fields stay flagged as inferred.
- Extended the tailor skill's `schemas/linkedin.schema.json` with optional `outreach_type` (enum: `standard` | `cold`) and `target_role` fields. Backwards-compatible — existing offer-based LinkedIn JSONs omit both fields and still validate.
- `SKILL.md` Steps 7 and 8 are now concrete. Step 9 passes `--linkedin-json` through to `generate_outputs.py`; the dossier is written directly to `$OUTPUT_DIR/company_dossier.md` as a first-class deliverable (not via `--interview-markdown` — the cold flow has no interview-prep file, the dossier replaces it). Added an alignment check requiring the motivation-letter hook, LinkedIn connection-request opener, and dossier § 3 to reference the same company fact.
- `/job-cold-prospect <name>` now runs fully end-to-end: research → role pick → tailored CV → motivation letter + short letter → LinkedIn messages → company dossier.

## 0.4.0 — 2026-04-17

**Phase D — CV tailoring + speculative letters.**

- Added `prompts/tailor_cv_cold.md` — anchors tailoring on `selected_role.json` + `company_profile.json` instead of a JD. Replaces keyword matching with values/domain alignment. Keeps all structural rules, chronological integrity, training-in-education separation, and the earlier-experience compression rule unchanged (Criterion A adapted to anchor alignment since no match_analysis exists in the cold flow).
- Added `prompts/generate_motivation_letter_cold.md` — cold letter opens with a specific observation from the company profile (recent news > mission > product), never implies a posting exists, respects `team_context_companies` and `tone_directives`, writes `letter_type: "speculative"`.
- Added `prompts/generate_short_letter_cold.md` — 500–750 character email-ready distillation, same hook as the full letter.
- Extended the tailor skill's `schemas/letter.schema.json` with an optional `letter_type` enum (`standard` | `speculative`). Backwards-compatible — existing tailor-skill letters omit the field.
- Made `--linkedin-json` and `--interview-markdown` optional in the tailor skill's `scripts/generate_outputs.py` so Phase D can produce a CV + letter pack standalone. Run summary reports `null` for the absent files. Regression-tested the full-pack path (all inputs supplied) — unchanged.
- `SKILL.md` Steps 5, 6, and a Phase-D variant of Step 9 are now concrete. Verified end-to-end CV + letter DOCX generation via the example JSONs in the tailor skill.

## 0.3.0 — 2026-04-17

**Phase C — Role inference loop.**

- Added `schemas/role_candidates.schema.json` — 1–3 candidate angles with title, rationale, seniority band, emphasis areas, risk notes. Non-empty `candidates[]` enforced.
- Added `schemas/selected_role.schema.json` — the user's pick, with `source` in `{candidate_pick, generalist, user_override}`.
- Added `prompts/infer_target_role.md` — proposes 1–3 distinct angles grounded in the fact base + company profile; respects `forbidden_title_labels` and `preferred_title_labels`; never auto-selects.
- `SKILL.md` Step 4 fully specified: generate candidates, forbidden-label post-check, present an interactive menu, persist `selected_role.json`, handle the three sources (number pick / generalist / override) with a confirm when generalist is requested against `allow_generalist: false`.
- Pipeline now runs Steps 0–4 and stops. Validated positive and negative schema cases (enum violations, empty candidate list) via `scripts/validate.py`.

## 0.2.0 — 2026-04-17

**Phase B — Research pipeline.**

- Added `schemas/company_profile.schema.json` — structured profile with citation-backed facts, inferred-field flags, and honest research gaps. Validates against JSON Schema Draft 2020-12.
- Added `prompts/research_company.md` — source priority (website → Indeed MCP → LinkedIn → news → tech hints), hard rules (cite every fact, flag inferences, quote the mission, honest gaps), and an example skeleton.
- `SKILL.md` Step 0 and Step 3 now fully specified: bash commands for path resolution, dependency check, blacklist pre-check against the input name, cold-prefixed output folder creation, raw-research caching, profile validation, and canonical-name blacklist re-check.
- Pipeline currently stops after Step 3 — `/job-cold-prospect <name>` produces `_prep/company_profile.json` + `_prep/raw_research.md` and summarises findings back to the user.

## 0.1.0 — 2026-04-17

**Phase A — Scaffold.**

- Created `.claude/skills/job-cold-prospect/` with `SKILL.md`, `plugin.json`, `README.md`, empty `prompts/` and `schemas/` directories.
- `SKILL.md` establishes the shared-infrastructure convention with `job-application-tailor`: Steps 0–2.5 delegate to the tailor skill verbatim, Steps 3–10 are placeholders to be filled in during Phases B–G.
- Cold output folder naming: `output/cold-[YYYY-MM-DD]-[company-slug]/`.
- Default language set to French; fit score explicitly dropped in favour of a narrative "angle of approach" in the company dossier.

No runtime code yet — the skill is discoverable as `/job-cold-prospect` but invocation only documents the placeholder steps until Phase B lands the company-research pipeline.
