# Pipeline Hardening Roadmap

Multi-session plan to harden the job-prospecting skills after a review on
**2026-07-01**. Read this before starting any item — the motivating evidence and
scope decisions matter.

## Why this exists

A working session that regenerated cold packs and triaged statuses surfaced a
class of problems no single-file read would catch:

- **The history DB diverged mid-session.** Status changes reverted, and a
  regenerated cold record (`#105 Talent-R`) was **replaced by a different
  company** (`Maten`) at the same id, while an earlier record (`#100 Codyssée`)
  survived. The schema uses `INTEGER PRIMARY KEY AUTOINCREMENT`, so ids are *not*
  reused within one lineage — the swap therefore means a **different DB lineage
  replaced the target**. Prime suspect (found while building Phase 1.1): the
  DB layer operates on a **temp working mirror** (`%TEMP%/jobhist-mirror-<hash>.db`)
  and refreshes it from the canonical target only when the target's mtime looks
  *newer*. A stale mirror (or an external snapshot/restore that resets the
  target's mtime) substitutes its whole lineage back onto the target on write.
  The live DB's mtime and output-folder dates were also inconsistent with
  wall-clock time, consistent with this.
- **Latent hazard:** because `update-status` keys on `id`, and after a lineage
  swap `id 105` names a *different company*, "set 105 to applied" can silently
  mutate the wrong record. That's data corruption, not just annoyance.
- **Ergonomic friction:** a descriptive role title produced a monster filename
  (`CV_Edward_Gent_Architecte_applicatif_-_Tech_Lead_NET_Desktop_Services_poste_en_CDI_a_representer_via_Talent-R.docx`);
  ~10 status updates had to be issued one at a time; regenerating a cold pack
  spawned a **duplicate** dated folder + DB row beside the old one (`#41` vs
  `#100`).
- **Pipeline blindness:** `org_type` (employer vs ESN vs agency) is written into
  the pack and dossier HTML but **dropped from the DB snapshot**, and `job-stats`
  has **no `source` filter**, so cold speculative and offer applications blend
  together in every report.
- **Skill hygiene:** `job-cold-prospect/SKILL.md` carries a long "Build status /
  Phase A–G" changelog in the always-loaded body (context cost on every trigger,
  zero runtime value) and a now-stale forward-reference to a `job-stats` follow-up.

## Rollout order

Sequenced cheap-and-safe first, then the DB core, then ergonomics. Each item is
one commit so any can be reverted independently. Check off as they land.

- [x] **Phase 0 — Skill hygiene (D)** · ~1 h, zero risk
  - [x] 0.1 Move the cold SKILL.md phase-log to a new `CHANGELOG.md`
  - [x] 0.2 Fix the stale `job-stats` forward-reference
  - [x] 0.3 Flag job-boards / aggregators in the cold flow
- [~] **Phase 1 — Data integrity (A)** · guardrails 1.1–1.3 done; 1.4 deferred
  - [x] 1.1 `db doctor` fingerprint (read-only) — done; surfaced the temp mirror
  - [x] 1.2 Auto-backup before DB mutations — done (`snapshot_before_mutation`, git-ignored `db-backups/`)
  - [x] 1.3 Natural-key resolution + id-reuse warning — done (`--expect-company` guard + job-status workflow)
  - [ ] 1.4 *(design-only, deferred)* Portable export/import/merge + stable `JOB_TAILOR_HOME`
- [ ] **Phase 2 — Pipeline segmentation (B)** · ~2–3 h, shares a migration with Phase 1
  - [ ] 2.1 DB migration v2→v3: `org_type` column + snapshot field
  - [ ] 2.2 `--source` and `--org-type` filters in `job-stats` / `job-status`
- [ ] **Phase 3 — Ergonomics (C)** · ~2–3 h
  - [ ] 3.1 Filename length cap / parenthetical strip
  - [ ] 3.2 Bulk `update-status`
  - [ ] 3.3 Regenerate **supersede** mode (no duplicate folders + rows)

