# Changelog

Build history for the job-prospecting skills. Kept out of the individual
`SKILL.md` bodies so those stay lean (a SKILL.md loads into context on every
trigger; historical notes don't need to ride along). Newest entries first
within each skill.

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
