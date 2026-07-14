# Changelog

Build history for the job-prospecting toolkit. Kept out of the individual
`SKILL.md` bodies so those stay lean (a SKILL.md loads into context on every
trigger; historical notes don't need to ride along). Newest entries first
within each section.

## v1.0.0 (unreleased)

The version declared in `.claude-plugin/plugin.json`. Tagging is held until
the packaged bundle passes a fresh-machine smoke test (see
`PLUGIN_ROADMAP.md` § Phase 5). Everything below is part of this release.

## Repo & infrastructure

- **Publication readiness (2026-07-14)** — the packager now bundles all
  **five** skills (`job-prep-cv` and `job-cold-prospect` were missing, so a
  built bundle shipped a tailor skill that broke at Step 0); one canonical
  plugin manifest at `.claude-plugin/plugin.json` (the unsupported per-skill
  `plugin.json` files are gone); skill setup blocks resolve both the dev
  layout and the installed-plugin layout (`$CLAUDE_PLUGIN_ROOT/skills/…`);
  the shippable surface is scrubbed of author-specific data (gitignored
  `example_*.json` excluded from bundles by name, prompt/schema examples
  genericized). Windows fix: the cross-process DB lock no longer silently
  degrades under contention (mandatory region locks made a waiter's lockfile
  seed write fail, which was misread as "proceed unlocked").
- **Review sprint 1 (2026-07-14)** — removed stale "Phase B/C stop point"
  instructions that halted the cold-prospect pipeline mid-run; untracked
  three personal job-offer texts committed before their ignore rule existed;
  `.daily_run/` and `.pytest_cache/` gitignored; the `Write(output/**)`
  permission the tailor skill's parallel subagents need now ships in the
  tracked `.claude/settings.json`.
- **Documentation set (2026-07-09 → 14)** — bilingual (EN + FR) non-technical
  overview and technical reference under `docs/`, plus a hub page; a
  pre-commit documentation-drift gate blocks commits that change
  doc-relevant source without touching `docs/` (bypass: `DOCS_OK=1`).
- **Pipeline hardening Phases 0–3 (2026-06-25 → 07-07)** — DB schema v3
  (`org_type` column + `--source` / `--org-type` segmentation across `stats`,
  `skills`, `count`, `list`); automatic DB snapshot to `db-backups/` before
  every mutating CLI command; `--expect-company` guard on `update-status` /
  `update-company`; `bulk-status` for multi-id updates; `record-application
  --supersede` to retire prior duplicate rows; `doctor` diagnostics; filename
  slug length cap. Details in `PIPELINE_HARDENING_ROADMAP.md`.

## job-application-tailor

Maintained in its own changelog:
[`.claude/skills/job-application-tailor/CHANGELOG.md`](.claude/skills/job-application-tailor/CHANGELOG.md).

## job-cold-prospect

- **Organisation-type awareness (2026-06-22)** — Step 3 classifies
  `company_profile.org_type` (`end_employer` / `esn` / `staffing_agency` /
  `recruitment_agency` / `unknown`) with a citable `org_type_evidence` +
  `org_type_inferred` flag; both fields required in `company_profile.schema.json`.
  Every downstream prompt (role inference, motivation letter, short letter,
  LinkedIn, dossier) branches on it: for an intermediary the pack pivots from
  "join your team/mission" to "the profile I offer for your missions / for you to
  represent", the LinkedIn target flips from CTO/hiring-manager to
  business-manager/recruiter, and the dossier's objection-prep swaps in the
  intermediary's real questions (mission types, TJM, mobility, availability).
  Cold-prospect suite: 36 pass.
- **Post-launch refactor (2026-05-04)** — Steps 0–2.5 (pre-flight, master-CV
  read, fact-base extract, fact-base verify) extracted to a shared `job-prep-cv`
  sub-skill (`disable-model-invocation: true`). Both `job-application-tailor` and
  `job-cold-prospect` delegate to it via a single ~10-line block, eliminating the
  verbatim "follow tailor SKILL.md § Step X" stubs. Folder naming is the only
  flow-aware branch inside the sub-skill (`[date]-[slug]/` for offer,
  `cold-[date]-[slug]/` for cold). No Python touched.
- **Phase G (tests + docs)** — cold-prospect `tests/` directory with schema-
  validation tests (including backwards-compat checks on the shared LinkedIn
  schema). Tailor skill gained 8 DB tests covering v1→v2 migration, legacy-row
  preservation, cold-insert round-trip, bad-source rejection, fresh-DB-at-v2,
  reopen idempotency, and half-migrated-state recovery. README, changelog, and
  roadmap updated.
- **Phase F (history DB)** — shared DB schema bumped to v2:
  `applications.source` (`'offer'` / `'cold'`) + `applications.company_profile_snapshot`.
  Existing DBs migrate in place on first open via `ALTER TABLE ADD COLUMN`;
  legacy rows default to `source='offer'`. Step 10 writes a cold row with a
  compact snapshot subset. `add_application()` rejects unknown `source` values.
- **Phase E (LinkedIn + dossier)** — Step 7 produces cold-flow LinkedIn messages
  (2 variants per leadership contact, hiring-manager-targeted, `outreach_type:
  "cold"` recorded). Step 8 produces `company_dossier.md`, a 9-section deliverable
  replacing the fit-score document with a narrative angle of approach.
  `linkedin.schema.json` extended with optional `outreach_type` + `target_role`
  (backwards-compatible).
- **Phase D (CV + letters)** — Steps 5, 6, and a Phase-D variant of Step 9
  produce the tailored CV DOCX, motivation-letter DOCX, and short-letter TXT.
  `letter_type: "speculative"` recorded.
- **Phase C (role inference loop)** — Step 4 produces `_prep/role_candidates.json`,
  prompts the user, writes `_prep/selected_role.json`.
- **Phase B (research pipeline)** — Steps 0–3 produce `_prep/company_profile.json`
  + `_prep/raw_research.md`.
- **Phase A (scaffold)** — initial skill scaffold.

The skill runs fully end-to-end: research → role pick → tailored CV → motivation
letter + short letter → LinkedIn messages → company dossier → history insert.