Suggested cadence: **Session A** = Phase 0 + Phase 1.1–1.3. **Session B** =
Phase 2 (+ decide 1.4 from 1.1's findings). **Session C** = Phase 3.

---

## Phase 0 — Skill hygiene (D)

**Goal:** shrink the always-loaded prompt, remove stale guidance, and reuse the
offer flow's aggregator handling in the cold flow.

**0.1 — Move the phase-log out of the always-loaded body.**
- Only `job-cold-prospect/SKILL.md` has a "## Build status" section (Phases A–G +
  the org_type note + the post-launch refactor). `job-application-tailor/SKILL.md`
  has none — leave it.
- Create `CHANGELOG.md` at the repo root (none exists today) and move the
  phase-log entries there verbatim. Leave a single one-line pointer in SKILL.md
  ("Change history: see `CHANGELOG.md`.").
- Net effect: ~15 lines of historical notes stop loading into context on every
  cold-prospect trigger.

**0.2 — Fix the stale forward-reference.**
- `job-cold-prospect/SKILL.md` Step 10 says *"Do not touch job-stats yet … until
  the stats skill gains a source filter (tracked as follow-up in
  COLD_PROSPECT_ROADMAP.md Phase F second pass)."* Reword to point at Phase 2 of
  this roadmap, and drop the "second pass" phrasing. Once Phase 2 lands, update
  again to describe the shipped filter.

**0.3 — Flag job-boards / aggregators in the cold flow.**
- The offer flow already detects aggregators (`common.is_aggregator`, the
  `aggregators.known_platforms` list in `config/settings.default.yaml`, and the
  `source_platform` field on `job_offer_analysis`). The cold flow has none — we
  hit this when **Aerocontact** (a job board) surfaced a **Safran** posting and a
  pack got generated for the board.
- **Recommended approach:** mirror the offer flow rather than overload `org_type`.
  Add optional `is_aggregator: bool` + `source_platform: string` to
  `company_profile.schema.json`, have `research_company.md` set them when the
  resolved company matches `is_aggregator(...)`, and have SKILL.md Step 3 prompt
  *"X is a job board, not usually the employer — who's the real client? (blank =
  proceed)."* (Alternative considered: a new `job_board` value in the `org_type`
  enum — rejected because org_type drives the letter/LinkedIn/dossier reframe and
  "aggregator" is an orthogonal axis.)

**Effort:** ~1 h. **Risk:** none (docs + one optional schema field).

---

## Phase 1 — Data integrity (A) — diagnose + guardrails first

**Scope decision (2026-07-01):** build the diagnostic + guardrails now; design
the full export/import/merge (1.4) only **after** 1.1 tells us what the
snapshot/restore behavior actually is. Don't over-build a sync system before the
root cause is confirmed.

