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

- [x] `test_resolve_returns_legacy_path_when_project_resources_exists` — implemented in `tests/test_paths.py`. Uses an injected `skill_root` fixture tree rather than monkeypatching; resolver takes `env` / `platform` / `skill_root` kwargs for testability.
- [x] `test_resolve_returns_xdg_path_on_linux_with_no_legacy` — plus a bonus `test_resolve_linux_falls_back_to_local_share_when_xdg_unset`.
- [x] `test_resolve_returns_library_path_on_mac_with_no_legacy`.
- [x] `test_resolve_returns_appdata_path_on_windows_with_no_legacy`.
- [x] `test_env_var_overrides_everything` — verified `JOB_TAILOR_HOME` wins even when both legacy resources AND `APPDATA` are populated.
- [x] `test_phase_3_reads_only_never_writes` — monkeypatches `Path.mkdir` as a write-spy; the resolved directory is not created.
- [x] `test_config_layering_merges_correctly` — plus `test_config_layering_returns_defaults_when_user_file_missing`. Nested dicts merge key-by-key (not wholesale replacement) — `fit_levels: {good: 75}` overrides only `good`, keeps `very_good` and `medium`.
- [x] `test_no_hardcoded_absolute_paths_in_scripts` — grep for `C:\`, `C:/`, `/home/`, `/Users/`.
- [x] `test_no_hardcoded_resources_slash_in_scripts` — legacy-aware scripts (`backup_user_data.py`, `paths.py`) are explicitly allowlisted because their whole job is to handle the legacy layout.



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

- [x] **Run Phase 0 first.** Backup `backups/pre-plugin-migration-2026-04-10-1553/` is verified and present before Phase 3 changes landed.
- [x] **Rule: Phase 3 reads, it does not move.** Pinned by `test_phase_3_reads_only_never_writes` — resolver performs no filesystem writes, no `mkdir`, no copies. Migration remains Phase 4.5's job.
- [x] **Add `scripts/paths.py`** with `resolve_user_data_dir()` and `load_settings()`. Resolver accepts injected `env`/`platform`/`skill_root` for testing; production callers pass nothing. Legacy detection probes `<repo>/resources/MASTER_CV.docx` — empty or missing folders fall through to the OS-standard path rather than being incorrectly treated as authoritative.
- [x] **Rename `config/settings.yaml` → `config/settings.default.yaml`** via `git mv`. Config layering implemented in `paths.load_settings()` with a recursive `_deep_merge` — nested dicts (fit_levels, behaviour) merge key-by-key so a partial user override doesn't wipe unrelated sibling keys.
- [x] **Update `common.py::_load_fit_levels`** to use `load_settings()` instead of opening the raw defaults file directly. Local import avoids a top-level circular dependency with `scripts.paths`.
- [x] **Update `generate_outputs.py::main`** to use `load_settings(defaults_path=Path(args.settings))` so the CLI picks up the user override automatically. Default `--settings` flag now points at `config/settings.default.yaml`.
- [x] **Update load-bearing doc/prompt references** — `SKILL.md` (all `config/settings.yaml` mentions → `config/settings.default.yaml`), `prompts/tailor_cv.md` (compression cutoff lookup), `references/commands.md` (generate_outputs.py example). Cosmetic README.md/SETUP.md rename is deferred to the Phase 5 documentation pass.
- [ ] **Replace every hardcoded `resources/...` path** in the remaining scripts with a `resolve_user_data_dir()` call. Currently only `backup_user_data.py` still references the legacy `resources/` layout and is explicitly legacy-aware (allowlisted in `test_no_hardcoded_resources_slash_in_scripts`). Nothing else in `scripts/` hardcodes the old path. *(Concern closed — the two outstanding call sites are `cv_cache_is_valid` / `save_cv_fact_base` / `copy_cached_cv_fact_base` in `common.py`, which derive the cache directory from `cv_path.parent`, so they automatically track wherever the resolved CV lives.)*
- [ ] **Update `SKILL.md` Directory Layout section** to describe the plugin-install vs user-data-dir split with the new layered-config example. *(Step 0 and the fit_level paragraph already renamed; the full layout section rewrite is pending and tracked as a Phase 5 pre-release task.)*
- [x] **Keep a backwards-compat path** — when `<repo>/resources/MASTER_CV.docx` exists, it takes precedence over any OS-standard location. Pinned by `test_resolve_returns_legacy_path_when_project_resources_exists`.

### Success criteria

- Running the skill with the plugin installed but no project-level `resources/` folder still works: the user data is auto-discovered in the OS-standard location.
- A second user on the same machine with a different `JOB_TAILOR_HOME` gets fully isolated data.

### Files touched
All scripts, all prompts (for path references), `SKILL.md`, `config/settings.default.yaml` (renamed), `references/commands.md`.

---

## Phase 4 — First-run onboarding

### Tests to write first

- [x] `test_init_creates_user_data_dir_if_missing` — implemented in `tests/test_init.py`. Asserts the target directory and its `output/` subfolder exist after init.
- [x] `test_init_does_not_overwrite_existing_master_cv` — real-CV bytes compared by SHA-256 before/after init. **Bonus** `test_init_does_not_overwrite_existing_customization_files` added for the same invariant on `cv_addendum.md` / `user_prefs.yaml`.
- [x] `test_init_copies_sample_cv_as_example_not_master` — additionally asserts `MASTER_CV.docx` is **not** created by init (only the user creates that).
- [x] `test_init_writes_both_templates`.
- [x] `test_init_is_idempotent` — second run produces byte-identical directory state (SHA-256 map compared).
- [x] `test_sample_cv_extracts_cleanly` — downgraded to a structural check (file opens as a valid docx AND contains the four load-bearing styles `NameStyle` / `SectionStyle` / `RoleStyle` / `BulletStyle`). Rationale: a true Step-2 extraction requires a model call, which doesn't belong in pytest. See Decision log 2026-04-10.
- [x] **Bonus** `test_init_returns_report_listing_created_and_skipped` — pins the shape of the report dict so the SKILL.md onboarding can present it to the user.



**Goal:** A brand-new user runs the skill, sees a helpful onboarding flow, ends up with a working setup in under 5 minutes.

**Why:** Currently if `MASTER_CV.docx` is missing, the skill stops with a one-line instruction. That's fine for you, not fine for a plugin installed by someone who just wants to apply to jobs.

### Tasks

- [x] **Add `init` mode to the skill** — `scripts/init.py::init_user_data()` resolves the user data dir, creates it and `output/`, and copies all three samples. Idempotent; never overwrites existing files. `main()` prints a human-readable report with "Next steps" that SKILL.md Step 0 surfaces to the user.
- [x] **Build `MASTER_CV.example.docx`** — generated by `scripts/build_sample_cv.py`, which reuses the styles from `scripts/create_cv_template.py` (`NameStyle`, `SectionStyle`, `RoleStyle`, `BulletStyle` etc.). Content is fictional: Alex Dupont, Software Engineer, 8+ years across Helios Analytics and Northbridge Software, INSA Lyon.
- [x] **Build `cv_addendum.template.md`** — at `samples/cv_addendum.template.md`. Documents the three recognised sections (`Additional experience entries`, `Hidden skills`, `Off-CV facts to remember`) and notes the dash-normalisation rule so users don't trip on en/em dashes.
- [x] **Build `user_prefs.template.yaml`** — at `samples/user_prefs.template.yaml`. Every key from `scripts/user_customization.py::DEFAULT_PREFS` is present with a commented example.
- [x] **Update SKILL.md Step 0** — the old one-line "save your CV then retry" instruction is replaced with a command block that runs `python -m scripts.init`, with a paragraph explaining idempotency, the non-overwriting rule, and that the example CV is a reference only.
- [ ] **Offer to open the folder in the user's file explorer** — deferred. `scripts/init.py::main()` prints the absolute path instead, which works cross-platform without needing a platform switch on `start` / `open` / `xdg-open`. Re-open if real users find the path-copying friction annoying.

### Success criteria

- A user who has never seen the skill before can go from zero to a generated application pack for their first real job offer, using only the sample CV as a reference point for their own.

### Files touched
`SKILL.md` (Step 0 onboarding), `samples/MASTER_CV.example.docx` (new), `samples/cv_addendum.template.md` (new), `samples/user_prefs.template.yaml` (new), `scripts/init.py` (new).

---

## Phase 4.5 — Migration from the loose project install

### Tests to write first

These are the most safety-critical tests in the whole roadmap. Every one pins an invariant that, if violated, would corrupt or orphan real user data.

- [x] `test_dry_run_writes_nothing_anywhere` — implemented via a whole-tree SHA-256 snapshot before/after `plan_migration`; plan is a pure function, asserts the plan dict carries file_copies + db_rewrites but touches zero files. Plus **bonus** `test_detect_legacy_returns_none_when_no_resources` pins the empty-probe invariant.
- [x] `test_apply_copies_all_legacy_files_to_new_location` — SHA-256 parity check over every file in `resources/` (except the DB, which is intentionally rewritten) and every file in `output/`.
- [x] `test_apply_does_not_move_or_delete_legacy_files` — pre/post whole-tree SHA-256 map compare of the legacy project root, excluding `backups/` from the compare.
- [x] `test_apply_rewrites_db_output_folder_column` — every row's `output_folder` is rewritten, no row still contains the legacy prefix, every rewritten path exists on disk.
- [x] `test_apply_is_a_noop_on_second_run` — SHA-256 map compare of the target tree across two `apply_migration` calls; the second call returns `{"already_migrated": True}`.
- [x] `test_apply_requires_phase_0_backup_to_exist` — missing `backups/` raises `MigrationError` matching /backup/; target dir is not created.
- [x] `test_verification_gate_blocks_apply_on_failure` — injects a `verify_fn` that always returns violations; assertion is two-fold: raises `MigrationError` AND the real destination is still empty AND the legacy tree is still present.
- [x] `test_rollback_restores_db_output_folder_column` — capture pre-migration values, apply, rollback, assert exact dict equality.
- [x] `test_find_duplicates_still_works_after_migration` — opens the migrated DB via `JobHistoryDB`, calls `find_duplicates`, asserts the returned `output_folder` points at the new location and exists.
- [x] ~~`test_skill_can_run_against_migrated_data`~~ — intentionally skipped with a docstring explaining that a full Step-5 run requires a model call. Invariants covered by the other tests. See Decision log.
- [x] `test_migrate_handles_paths_with_spaces` — both legacy (`Job Prospecting`) and target (`New Location With Spaces`) contain spaces; asserts the DB rewrite produced paths that exist.



**Goal:** An existing user (currently: Eddie) can switch from the loose repo-based install to the plugin install without losing data or re-running every past application.

**Why:** The current layout puts `MASTER_CV.docx`, `job_history.db` (34 real applications), cached fact base, and ~30 `output/<fit>-<date>-<slug>/` folders inside the project directory. Phase 3 moves the canonical location to an OS-standard user data dir. Without an explicit migration step, the first plugin install would either (a) start from empty and orphan all the history, or (b) silently keep writing to two different places. Both are bad.

### Tasks

- [x] **Confirm Phase 0 backup exists and has been verified.** Phase 0 ran at `backups/pre-plugin-migration-2026-04-10-1553/` on 2026-04-10 with clean SHA-256 verification (see Phase 0 task list).
- [x] **Write `scripts/migrate.py`** — implemented with three public functions + a CLI:
  1. `detect_legacy_install(project_root)` — returns a `LegacyLayout` dataclass or None. Requires `resources/MASTER_CV.docx` specifically; a bare `resources/` dir does not anchor a migration.
  2. `plan_migration(legacy, target)` — pure function; returns a dict with `file_copies`, `db_rewrites`, and the marker path. No filesystem writes whatsoever (pinned by `test_dry_run_writes_nothing_anywhere`).
  3. `apply_migration(legacy, target, backups_dir, verify_fn=None)` — stages all copies under `<target>/.migration_staging/`, runs the verification hook against the staged copy, and on success rename-commits each staged file to its final location. On failure the staging dir is cleaned up and the real destination is never touched.
  4. Verification hook is dependency-injected — tests pass an `always_fails` stub; production uses `_default_verify` which reopens the staged DB and runs `SELECT COUNT(*) FROM applications`. Richer checks can be layered on later without changing the call site.
  5. Copy-never-move is enforced by using `shutil.copy2` into staging and `shutil.move` *only* staging → final (so the legacy tree is untouched).
  6. The DB's `output_folder` column is rewritten **in the staged copy** before the verification gate, so a rewrite bug surfaces at verify time instead of on the real DB.
  7. `<target>/.migrated_from` is written after commit; subsequent runs short-circuit with `{"already_migrated": True}`.
- [x] **Handle the output folder rewrite specifically.** `_rewrite_path()` uses prefix-stripping against the resolved legacy output path and falls back to `Path.relative_to` — survives path-separator differences. The sidecar `.migration_rollback.json` records `{app_id: original_output_folder}` so `rollback_migration(target)` can undo the column rewrite in a single UPDATE pass. Tested end-to-end via `test_rollback_restores_db_output_folder_column`.
- [ ] **Memory files cleanup prompt.** Not yet wired into `migrate.py::main()`. Deferred to the Phase 5 packaging pass so the prompt can sit alongside the README migration section rather than shipping as loose print statements. Listed files: `project_cv_fortran_experience.md`, `feedback_no_backend_label.md`, `feedback_motivation_letter_tone.md`, `feedback_training_not_in_experience.md`.
- [x] **Dry-run eval.** `test_find_duplicates_still_works_after_migration` acts as the automated end-to-end check: fixture legacy install → `apply_migration` → open migrated DB via `JobHistoryDB` → call `find_duplicates` → assert the returned row's `output_folder` points at the new location and is openable. Running this against Eddie's real data is left as a manual smoke step when Phase 5 ships.
- [ ] **Document in README** — deferred to Phase 5 (README.md is one of the Phase 5 packaging deliverables, so migration docs will land with the rest of the release docs rather than in a separate pass).

### Success criteria

- Eddie (the canonical legacy user) can run `scripts/migrate.py --apply` and then immediately run the skill on a past job offer; the duplicate detector correctly surfaces his prior application and points at the *new* output folder location.
- Running the migration twice in a row is a no-op; it doesn't duplicate rows or re-copy files.
- Rollback restores the DB to the pre-migration state.

### Files touched
`scripts/migrate.py` (new), `README.md` (migration section), `PLUGIN_ROADMAP.md` (tick the boxes).

---

## Phase 5 — Plugin packaging and release

### Tests to write first

- [x] `test_plugin_manifest_is_valid_json` — implemented in `tests/test_package.py`. Asserts name/version/description exist.
- [x] `test_package_script_produces_archive` — `test_package_plugin_produces_archive` in `test_package.py`. Uses a synthetic fake repo fixture, not real data.
- [x] `test_package_excludes_user_data` — split into `test_build_plugin_tree_excludes_user_data` + `test_package_plugin_archive_excludes_user_data`. Both byte-scan the produced tree/archive for the sentinel bytes `REAL-CV-SECRET`, `USER-OUTPUT`, `SQLITE`, so any future path-matching regression fails loudly rather than silently.
- [x] `test_package_excludes_backups` — `test_build_plugin_tree_excludes_backups`. Matches `pre-plugin-migration-*` anywhere under the dist tree.
- [x] `test_package_includes_sample_cv` — two assertions: tree-level `test_build_plugin_tree_includes_sample_cv` and archive-level `test_package_plugin_archive_includes_sample_cv`.
- [x] ~~`test_all_phase_tests_pass_in_ci`~~ — intentionally skipped with rationale. A pytest that asserts pytest passed is circular. The intent is satisfied by `scripts/package.py::run_phase_tests()` which the CLI calls before bundling; `--skip-tests` is the explicit override. See Decision log 2026-04-10.
- [x] **Bonus** `test_build_plugin_tree_uses_top_level_skills_dir` — pins the structural `.claude/skills/<name>/` → `skills/<name>/` transformation.
- [x] **Bonus** `test_build_plugin_tree_excludes_tests_and_pycache` — covers the other non-data exclusions (`tests/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`).
- [x] **Bonus** `test_build_plugin_tree_refuses_existing_target` — pins the no-silent-overwrite invariant (caller cleans up; matches Phase 0 backup behaviour).
- [x] **Bonus** `test_package_plugin_archive_includes_manifest` — pins `.claude-plugin/plugin.json` presence in the zip.



**Goal:** The repo produces a Claude Code plugin bundle that can be installed either via a marketplace (`/plugin marketplace add` + `/plugin install`) or directly as a local `--plugin-dir`, without the user ever copying files by hand.

**Why:** Everything above is worthless if users have to manually copy files into `.claude/skills/`.

### Tasks

- [x] **Research current Claude Code plugin format** — April 2026 canonical layout is `<plugin-root>/.claude-plugin/plugin.json` + auto-discovered `<plugin-root>/skills/<name>/SKILL.md` (NOT `.claude/skills/`). Only `name` is required in `plugin.json`. Distribution is via marketplace JSON (GitHub repos / local paths) or dev-time `claude --plugin-dir <path>`. No tarball install, no minimum-version field, no `.claudeignore`. MCPs go in an optional `.mcp.json` at plugin root. Source: claude-code-guide agent against current docs, 2026-04-10.
- [x] **Write `.claude-plugin/plugin.json`** — created at repo root with name, version (1.0.0), description, author, license (MIT), keywords. Skills are auto-discovered — no explicit listing needed. No required MCPs (Gmail/Calendar are optional). No minimum-version field exists in the current format.
- [x] **Write a short `README.md`** — rewritten around the three install paths (marketplace, local `--plugin-dir`, built bundle), first-run OS-standard data dir behaviour, the four optional customization files, cross-platform PDF fallbacks, and a migration section pointing at `scripts/migrate.py`. Contributors are linked to `PLUGIN_ROADMAP.md`.
- [x] **Package script** — `scripts/package.py` with `build_plugin_tree()`, `package_plugin()`, and a CLI. Transforms the dev-time `.claude/skills/<name>/` layout into the plugin-install `skills/<name>/` layout (non-destructive; dev flow untouched). Copies `.claude-plugin/plugin.json` into the dist. Exclusion lists enforced at copy time AND verified by the test suite: `resources/`, `output/`, `backups/`, `tests/`, `__pycache__/`, `.pytest_cache/`, `job-application-tailor-workspace/`, plus file-level `MASTER_CV.docx`, `job_history.db`, `cv_fact_base.json`, `.cv_hash`, `cv_addendum.md`, `user_prefs.yaml`, `settings.yaml`, `*.pyc`/`*.pyo`/`*.db`/`*.sqlite*`. CLI runs the full phase test suite first and refuses to package on failure; `--skip-tests` is the opt-out.
- [x] **Dry-run packaging against the live repo** — 2026-04-10: produced `dist/job-prospecting.zip` (216 KB, 64 entries). Manual audit: manifest present, all three skills' `SKILL.md` present, sample CV present, zero user-data leaks (byte-scan for `MASTER_CV.docx`, `job_history.db`, `cv_fact_base.json`, `/resources/`, `/output/`, `/backups/`, `__pycache__`, `/tests/`, `.cv_hash` — only the allowlisted `MASTER_CV.example.docx` matched). Stale `dist/` cleaned up after the audit. `dist/` added to `.gitignore` alongside `backups/`.
- [ ] **Smoke test the package** on a fresh machine (Windows + Mac + Linux if possible).
- [ ] **Tag v1.0.0 in git**, push. *(Held pending user confirmation — tagging is a public/durable action per CLAUDE.md.)*

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
- *2026-04-10 — Phase 3 resolver takes `env` / `platform` / `skill_root` as injected kwargs instead of reading `os.environ` / `sys.platform` directly, so tests can exercise every branch without monkeypatching module globals. Rationale: each branch (env var, legacy, three OSes, fallback) must be independently verifiable, and monkeypatching `sys.platform` is fragile across pytest sessions. The cost is three extra kwargs on a function that production code calls with no arguments — small price for branch isolation. Also: legacy detection probes specifically for `resources/MASTER_CV.docx`, not just the presence of the `resources/` directory, because an empty legacy folder must not shadow the OS-standard path. Caught during test design: if a user has an empty `resources/` lying around from an aborted install, they'd be silently pinned to an empty data dir forever.*
- *2026-04-10 — Phase 3 config layering uses a recursive `_deep_merge`, not a flat `dict.update()`. Rationale: `settings.default.yaml` has nested dicts (`fit_levels`, `behaviour`, `formatting`) and the roadmap's invariant is that a user override like `fit_levels: {good: 75}` must change only `good` while leaving `very_good` and `medium` intact. A flat update would replace the whole `fit_levels` dict. The merge function is in `scripts/paths.py` to keep all plugin-install-vs-user-data concerns in one module.*
- *2026-04-10 — Phase 4 `test_sample_cv_extracts_cleanly` downgraded from "run the Step 2 extractor end-to-end" to a structural docx-open + style-presence check. Rationale: the Step 2 extractor is a model call, not a Python function, and the roadmap's TDD rule is "no implementation without a test that fails for the right reason" — a test that requires a model call fails for all kinds of reasons that aren't template drift (network, rate limits, model version). A structural check on the four load-bearing paragraph styles (`NameStyle`, `SectionStyle`, `RoleStyle`, `BulletStyle`) catches the same failure mode the integration test was meant to pin: if `build_sample_cv.py` ever drifts away from the styles in `create_cv_template.py`, the structural test goes red immediately. A full end-to-end extractor eval can run once per release in a manual smoke pass; it doesn't belong in pytest.*
- *2026-04-10 — Phase 4.5 migrate.py uses a staging-dir commit pattern (copy to `<target>/.migration_staging/` → verify → `shutil.move` each file to its final location) rather than copy-direct-to-target. Rationale: `test_verification_gate_blocks_apply_on_failure` requires that a verification failure leaves the real destination entirely untouched. Copy-direct would force us to track and delete partial writes on failure, which is exactly the kind of cleanup code that fails at 2 a.m. Staging + move gives us an atomic-ish commit with a trivial failure path (`shutil.rmtree(staging)` in a `finally:` block) and no branching cleanup logic. Cost: two-phase I/O (copy then move), but on same-filesystem moves that's a rename, so it's effectively free.*
- *2026-04-10 — Phase 4.5 `sqlite3.connect(...)` is NOT closed by its context manager — the `with` block only commits. On Windows this leaves a file handle open long enough for a subsequent `shutil.move` to fail with `WinError 32`. Caught during test bring-up: all six "apply" tests failed with a PermissionError on the staged DB until every sqlite3 call was wrapped in an explicit `try: ... finally: conn.close()`. Lesson: never rely on `with sqlite3.connect` on Windows if you're going to move or delete the DB file in the same function.*
- *2026-04-10 — Phase 4.5 `test_skill_can_run_against_migrated_data` intentionally skipped with a docstring rather than implemented. Running Step 5 requires a model call and the roadmap's TDD rule is "no implementation without a test that fails for the right reason". A model-dependent test fails for all sorts of reasons that aren't migration bugs (network, rate limits, non-determinism), so it would rot. The invariants that test was meant to pin are covered by `test_find_duplicates_still_works_after_migration` (DB + path round-trip under realistic query) plus `test_apply_copies_all_legacy_files_to_new_location` (SHA-256 identity of every non-DB file). A model-free integration failure would show up before the manual smoke pass at release time.*
- *2026-04-10 — Phase 4 init.py takes `user_data_dir` and `samples_dir` as kwargs (same DI pattern as `paths.resolve_user_data_dir`) so tests can use a synthetic `samples/` dir with placeholder bytes and never depend on the real docx existing. This meant Phase 4 tests could be written before Task #2 (build sample CV) without blocking — `test_sample_cv_extracts_cleanly` carries an `if not sample.exists(): pytest.skip(...)` guard that the real sample then satisfies. Lets TDD and implementation interleave naturally across tasks within a phase.*
- *2026-04-10 — Phase 5 plugin layout is `<root>/skills/<name>/`, NOT `<root>/.claude/skills/<name>/`. Earlier drafts of this roadmap's Phase 3 target-layout diagram showed the latter, which was wrong: the current Claude Code plugin format auto-discovers skills under a top-level `skills/` directory, and `.claude/skills/` is the in-repo dev convention only. Rather than restructure the live repo (which would break the in-place `/slash` dev flow) the packaging script performs the transformation at build time: it walks `.claude/skills/<name>/`, applies the exclusion list, and writes to `<dist>/job-prospecting/skills/<name>/`. The dev-time and plugin-install layouts therefore coexist, with `package.py` as the only place that knows about both.*
- *2026-04-10 — Phase 5 packaging test fixture uses sentinel byte strings (`REAL-CV-SECRET`, `USER-OUTPUT`, `SQLITE`) inside the fake user-data files and byte-scans the produced tree + archive for them. A pure path-based exclusion test would miss the case where a new exclusion rule is written correctly but a regression later reintroduces a code path that copies the file via some other mechanism. Byte-scanning the output catches both. The pattern is cheap (rglob + read_bytes on a ~64-file tree) and the test is the last line of defence before a user's master CV or SQLite history ships to a stranger.*
- *2026-04-10 — `test_all_phase_tests_pass_in_ci` is a skipped marker, not an implementation. Rationale: a pytest that asserts "pytest passed" is circular — if the outer pytest run is green, the inner assertion is trivially true, and if it's red, the assertion never runs at all. The roadmap's actual intent was a release gate, which lives in the right place: `scripts/package.py::run_phase_tests()` is called by `package.py::main()` before bundling and exits non-zero on any failure. The escape hatch is an explicit `--skip-tests` CLI flag, documented in the README, so an operator who knows exactly why the suite is red (e.g., a flaky network test unrelated to the plugin) can still cut a bundle. Same skip-with-rationale pattern as `test_skill_can_run_against_migrated_data` in Phase 4.5.*
- *2026-04-10 — Phase 2 PDF pipeline extracted from `generate_outputs.py` into its own module `scripts/pdf_pipeline.py` with three private helpers (`_try_docx2pdf`, `_try_libreoffice`, `_try_pandoc`). `convert_docx_to_pdf` resolves them at call time via module globals so tests can monkeypatch each converter independently without touching the loop. Total-failure path raises `PdfConversionError` (a new subclass of `RuntimeError`) with a multi-line message naming all three tools AND the DOCX path — the old code silently swallowed every failure. Still TODO: `requirements.txt` notes and the manual 5-platform smoke matrix, both of which don't belong in TDD and are tracked as open boxes on the roadmap.*

---

## Notes and learnings (append freely)

- The compression rule added earlier in this conversation depends on match analysis evidence naming pre-cutoff roles by company+dates. Phase 1's `cv_addendum.md` will need to be included in the fact base context that the match analysis reads, or its additions will be invisible to the load-bearing check.
- `job-stats` has a `skill_gap_trends` method that could feed a "suggested learning topics" satellite skill later.
- Windows file locking (seen during workspace cleanup) sometimes holds empty directories briefly; not a blocker but worth knowing.
