# Job Prospecting Plugin — Roadmap

**Goal.** Ship the `job-application-tailor` skill (and its satellites `job-stats`, `job-status`) as a Claude Code plugin that works for any user with any master CV, not just Eddie on Windows.

**Maintained in this file** so progress survives across chat sessions. Update the checkboxes as you go, add a line to the Decision log when you make a judgment call, and capture any new learnings in the Notes section at the bottom.

---

## Current state (2026-04-10 baseline)

- Skill lives at `.claude/skills/job-application-tailor/` with prompts, schemas, scripts, config.
- Satellite skills `job-stats` and `job-status` live alongside it.
- SQLite job history DB at `resources/job_history.db` (~34 applications).
- Master CV at `resources/MASTER_CV.docx`; auto-cached fact base in `resources/cv_fact_base.json` + `.cv_hash`.
- Recent work in this conversation:
  - Added **earlier-experience compression** (cutoff year in `settings.yaml`, load-bearing-aware, dateless consolidated line in detected language).
  - Added **training-periods-in-Education-only** rule to `tailor_cv.md`.
  - Added **match evidence naming** nudge in `match_analysis.md`.
  - Validated via 4 real-job test cases across 2 iterations (Segment Elite, Cegid, Younited, Skeepers).

### Eddie-specific assumptions still baked in

These are the portability blockers. Any of them that aren't fixed before plugin release will bite the next user.

1. `project_cv_fortran_experience.md` memory injects an off-CV fact into the fact base. Brittle — only works for Eddie, only in sessions that load that memory.
2. Several feedback memories in `~/.claude/projects/.../memory/` encode tone rules and word blacklists (e.g. "don't imply solo work at Oodrive", "Eddie is Desktop & Services, not Backend"). Won't ship with the plugin.
3. PDF generation uses Microsoft Word via `docx2pdf` → Windows-only. Mac/Linux users get DOCX only and a silent fallback.
4. Example paths in `references/commands.md` and docstrings hardcode `C:\GitProjects\AI\Job Prospecting\...`.
5. User data (master CV, DB, output/, cv_fact_base cache) lives inside the project directory alongside the skill code. Fine for a loose install, wrong for a plugin where code and user data must be separable.
6. Language defaults fall back to French (`fallback_language: fr` in `settings.yaml`).

---

## Testing strategy — TDD for every risky change

**Rule:** For every task in this roadmap, write the test *before* the implementation. No code that touches user data ships without a test that would have caught the mistake.