**1.1 — `db doctor` fingerprint (read-only).**
- New `cli.py` subcommand `db doctor` (or `doctor`) that prints: schema version,
  DB path + mtime, row count, `max(id)`, whether `JOB_TAILOR_HOME` is set, and a
  **content fingerprint** — a stable hash over sorted
  `(company_norm, job_title_norm, created_at, status)` tuples (NOT over the raw
  file, so it's insensitive to VACUUM/rowid noise).
- Purpose: run it at the start/end of a session to detect when the DB has been
  silently replaced or restored across environments, and to confirm whether
  moving the DB to a stable `JOB_TAILOR_HOME` outside the repo stops the drift.
- Read-only, no migration.
- **Implemented (`cli.py doctor`, `--json`):** reports the canonical target AND
  the temp working mirror side by side (path, mtime, size, schema version, row
  count, max id, fingerprint) and **flags divergence** between them — the mirror
  being the leading suspect for the incident above. Fingerprint =
  `job_history_db.compute_content_fingerprint` over sorted natural-key+status
  tuples (order-independent, so two lineages with the same content match).
  First run on the live DB: target == mirror, fp `5c059a4f418f50df`, 105 rows,
  max id 110, `JOB_TAILOR_HOME` unset. Tests in `tests/test_db_doctor.py`.

**1.2 — Auto-backup before mutations.**
- Wrap `update-status`, `update-company`, `update-output-folder`, and
  `record-application` so they snapshot the DB into `backups/` (timestamped)
  before writing. Reuse `scripts/backup_user_data.py` (`backup()` /
  `verify_backup()` already exist). Keep the last N (e.g. 20); prune older.
- Gives a cheap undo and a paper trail if a restore clobbers work again.

**1.3 — Natural-key resolution + id-reuse warning in `job-status`.**
- `job-status` should resolve the target application by
  `(company_norm, job_title_norm)` primarily, and treat a bare numeric id as a
  convenience that is **re-validated**: before mutating, show
  `#<id> <company> — <title>` and, if the caller stated an expected company that
  doesn't match, refuse and surface the mismatch. This is the concrete defense
  against "update 105" hitting `Maten` when the user means the old `Talent-R`.
- Mostly a SKILL.md workflow change plus a small `cli.py` guard; no schema change.

**1.4 — (DESIGN-ONLY, DEFERRED) Portability + stable location.**
- Sketch, to be finalized after 1.1:
  - `export-history` / `import-history` to a **JSONL** file keyed on the natural
    key, so re-import merges (upsert on natural key, newest `updated_at` wins)
    instead of colliding on autoincrement id. This is the cross-machine story;
    the JSONL lives in a private location (NOT this public repo).
  - Document pointing `JOB_TAILOR_HOME` at a stable user dir outside the
    snapshot/restore-prone repo, since `resolve_user_data_dir()` already honors it.
- Decide scope once we know whether the drift is environment snapshotting, cloud
  sync, or genuine multi-machine use.

**Effort:** ~half a day for 1.1–1.3. **Risk:** low (additive; backups are safety).

---

## Phase 2 — Pipeline segmentation (B)

**Goal:** make the pipeline visible by employer-type and by cold-vs-offer.

**2.1 — Migration v2→v3.**
- `job_history_db.py`: bump schema version, `ALTER TABLE applications ADD COLUMN
  org_type TEXT` (default NULL), migrating in place exactly like the v1→v2
  `source` / `company_profile_snapshot` add. Legacy rows stay NULL.
- `add_application()` accepts an optional `org_type`; reject unknown values the
  same way `source` is validated.
- `cli.py` cold `record-application` path reads `company_profile.org_type` into
  the row **and** into the `company_profile_snapshot` subset (the subset at
  `cli.py:~518` currently omits it — that's why today's cold rows have no
  org_type).

**2.2 — Filters + a breakdown.**
- `job-stats`: add `--source offer|cold` and `--org-type <type>` to `stats`,
  `count`, and `skills`; add a `stats --type org` breakdown. Fit-% averages
  should be computed on offer rows only (cold rows have NULL fit by design).
- `job-status`: add `--source` / `--org-type` to `list`.
- Update the Phase-0.2 note in cold SKILL.md to describe the shipped filter.

**Effort:** ~2–3 h. **Risk:** low (mirrors the proven v1→v2 migration pattern).
Add DB tests alongside, like `test_job_history_db_v2.py`.

---

## Phase 3 — Ergonomics (C)

**3.1 — Filename length cap / parenthetical strip.**
- `common.slug_for_filename` (and/or `safe_filename`): cap the job-title slug at
  a sane length (~60 chars) and drop trailing parenthetical qualifiers
  (`(à représenter via Talent-R)`, `(F/H)`). The **document content** keeps the
  full title — only the filename slug is trimmed. Add a unit test with the
  Talent-R title as the fixture.

**3.2 — Bulk status update.**
- `cli.py update-status` accepts multiple ids with a single status
  (`update-status 104 102 103 --status applied`), or a sibling `bulk-status`
  subcommand. One backup (Phase 1.2) covers the batch. Document in
  `job-status/SKILL.md`; regenerate `references/cli.md`.

**3.3 — Regenerate supersede mode.**
- When regenerating a pack for a company that already has one, offer to **reuse
  the existing folder/row** (or mark the prior row `dropped` and reuse the
  folder) instead of creating a second dated folder + DB row. Ties to the
  natural-key work in 1.3. Prevents the `#41` vs `#100` duplication seen this
  session.

**Effort:** ~2–3 h. **Risk:** low–medium (3.3 touches folder rename logic;
lean on the existing `rename-application` primitives).

---

## Out of scope / deferred

- **E — Behavioral eval harness for the cold-prospect prompts** (via
  `skill-creator`): the org_type reframe is only schema-tested, never
  behavior-tested. Highest-confidence but heaviest lift; revisit after A–D.
- **Full DB export/import/merge (1.4)** — pending Phase 1.1 diagnosis.
- **Auto-blacklist after N rejections** — a `job-stats`/`job-status` idea carried
  over from the prior `SKILL_IMPROVEMENTS_ROADMAP.md` out-of-scope list.
- **Fixing the flaky `test_db_concurrency.py`** — fails consistently in the
  Windows sandbox; may be a real locking bug (relevant to Phase 1) or a bad test.
  Diagnose opportunistically during Phase 1.
