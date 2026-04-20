# Changelog

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