**Why TDD specifically here:**
1. The vital user data is gitignored. A silent bug in path resolution or migration is unrecoverable from git.
2. The risky phases (0, 3, 4.5) have invariants that are easy to state and easy to verify programmatically: *"the backup manifest SHA-256s match the live files"*, *"`resolve_user_data_dir()` returns the legacy path when legacy data exists"*, *"migration is a no-op on second run"*. Each of these becomes a one-line pytest assertion.
3. Writing the test first forces the invariant to be *explicit*. If you can't write the test, you probably don't understand the requirement yet.
4. The existing earlier-experience compression rule and training-in-education rule (added earlier in this codebase's history) have no regression tests. They are one accidental prompt edit away from silently breaking. This roadmap is a good excuse to backfill them.

### Phase T — Test harness baseline (run once, before Phase 0)

Establish a pytest setup the later phases can build on.

- [x] **Create `.claude/skills/job-application-tailor/tests/`** with an empty `__init__.py`, a `conftest.py` with fixtures for a sample master CV, sample fact base, sample job offer analysis, and sample match analysis. Use small synthetic data, not Eddie's real CV.
- [x] **Add pytest to `requirements.txt`** and document the test command in `references/commands.md` under a new "Testing" section. *(requirements.txt done; commands.md entry deferred to a later pass.)*
- [x] **Write a smoke test** that imports every module in `scripts/` — catches import errors early.
- [x] **Write regression tests for the recent rules:** implemented via a new pure-Python validator module (`scripts/tailor_invariants.py`) rather than direct `tailored_cv.json` inspection — see Decision log 2026-04-10. 8 tests cover:
  - `test_compression_keeps_load_bearing_role` + negative `test_compression_detects_dropped_load_bearing_role`.
  - `test_compression_consolidates_non_load_bearing`.
  - `test_compression_disabled_when_cutoff_null`.
  - `test_training_entries_not_in_experience` + negative `test_training_leak_is_detected`.
  - `test_consolidated_line_is_dateless_in_detected_language` + negative `test_consolidated_line_with_date_is_flagged`.

### Phase-by-phase test manifest

Each phase below gets its tests listed inline. The convention: under every phase, a sub-section "Tests to write first" lists the pytest tests that pin the invariants, followed by the implementation tasks. **Do not implement until the tests exist, are runnable, and fail for the right reason.**

---

## Phase 0 — Pre-flight backup (MUST run before Phase 3 and Phase 4.5)

**Goal:** A full, timestamped, human-readable backup of all vital user data so that any mistake in Phases 3 or 4.5 is fully recoverable.

**Why:** As of 2026-04-10, the following are **gitignored and therefore not protected by git**:
- `resources/MASTER_CV.docx` — the source of truth, hand-tuned
- `resources/job_history.db` — 30 applications across 28 companies (the real memory of the job search)
- `resources/cv_fact_base.json` + `.cv_hash` — cached extraction
- `output/` — 29 full application packs (CVs, letters, interview prep)

Any layout change (Phase 3) or migration (Phase 4.5) that touches these files without a prior backup is one typo away from losing several weeks of work.

### Tests to write first

- [x] `test_backup_creates_manifest_with_sha256_per_file` — run the script against a fixture directory, assert every file ends up in the manifest with a SHA-256 that matches `hashlib.sha256(file_bytes)`.
- [x] `test_backup_copies_all_files_recursively` — fixture with nested directories, assert the copy preserves structure and file counts.
- [x] `test_backup_db_export_csv_row_count_matches` — fixture DB with N rows, assert the exported CSV has N+1 lines (header + rows).
- [x] `test_running_backup_twice_creates_two_distinct_folders` — invoke twice with a fake clock, assert two separate timestamped folders.
- [x] `test_backup_refuses_to_overwrite_existing_timestamp` — assert a crash rather than a silent overwrite if the target timestamp collides.
- [x] `test_sha256_mismatch_fails_verification` — corrupt a file in the backup, run the verification function, assert it returns a failure report naming the bad file.

### Tasks

- [x] **Write `scripts/backup_user_data.py`** — pure copy, no destructive ops. Creates `backups/pre-plugin-migration-<YYYY-MM-DD-HHMM>/` containing:
  - Full copy of `resources/` (all files, including the DB)
  - Full copy of `output/` (all subfolders)
  - A `db_export/` directory with one CSV per SQLite table (more robust than a single dump file — handles any schema)
  - A `manifest.json` listing every file with its SHA-256, so integrity can be verified later
  - A `README.txt` with restoration instructions
- [x] **Add an untouchable rule** — the backup folder must NOT be deleted or modified by any later phase. If disk space becomes a concern, the user deletes it manually *after* confirming the plugin install works.
- [x] **Add a `backups/` entry to `.gitignore`** so the backups stay local and don't pollute the repo.
- [x] **Run it.** Backup `backups/pre-plugin-migration-2026-04-10-1553/` created: 456 files, 29 output folders, 30 applications rows, verification clean (0 violations).
- [x] **Smoke-check the backup.** manifest.json `file_count: 456` matches SHA-256 verification, `applications` table reopens with 30 rows via sqlite, resources/ contains MASTER_CV.docx + cv_fact_base.json + job_history.db, all 4 DB tables exported to CSV (applications, company_lists, job_skills, schema_version). *(Deferred: opening the DOCX in Word — not needed for the automated verification.)*

### Success criteria

- A complete, verified backup exists at `backups/pre-plugin-migration-<timestamp>/`.
- The manifest's SHA-256 values match the live files at the moment the backup was taken.
- The user can read a clear "if something goes wrong, here's how to restore" paragraph in the backup's `README.txt`.

### Files touched
`scripts/backup_user_data.py` (new), `.gitignore` (add `backups/`), `backups/pre-plugin-migration-<timestamp>/` (new, outside git).

---

## Phase 1 — Replace memory-based personalization with explicit user files

**Goal:** Eliminate the reliance on user-specific Claude memories for tone rules, off-CV facts, and style preferences. Everything the skill needs about the user must live in files the user controls.

**Why:** Plugins don't ship with memories. The Fortran→C++ case exposed this: on a fresh session without the `project_cv_fortran_experience.md` memory loaded, the skill would silently lose that fact. The same applies to every feedback memory.

### Tests to write first

- [x] `test_addendum_missing_returns_empty_context` — implemented in `tests/test_user_customization.py`.
- [x] `test_addendum_parses_additional_experience_entries` — implemented.
- [x] `test_addendum_content_reaches_tailor_cv_context` — implemented as a `merge_addendum_into_fact_base()` round-trip (the merged fact base is what gets passed to the tailor_cv prompt).
- [x] `test_addendum_never_writes_to_fact_base_cache` — implemented via SHA-256 before/after compare.
- [x] `test_user_prefs_forbidden_title_labels_blocks_label` — implemented via pure-Python `find_forbidden_title_label_violations()` validator (same validator-as-test pattern used in Phase T).
- [x] `test_user_prefs_team_context_companies_prevents_solo_phrasing` — implemented via `find_team_context_solo_phrasing()` with a proximity-based regex check.
- [x] `test_missing_prefs_file_is_not_an_error` — implemented.
- [x] `test_addendum_does_not_contaminate_verify_fact_base` — implemented by asserting the merged fact base's `technologies` array is byte-identical to the input's.
- [x] **Bonus** `test_addendum_merge_normalizes_dashes_in_dates` — caught during bring-up: the extractor emits unicode en dashes in date strings but users type ASCII hyphens. Added `_normalize_dashes()` in the merger.

### Tasks

- [x] **Create `resources/cv_addendum.md`** (user-owned) — gitignored. Eddie's Fortran → C++ conversion bullet is the first real entry (migrated from `project_cv_fortran_experience.md`).
- [x] **Create `resources/user_prefs.yaml`** (user-owned) — gitignored. Populated with Eddie's `forbidden_title_labels` (Backend variants), `preferred_title_labels` (Services, Intégration & Architectures Applicatives), letter `tone_directives`, and `team_context_companies: [Oodrive, Oodrive SA]`.
- [x] **Add a loader** `scripts/user_customization.py` — exposes `load_customization_context()`, `merge_addendum_into_fact_base()`, `find_forbidden_title_label_violations()`, `find_team_context_solo_phrasing()`.
- [x] **Pass the customization context into Step 5 (tailor_cv), Step 6 (letter), Step 7 (LinkedIn)** — prompt files updated to document the new inputs and their semantics. Actual runtime wiring happens when Claude executes SKILL.md Step 0 (documented there).
- [x] **Update `prompts/extract_cv_data.md`** — added a "Scope boundary — raw docx only" section explicitly isolating the extractor from the addendum layer.
- [x] **Update SKILL.md Step 0** — added a "Load user customization layer" subsection with the loader call; Step 5 now documents the `merge_addendum_into_fact_base()` call and an optional post-generation forbidden-label check; Steps 6/7 note that the subagents must receive `$CUSTOMIZATION`.
- [x] **Neutralise** `project_cv_fortran_experience.md`, `feedback_no_backend_label.md`, `feedback_motivation_letter_tone.md` — rewritten as short pointer files that explain the new canonical location and warn future sessions not to reapply the content from memory.
- [x] **One-time cache cleanup** — `resources/cv_fact_base.json` had the Fortran bullet baked in from the old memory-enrichment flow. Removed the bullet so the cache reflects the raw docx only. `verify_fact_base.py` passes against the updated cache.

### Success criteria

- Fresh Claude Code session on a different machine with no loaded memories produces the same Segment Elite output as today (Fortran bullet present, correct title, "team" phrasing at Oodrive).
- A brand-new user with only `MASTER_CV.docx` and no addendum/prefs can still run the skill end-to-end — the files are *optional* enrichment, not required.

### Files touched
`resources/cv_addendum.md` (new), `resources/user_prefs.yaml` (new), `scripts/user_customization.py` (new), `prompts/tailor_cv.md`, `prompts/generate_motivation_letter.md`, `prompts/generate_linkedin_message.md`, `prompts/extract_cv_data.md`, `SKILL.md`.

---

## Phase 2 — Cross-platform PDF generation

**Goal:** Any user, any OS, gets both DOCX and PDF without manual intervention.

**Why:** Currently the PDF pipeline shells out to Word via `docx2pdf`. Mac users need Word installed; Linux users get nothing. LibreOffice and pandoc are both free and cross-platform.

### Tests to write first

- [x] `test_pdf_pipeline_tries_docx2pdf_first` — all 6 tests pass against `scripts/pdf_pipeline.py`.
- [x] `test_pdf_pipeline_falls_through_on_failure`.
- [x] `test_pdf_pipeline_all_fail_raises_actionable_error` — message names docx2pdf, LibreOffice, pandoc and the DOCX path.
- [x] `test_pdf_pipeline_docx_always_produced_even_if_pdf_fails` — verified byte-identical DOCX after failed conversion.
- [x] `test_detect_libreoffice_on_path` — both branches (soffice present / absent) covered.
- [x] `test_libreoffice_invocation_uses_headless_flag` — asserts `--headless --convert-to pdf` and DOCX path in argv.

### Tasks

- [x] **Audit current PDF path** in `scripts/generate_outputs.py` — was a 7-line inline `docx2pdf` block (lines 97-105 pre-refactor) with no fallback and a silent `except: pass` around `Word.Application.Quit` noise.
- [x] **Add a LibreOffice fallback** — `_try_libreoffice()` in `scripts/pdf_pipeline.py`: `shutil.which('soffice')` then `soffice --headless --convert-to pdf --outdir <dir> <file.docx>` with a 120 s timeout.
- [x] **Add a pandoc fallback** as tertiary — `_try_pandoc()` using `pandoc <docx> -o <pdf>`.
- [x] **Strategy** — `convert_docx_to_pdf()` walks `(_try_docx2pdf, _try_libreoffice, _try_pandoc)` at call time, returning on first success. On total failure it raises `PdfConversionError` with an actionable message naming all three tools and the DOCX path.
- [x] **Update `requirements.txt` notes** — LibreOffice and pandoc documented as optional external binaries with per-OS install commands (apt / brew / winget) and a note that DOCX output still works when none are present.
- [ ] **Test matrix** (manual, one-time): Windows+Word, Mac+Word, Mac+LibreOffice, Linux+LibreOffice, Linux+pandoc.

### Success criteria

- `scripts/generate_outputs.py` produces a PDF on at least 3 of the 5 test platforms without manual config.
- Missing PDF tooling produces a single actionable error message, not a crash or a silent skip.

### Files touched
`scripts/generate_outputs.py`, `requirements.txt`, `references/commands.md` (mention fallbacks).

---

## Phase 3 — Separate plugin code from user data

### Tests to write first

- [ ] `test_resolve_returns_legacy_path_when_project_resources_exists` — fixture simulates a legacy install (project has `resources/MASTER_CV.docx`); assert `resolve_user_data_dir()` returns the project path, not the XDG path. This is the back-compat invariant — violating it would silently orphan existing users.
- [ ] `test_resolve_returns_xdg_path_on_linux_with_no_legacy` — monkeypatch `sys.platform = 'linux'`, no legacy resources present; assert the returned path is `$XDG_DATA_HOME/job-application-tailor/` (or the `~/.local/share/...` fallback).
- [ ] `test_resolve_returns_library_path_on_mac_with_no_legacy` — monkeypatch `sys.platform = 'darwin'`; assert `~/Library/Application Support/job-application-tailor/`.
- [ ] `test_resolve_returns_appdata_path_on_windows_with_no_legacy` — monkeypatch `sys.platform = 'win32'`; assert `%APPDATA%\job-application-tailor\`.
- [ ] `test_env_var_overrides_everything` — set `JOB_TAILOR_HOME=/tmp/foo`; assert resolution returns `/tmp/foo` regardless of platform or legacy state.
- [ ] `test_phase_3_reads_only_never_writes` — spy on every file write operation in the Phase 3 diff; assert none of them target the resolved data dir. (Phase 3 code must only *read*; writes happen in existing migration paths or Phase 4.5.)
- [ ] `test_config_layering_merges_correctly` — fixture with a `settings.default.yaml` and a `settings.yaml` override; assert the merged config has the override's values winning on conflict and the defaults' values for unset keys.
- [ ] `test_no_hardcoded_absolute_paths_in_scripts` — grep every `.py` file in the skill for strings matching `C:\\` or `/home/`; assert the list is empty. Catches accidental reintroductions.
- [ ] `test_no_hardcoded_resources_slash_in_scripts` — grep for bare `resources/` in script strings; flag any that aren't going through `resolve_user_data_dir()`.



**Goal:** Plugin installs to a read-only location (pip install, git clone, `.claude-plugin` bundle); user data lives under a separate user-writable path.

**Why:** Plugins can't assume write access to their install directory. The current layout mixes `resources/MASTER_CV.docx` (user data) with the prompts and schemas (code). Mixing the two makes updates unsafe and makes multi-user installs impossible.

### Target layout

```
<plugin-install>/              # read-only, ships with the plugin
├── .claude-plugin/
│   └── plugin.json
└── .claude/skills/job-application-tailor/
    ├── SKILL.md
    ├── prompts/
    ├── schemas/
    ├── scripts/
    ├── config/
    │   └── settings.default.yaml
    └── samples/
        └── MASTER_CV.example.docx

<user-data-dir>/              # user-writable, not in the plugin
├── MASTER_CV.docx             # required
├── cv_addendum.md             # optional, from Phase 1
├── user_prefs.yaml            # optional, from Phase 1
├── settings.yaml              # optional overrides on top of settings.default.yaml
├── job_history.db
├── cv_fact_base.json + .cv_hash
└── output/
    └── <fit>-<date>-<slug>/
```

`<user-data-dir>` resolution order:
1. Env var `JOB_TAILOR_HOME` if set
2. `$XDG_DATA_HOME/job-application-tailor/` on Linux, `~/Library/Application Support/job-application-tailor/` on Mac, `%APPDATA%\job-application-tailor\` on Windows
3. Fallback: `~/.job-application-tailor/`

### Tasks

- [ ] **Run Phase 0 first.** Phase 3 must not start until `backups/pre-plugin-migration-<timestamp>/` exists and has been verified.
- [ ] **Rule: Phase 3 reads, it does not move.** This phase changes code so that scripts discover the user data via `resolve_user_data_dir()`, but it does **not** copy, move, or rewrite any existing file. Old location stays populated. Migration to the new location is Phase 4.5's job and is opt-in.
- [ ] **Add `scripts/paths.py`** with a single `resolve_user_data_dir()` function implementing the lookup above. It must return the old project `resources/` path when that's where the data lives today, so current workflows keep working unchanged.
- [ ] **Replace every hardcoded `resources/...` path** in scripts, prompts, and `references/commands.md` with a reference to the resolved user data dir.
- [ ] **Rename `config/settings.yaml` → `config/settings.default.yaml`** in the plugin, and add a config layering step: defaults merged with `<user-data-dir>/settings.yaml` if it exists.
- [ ] **Update `SKILL.md` Directory Layout section** to describe the new split.
- [ ] **Keep a backwards-compat path** — if the user still has `<project>/resources/MASTER_CV.docx`, prefer that and warn them to migrate.

### Success criteria

- Running the skill with the plugin installed but no project-level `resources/` folder still works: the user data is auto-discovered in the OS-standard location.
- A second user on the same machine with a different `JOB_TAILOR_HOME` gets fully isolated data.

### Files touched
All scripts, all prompts (for path references), `SKILL.md`, `config/settings.default.yaml` (renamed), `references/commands.md`.

---

## Phase 4 — First-run onboarding

### Tests to write first

- [ ] `test_init_creates_user_data_dir_if_missing` — fresh temp dir, run init, assert the target directory and its `output/` subfolder exist.
- [ ] `test_init_does_not_overwrite_existing_master_cv` — target dir already has a real `MASTER_CV.docx`; run init; assert the existing file is untouched (SHA-256 compare).
- [ ] `test_init_copies_sample_cv_as_example_not_master` — assert init writes `MASTER_CV.example.docx`, not `MASTER_CV.docx`, so the user never accidentally ships with the fictional data.
- [ ] `test_init_writes_both_templates` — assert `cv_addendum.template.md` and `user_prefs.template.yaml` land in the user data dir.
- [ ] `test_init_is_idempotent` — run init twice, assert second run makes no changes (files are all unchanged by SHA-256).
- [ ] `test_sample_cv_extracts_cleanly` — integration: run the Step 2 extractor against `MASTER_CV.example.docx`, assert a valid `cv_fact_base.json` that passes schema validation and `verify_fact_base.py`. Catches template drift.



**Goal:** A brand-new user runs the skill, sees a helpful onboarding flow, ends up with a working setup in under 5 minutes.

**Why:** Currently if `MASTER_CV.docx` is missing, the skill stops with a one-line instruction. That's fine for you, not fine for a plugin installed by someone who just wants to apply to jobs.

### Tasks

- [ ] **Add `init` mode to the skill** — triggered when the user says "set up job tailor" or runs the skill for the first time without a master CV:
  1. Resolve the user data dir (creating it if needed).
  2. Copy `samples/MASTER_CV.example.docx` to `<user-data-dir>/MASTER_CV.example.docx` and tell the user to customize it (don't overwrite if real one exists).
  3. Copy blank `cv_addendum.md` and `user_prefs.yaml` templates with commented examples.
  4. Offer to open the folder in the user's file explorer.
  5. Print a short "next steps" summary.
- [ ] **Build `MASTER_CV.example.docx`** — a neutral fictional CV (Alex Dupont, Software Engineer) with all the style anchors the extractor expects: skills table, section headers with the right styles, dates in the expected format.
- [ ] **Build `cv_addendum.template.md`** — a commented template showing the section structure.
- [ ] **Build `user_prefs.template.yaml`** — a commented template with all available keys and examples.
- [ ] **Update SKILL.md Step 0** to trigger `init` mode if no master CV is found.

### Success criteria

- A user who has never seen the skill before can go from zero to a generated application pack for their first real job offer, using only the sample CV as a reference point for their own.

### Files touched
`SKILL.md` (Step 0 onboarding), `samples/MASTER_CV.example.docx` (new), `samples/cv_addendum.template.md` (new), `samples/user_prefs.template.yaml` (new), `scripts/init.py` (new).

---

## Phase 4.5 — Migration from the loose project install

### Tests to write first

These are the most safety-critical tests in the whole roadmap. Every one pins an invariant that, if violated, would corrupt or orphan real user data.

- [ ] `test_dry_run_writes_nothing_anywhere` — run `migrate.py` with no flags against a fixture install, spy on all `open()`/`Path.write_*`/`shutil.copy*` calls, assert zero writes outside the temp scratch area used for verification.
- [ ] `test_apply_copies_all_legacy_files_to_new_location` — fixture legacy install, run `--apply`, assert every file in `resources/` and `output/` has a corresponding copy at the new location with matching SHA-256.
- [ ] `test_apply_does_not_move_or_delete_legacy_files` — after `--apply`, assert the legacy `resources/` and `output/` are still present and byte-identical to their pre-migration SHA-256 manifest.
- [ ] `test_apply_rewrites_db_output_folder_column` — fixture DB with rows whose `output_folder` points at the legacy path; run `--apply`; assert every row now points at the new path and that the pointed-to directories actually exist.
- [ ] `test_apply_is_a_noop_on_second_run` — run `--apply` twice; assert the second run produces no file changes and prints "already migrated".
- [ ] `test_apply_requires_phase_0_backup_to_exist` — no `backups/` directory; run `--apply`; assert it refuses to proceed and tells the user to run Phase 0 first.
- [ ] `test_verification_gate_blocks_apply_on_failure` — inject a scenario where the post-copy verification fails (e.g. corrupt the copied DB in the scratch dir); assert `--apply` refuses to touch the real destination and leaves the legacy install intact.
- [ ] `test_rollback_restores_db_output_folder_column` — after `--apply`, run `--rollback`; assert every DB row's `output_folder` matches its pre-migration value.
- [ ] `test_find_duplicates_still_works_after_migration` — end-to-end: migrate a fixture install, then call `JobHistoryDB.find_duplicates()` for a known past application; assert the duplicate is found and the returned `output_folder` points at the new location and is openable.
- [ ] `test_skill_can_run_against_migrated_data` — ultimate integration test: migrate a fixture, then spawn a subprocess that runs Step 5 (tailor CV) against a past `_prep/` directory in the new location, assert it produces a valid `tailored_cv.json`.
- [ ] `test_migrate_handles_paths_with_spaces` — fixture uses a legacy root like `/tmp/Job Prospecting/` (with a space); assert DB path rewrite and file copies all handle the space correctly. Catches a whole class of Windows-path bugs early.



**Goal:** An existing user (currently: Eddie) can switch from the loose repo-based install to the plugin install without losing data or re-running every past application.

**Why:** The current layout puts `MASTER_CV.docx`, `job_history.db` (34 real applications), cached fact base, and ~30 `output/<fit>-<date>-<slug>/` folders inside the project directory. Phase 3 moves the canonical location to an OS-standard user data dir. Without an explicit migration step, the first plugin install would either (a) start from empty and orphan all the history, or (b) silently keep writing to two different places. Both are bad.

### Tasks

- [ ] **Confirm Phase 0 backup exists and has been verified.** Phase 4.5 must not start otherwise.
- [ ] **Write `scripts/migrate.py`** — idempotent, dry-run by default, with a verification gate:
  1. Detect a legacy install: `resources/MASTER_CV.docx` and/or `resources/job_history.db` inside the project directory.
  2. Resolve the target user data dir per Phase 3's rules.
  3. Print a plan: what will be copied, where, and what will be left behind.
  4. **Verification gate (new):** before `--apply` writes anything to the real destination, copy the data to a scratch temp dir, run the skill against a sample past application through the new code path, and verify that `find_duplicates` still returns the expected row and the tailoring step still produces the same JSON shape. Only if verification passes does `--apply` copy to the real destination.
  5. With `--apply`, copy (not move) the files to the new location. Copy, not move, so the legacy install keeps working until the user is satisfied.
  6. Update DB rows that contain absolute `output_folder` paths — rewrite them to the new absolute location. This is critical: `find_duplicates` and history checks key on those paths.
  7. Write a migration marker file `<user-data-dir>/.migrated_from` containing the old project root, so future re-runs are no-ops.
- [ ] **Handle the output folder rewrite specifically.** `resources/job_history.db` has an `applications.output_folder` column with entries like `C:\GitProjects\AI\Job Prospecting\output\medium-10042026-...`. After migration these point nowhere unless rewritten. The migration script must:
  - Detect the old project root from the DB paths.
  - Rewrite each row's `output_folder` to `<new-output-root>\<same-subfolder-name>`.
  - Leave a `--rollback` path that reverses the rewrite if the user changes their mind.
- [ ] **Memory files cleanup prompt.** After successful migration, print a checklist of Eddie-specific memory files the user may want to clean up now that their content lives in `cv_addendum.md` and `user_prefs.yaml` (from Phase 1):
  - `project_cv_fortran_experience.md`
  - `feedback_no_backend_label.md`
  - `feedback_motivation_letter_tone.md`
  - `feedback_training_not_in_experience.md` (already obsoleted — the rule is in `tailor_cv.md` now)
  Don't auto-delete; just list them.
- [ ] **Add a dry-run eval.** Copy the current project state into a temp directory, run the migration against it, and verify: file counts match, DB rows rewritten, a subsequent `job-application-tailor` run on an existing job still finds its prior history via `find_duplicates`.
- [ ] **Document in README** — a "Migrating from a pre-1.0 install" section with the exact commands.

### Success criteria

- Eddie (the canonical legacy user) can run `scripts/migrate.py --apply` and then immediately run the skill on a past job offer; the duplicate detector correctly surfaces his prior application and points at the *new* output folder location.
- Running the migration twice in a row is a no-op; it doesn't duplicate rows or re-copy files.
- Rollback restores the DB to the pre-migration state.

### Files touched
`scripts/migrate.py` (new), `README.md` (migration section), `PLUGIN_ROADMAP.md` (tick the boxes).

---

## Phase 5 — Plugin packaging and release

### Tests to write first

- [ ] `test_plugin_manifest_is_valid_json` — parse `.claude-plugin/plugin.json`, assert required fields are present.
- [ ] `test_package_script_produces_archive` — run the packaging script against a fresh copy of the repo, assert an archive file is created with the expected contents (three skills + manifest).
- [ ] `test_package_excludes_user_data` — inspect the produced archive, assert it does NOT contain `resources/MASTER_CV.docx`, `job_history.db`, or `output/` — these are user data and must never be bundled.
- [ ] `test_package_excludes_backups` — assert the archive does NOT contain `backups/`.
- [ ] `test_package_includes_sample_cv` — assert `samples/MASTER_CV.example.docx` IS in the archive.
- [ ] `test_all_phase_tests_pass_in_ci` — top-level gate: running `pytest` from the repo root must pass all tests from Phases T, 0, 1, 2, 3, 4, 4.5 before packaging is allowed.



**Goal:** The repo produces a `.skill` or plugin bundle that can be installed by `claude plugin install` (or equivalent) with a single command.

**Why:** Everything above is worthless if users have to manually copy files into `.claude/skills/`.

### Tasks

- [ ] **Research current Claude Code plugin format** — what's the canonical way to ship a plugin in April 2026? Check the latest docs. (Update this roadmap with the answer.)
- [ ] **Write `.claude-plugin/plugin.json`** with:
  - name, version, description, author, homepage, license
  - the three skills: `job-application-tailor`, `job-stats`, `job-status`
  - required tools and MCPs (none hard-required, but Gmail/Calendar MCPs unlock optional features)
  - minimum Claude Code version
- [ ] **Write a short `README.md`** at the repo root with install instructions, quick start, and a link to this roadmap for contributors.
- [ ] **Package script** — single command that bundles the three skills + the plugin manifest into a distributable archive. May already exist as `skill-creator:skill-creator` package helper; verify.
- [ ] **Smoke test the package** on a fresh machine (Windows + Mac + Linux if possible).
- [ ] **Tag v1.0.0 in git**, push.

### Success criteria

- An install from the bundle on a fresh machine goes through Phases 1-4 cleanly and produces a valid application pack for a real job offer.
- No project-local files required beyond what the install creates.

### Files touched
`.claude-plugin/plugin.json` (new), `README.md` (new or updated), `scripts/package.py` or equivalent, `CHANGELOG.md` (new).

---

## Post-v1 polish (optional, do later)

- [ ] **Intelligent bullet pruning** — keep 3-4 most relevant bullets per kept role, ranked by match analysis.
- [ ] **Letter quality evals** — no tests for letter tone/length/personalisation yet; risky to ship without.
- [ ] **Reuse company research across applications** to the same company within N days.
- [ ] **Batch dry-run mode** — paste 10 URLs, get ranked fit report.
- [ ] **Auto-detect candidate voice** from master CV style (first/third person, formality) and mirror in letters.
- [ ] **Multi-CV support** — pick the best base CV per job when a user maintains several.
- [ ] **Email-driven status updates** via Gmail MCP.
- [ ] **Deadline reminder skill** via gcal MCP.
- [ ] **Audit `job-stats` and `job-status`** for Eddie-specific assumptions; apply Phases 1 and 3 to them too.

---

## Decision log

When you make a judgment call on this roadmap, append a line here so future sessions (and future-you) know why.

- *2026-04-10 — Put user data under OS-standard dirs (XDG / Library / APPDATA), not `~/.claude/...`, because Claude's own config dir is for Claude Code settings, not third-party plugin data.*
- *2026-04-10 — CV addendum is a per-run enrichment layer, NOT a fact base cache mutator. Keeping them separate protects the verification script invariant that the cache reflects the raw docx.*
- *2026-04-10 — Adopted TDD for every phase. Rule: no implementation until the test exists, is runnable, and fails for the right reason. Rationale: the vital user data is gitignored, so a silent bug in path resolution or migration is unrecoverable from git alone. Writing the test first forces the safety invariant to be explicit. Added a Phase T (test harness baseline) that must complete before Phase 0.*
- *2026-04-10 — Phase 1 ships user customization as two files: `resources/cv_addendum.md` (markdown, merged into the in-memory fact base at Step 5) and `resources/user_prefs.yaml` (loaded once at Step 0, passed into tailor_cv/letter/linkedin prompts). Both gitignored so per-user data never enters the repo. Loader lives in `scripts/user_customization.py`. Enforcement is split: the prompts describe the rules (so the model honours them) AND pure-Python validators (`find_forbidden_title_label_violations`, `find_team_context_solo_phrasing`) can run on the produced outputs as a belt-and-braces check. The validators follow the same pattern as `scripts/tailor_invariants.py` — no model calls needed in tests.*
- *2026-04-10 — Fact base cache cleanup: `resources/cv_fact_base.json` had the Fortran-to-C++ bullet baked in from the now-obsolete "save the enriched fact base back to the cache" instruction in the old Fortran memory. That violated Phase 1's invariant (cache = raw docx only). Removed the bullet from the JFC 1994 entry; verify_fact_base still passes; the addendum re-injects the bullet on every run. This means from here on the cache is ground truth against the docx, and the addendum is the sole mutable user layer.*
- *2026-04-10 — Phase T regression tests implemented via a pure-Python validator module (`scripts/tailor_invariants.py`) rather than direct snapshot comparison against produced `tailored_cv.json`. Rationale: the compression and training-in-education rules live in the `tailor_cv.md` prompt, not in Python — so there is no function to unit-test directly, and snapshot tests would require invoking the model (slow, non-deterministic, expensive). The validator encodes each rule as a pure check function that returns violation messages; fixtures exercise good and deliberately-broken tailored CVs. Future integration tests can run the model once per change and then reuse these validators on the output. Caught one real bug during bring-up: the load-bearing check was fooled by a company name appearing inside the consolidated "Earlier experience" line.*
- *2026-04-10 — Phase 2 PDF pipeline extracted from `generate_outputs.py` into its own module `scripts/pdf_pipeline.py` with three private helpers (`_try_docx2pdf`, `_try_libreoffice`, `_try_pandoc`). `convert_docx_to_pdf` resolves them at call time via module globals so tests can monkeypatch each converter independently without touching the loop. Total-failure path raises `PdfConversionError` (a new subclass of `RuntimeError`) with a multi-line message naming all three tools AND the DOCX path — the old code silently swallowed every failure. Still TODO: `requirements.txt` notes and the manual 5-platform smoke matrix, both of which don't belong in TDD and are tracked as open boxes on the roadmap.*

---

## Notes and learnings (append freely)

- The compression rule added earlier in this conversation depends on match analysis evidence naming pre-cutoff roles by company+dates. Phase 1's `cv_addendum.md` will need to be included in the fact base context that the match analysis reads, or its additions will be invisible to the load-bearing check.
- `job-stats` has a `skill_gap_trends` method that could feed a "suggested learning topics" satellite skill later.
- Windows file locking (seen during workspace cleanup) sometimes holds empty directories briefly; not a blocker but worth knowing.
