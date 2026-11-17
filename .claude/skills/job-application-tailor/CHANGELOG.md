# Changelog

## [Unreleased]

### Added — `gate offer` checks the analysis against the cached offer (2026-11-17)
- **Why.** The match rows are now built from the offer analysis, so a technology the analysis invents becomes a scored row. Of 102 offer packs since 2026-06-01 with a cached `raw_offer.md`, 14 listed a technology the offer never names: "C#" and "REST APIs" for an offer that says ".Net APIs", "REST APIs" in three more, "GitHub Copilot" for "Copilot", "JavaScript / TypeScript" for "JS/TS", "Agents IA" for an English offer's "AI agents". Until now `gate offer` checked the schema only.
- **Blocking** (`scripts/offer_trace.py`): each `technologies` item must be found in `raw_offer.md` — as written, ignoring spaces and hyphens ("PowerBI" = "Power BI"), through a known synonym, or word by word on five-letter stems with plural "s" ignored ("API REST" covers "REST APIs"). The skill lists are not checked: they paraphrase by design (212 items in 76 packs would fail).
- **Warning:** the raw text reads as English but `detected_language` is `fr` — 8 packs since June, the analysis prompt's market-signal flip. Stronger wording when the offer says French is not required (Brevo). Whether that case should switch the pack to English is still the user's open decision; the warning makes it visible at Step 3.
- **Prompt.** `analyze_job_offer.md`: copy technology names as written; don't infer, expand, specify or translate them.
- **Tests** — `tests/test_offer_trace.py` (14).

### Added — required skills missing, shown next to the fit score (2026-11-17)
- **Why, and why not weighting.** The question was whether required skills should weigh more in `overall_fit_pct`. Simulated on 144 offer packs: every scheme tried (required ×2; ×2 with preferred ×0.5; ×3 with preferred and responsibilities ×0.5) raised the mean score by 2–4 points, because the candidate matches required skills best (average credit 0.75 vs 0.49 for technologies); 19–44 packs changed fit level and 5–8 crossed the 50% cut-off. The outcome data (3 interviews, 27 rejections) can't tell the schemes apart, and one interview came with 4 required skills missing. Weighting would also amplify the model's required-vs-preferred call in Step 3 and invalidate the 50 / 70 / 85% thresholds. So the score stays unweighted and the knockout risk is shown on its own.
- **`match_summary.required_gap_count` / `required_gaps`**, computed by the gate's recount (`common.recount_match_summary`): the `required_skill` rows rated `gap`. Optional in the schema; older packs gain them the next time `gate match` runs. They reach `run_summary.json` with the rest of `match_summary`.
- **Interview prep.** The fit banner gains a line "Required skills missing: N (…)" (« Compétences requises manquantes : N (…) »); `gate interview` blocks a missing or wrong count, and skips packs analysed before the count existed. `SKILL.md` Step 4 has the count reported to the user with the score.
- **Tests** — recount test for the new fields; four `gate interview` tests.

### Changed — match rows are fixed by the offer analysis (2026-11-17)
- **Why.** `overall_fit_pct` = (direct + 0.5 × transferable) / rows, and the model chose the rows. On the 25 offer packs from 2026-10-21 to 2026-11-16 only 71% of the offer's skill / technology items had a row of their own; responsibility rows ranged from 1 of 6 to all of them; a missing technology folded into a transferable row earned half credit. The gate-gaps reruns saw the same offer move by up to 13 points.
- **Rule** (`scripts/match_rows.py`): one row per item of `required_skills`, `preferred_skills`, `technologies` and `responsibilities` (all of them), in that order, the item's text as `requirement` and its list as `category`; an item listed twice gets one row, under the first list. New `match-rows <folder>` prints the rows; `gate match` gains a blocking `match rows = offer items` check (missing, extra, duplicated or recategorised rows).
- **Missing technology = gap, now blocking.** `check_match_grounding.py`'s "offer technology without a `gap` row" was a warning; with one row per technology it is an error.
- **Lead-in wording.** The grounding tokenizer strips "strong interest in", "experience with", "maîtrise de", "intérêt pour"… before looking a skill up. "Experience or strong interest in SaaS" split on "or" had left "strong interest in SaaS" as one unknown tech token and blocked a grounded direct.
- **Effect, measured.** Two independent Step 4 runs on pack #166 (Trekea): same 35 rows, 64% and 67%; the six rows they rated differently are judgment calls (direct vs transferable, transferable vs gap). Scores change for every rerun pack, mostly because all responsibilities now count. Old packs fail `gate match` until rerun.
- **Tests** — `tests/test_match_rows.py` (6), a gate test for the row check, 2 lead-in tests; the grounding tests filter the now-blocking gap-row errors where they check something else.

### Added — rerun a whole pack in place (2026-11-17)
- **Why.** Asked to "rerun" three existing offer packs (full pipeline, same folder, same history row), the only route was improvisation. `preflight` always created a new folder, and `record-application` always inserted, so the original rows kept their old fit scores (#167 / #166 showed 68% / 66% while their packs said 66% / 63%) and nothing could refresh them.
- **`record-application <folder> --update <id>`.** Rewrites row `<id>` from the folder's `_prep/`, with the same derivation as a plain record: company, title, location, URL, domain, seniority, fit level and %, match counts, language, `org_type`, the cold profile snapshot, the folder path, and the skills (replaced, not appended). The id, `status`, `source`, `created_at` and every `application_events` row are left alone. A `--url` given on the first record is kept when `_prep/` has none. Prints each changed column; `--dry-run` previews. It refuses with exit 2 and writes nothing when the row is another company or another flow, or when the folder's fit prefix doesn't match the new score (the row's `fit_level` is read from the folder name, so `rename-with-fit` must run first). It also refuses `--supersede` combined with `--update`, and an unknown id exits 1. New DB method `JobHistoryDB.refresh_application()`.
- **`preflight --reuse-dir <pack>`** (replaces `--input`). Returns the usual JSON with `output_dir` / `prep_dir` on the existing pack and `"reused": true`, and creates no folder. A valid cache is copied over the pack's `_prep/cv_fact_base.json` and verified as usual. On `cache_stale` the pack's old fact base is renamed `cv_fact_base.prev.json` (reported as `previous_fact_base`), so a fact base extracted from a previous CV can't be picked up and re-blessed. It refuses a folder without `_prep/` or with the wrong `cold-` prefix for `--flow`.
- **Docs.** New "Rerunning a whole pack in place" sections in this `SKILL.md` and in `job-cold-prospect/SKILL.md`, and `$REUSE_DIR` in `job-prep-cv/SKILL.md`. They say what the rerun reuses (raw offer or research, company research, the cold role pick), what it skips (Step 3.5, Step 10, `rename-cold-folder`), the backup of `_prep/` first, and that the `--draft` gates re-take the humanizer snapshot.
- **Tests.** `tests/test_rerun_in_place.py` (16).

### Fixed — stale absolute `output_folder` paths broke id-based commands (2026-11-17)
- **Why.** `applications.output_folder` stores absolute paths. About 100 of 157 rows point at a path that doesn't exist on this machine (90 are `/sessions/<id>/mnt/…` from cloud sessions), although 94 of those packs are under `<project root>/output/` by the same folder name. `regenerate-outputs 159`, `rename-application <id>` and any other lookup by id failed with "Output folder does not exist".
- **Fallback.** New `scripts/paths.py` helpers: `stored_folder_name()` splits on both `/` and `\`, and `locate_output_folder()` / `resolve_output_folder()` fall back to `<project root>/output/<folder name>` when the stored path is gone. `_resolve_app_folder` (used by `regenerate-outputs`, `record-application`) and `rename-application` read the folder through them. The project-root rules moved from `preflight.py` to `paths.resolve_project_root()`, so preflight and the CLI find `output/` the same way.
- **`repair-output-folders`.** Reports how many rows are fine, how many are repairable by folder name and which packs are missing everywhere. It is a dry run by default: `--apply` snapshots the DB and then rewrites only the repairable rows. `--project-root` points it at another `output/`. To keep previews from filling `db-backups/`, `Command` gained `writes_if`, and the snapshot is taken only when it returns true.
- **Storage unchanged.** New rows still store absolute paths, and no schema migration was needed: the fallback works on the folder name, which is the portable part.
- **Tests.** `tests/test_output_folder_fallback.py` (11), plus a registry test that the dry run takes no snapshot.

### Added — claims rule 8: figures must be stated by a source (2026-11-17)
- **Why.** A test on a copy of pack #159: the tailored CV and the letter changed from "17 000+ sauvegardes" to "45 000+", plus an invented "j'ai dirigé une équipe de 12 personnes", passed `gate cv` and `gate letters`. The claims check read technologies, durations and intensity wording, but no other number. `factbase_consistency.py` closed the same hole for the fact base only (the "40+ → 100+" incident).
- **Rule.** In `scripts/claims_guard.py`, every number in the CV (all but the contact line), in a letter's `paragraphs` and in a LinkedIn `message` must be one the master CV or addendum states; a percentage needs a percentage in the source ("95-98%" backs both ends). Messages are `[figure] <file>: '<value>' ...`.
- **Not claims:** a figure in a negated clause ("je n'ai pas administré Microsoft 365"); the role's own figure in a clause that isn't first-person ("Acme, avec ses 650 collaborateurs, ..."); a number after the same name as in the offer or research (".NET 4.8"); a reference number of 5+ digits found there. Years, dates, call / commute times and durations (rule 7) are not figures. A count copied from the offer into a first-person clause ("j'ai dirigé une équipe de 12 personnes") stays a claim.
- **Role-side text.** `run_check` now also reads `raw_offer.md`, `company_research.md` and `raw_research.md` for the figures a letter may quote back.
- **Calibration.** On the 39 packs generated since 2026-10-01: no failure. On all 168: 73 fail, 71 of them only on figures the master CV no longer states (the old "40+" applications figure, 49 packs; a removed "City & Guilds 726" education line, 25) — true drift against today's CV, as expected for old packs. The other two are an unsourced "Microsoft 365" claim and "industrie 4.0" in a pack whose offer text was not cached.
- **Prompts.** `cv_rules.md` § Evidence ledger and the letter / LinkedIn prompts say figures are copied as the source states them.
- **Tests** — 27 cases in `tests/test_claims_guard.py` (rule 8 block); `tests/test_gate.py`'s sample master CV gains the education line its sample tailored CV carries.

### Added — humanizer guard: the style pass may not change the content (2026-11-17)
- **Why.** The first three packs rerun with the humanizer pass: one short letter gained a sentence no source supports ("L'équipe pouvait ensuite s'y retrouver sans moi"), and two runs edited the subject line and LinkedIn subject hints the pass is told to leave alone. Every gate passed.
- **`gate letters --draft` / `gate linkedin --draft`.** The run made on the draft, before the pass: same checks, and a passing run copies the stage's files to `_prep/pre_humanize/`. A failing draft run removes any older snapshot; `--draft` on another stage exits 2.
- **`humanizer guard` check** in the plain `gate letters` / `gate linkedin` (`scripts/humanize_guard.py`). Against the snapshot — blocking: a changed field outside the prose (anything but a letter's `paragraphs` or a LinkedIn `message`), an added number, an added name (a capitalised word that does not open a sentence, or one with an inner capital). Warnings: a number from the draft that is gone, and a sentence sharing less than half its content words with the draft. With no snapshot (plugin absent, older pack) the check passes with a note.
- **Limits.** The sentence check is a warning because wording alone cannot prove a new claim; a paraphrase built from the draft's own vocabulary is not detected. Calibrated on one real before/after pair (pack #159: no finding) and the invented sentence above (reported).
- **Prompts.** `prompts/humanize_pass.md` now runs draft gate → pass → final gate, and says how to re-baseline when a later fix needs a new fact. The six letter / LinkedIn prompts and both `SKILL.md` files follow it.
- **Tests** — `tests/test_humanize_guard.py` (14) and 7 gate tests in `tests/test_gate.py`.

### Changed — Step 9 also converts the motivation letter to PDF (2026-11-17)
- `generate_outputs.py` (behind `regenerate-outputs`) used to convert only the CV. A rebuild of a pack whose letter PDF came from an earlier build left that PDF beside the new DOCX with stale text, an easy wrong attachment. The letter DOCX now goes through the same `convert_docx_to_pdf()` fallback chain, `run_summary.json` gains `letter_pdf_file`, and `--skip-pdf` skips both. Applies to offer and cold packs.
- **Tests** — `test_pdf_built_for_cv_and_letter` in `tests/test_generate_outputs_html.py` (converter stubbed).

### Added — humanizer pass on letters and LinkedIn messages (2026-11-17)
- Letters, short letter and LinkedIn messages (offer and cold flows) go through the `humanizer:humanizer` skill after drafting and before their gate, per the shared `prompts/humanize_pass.md`. Style only: facts, length limits, team scope and the cold-flow hook are kept; skipped when the plugin isn't installed.

### Fixed — `list --company` required the full company name (2026-10-19)
- `JobHistoryDB.list_applications(company=...)` compared `company_norm` with `=`, so `list --company "opus"` returned "No applications found." while "Opus Recruitment Solutions" was in the DB. Resolving an application by company before a status change (the `job-status` workflow) then fell back to scanning the whole list. It is now a substring `LIKE` on the normalised name. `%` and `_` in the query are escaped and match literally; a query that normalises to an empty string (e.g. `_`) still matches nothing rather than every row. A short query can now return several companies — `job-status` already asks the user to pick when a lookup is ambiguous.
- **Tests** — `test_list_applications_company_matches_partial_name` in `tests/test_job_history_db_v3.py`.

### Fixed — subagent write-permission note named the wrong rule (2026-10-05)
- `SKILL.md`'s Steps 6/7 note said the tracked `.claude/settings.json` pre-approves `Write(output/**)`. The rule has been `Edit(output/**)` since `ad8478e`: Claude Code accepts `Write()` path rules but never consults them, while `Edit()` rules cover every built-in file-writing tool. Someone troubleshooting a denied subagent write by "confirming the rule is present" would have looked for, or re-added, a rule that does nothing. Verified with a headless run on project settings only, in default permission mode: writes under `output/**/_prep/` from both the main agent and a subagent were allowed without a prompt, and a control write outside `output/` was denied.

### Added — claims guard against over-claimed skills and wording (2026-10-05)
- **Why.** A run skipped the user's addendum and over-claimed: skills the master CV lists as "Familier / à approfondir" appeared as strengths, letters said "pratique quotidienne" of tools no source described as daily, and technologies from the job posting leaked into the skills table. The existing checks (`verify_fact_base.py`, `check_match_grounding.py`) guard the fact base and match matrix, not the generated prose.
- **`scripts/claims_guard.py merge <prep_dir>` — mandatory Step 3.9.** Writes `$PREP_DIR/cv_fact_base_merged.json`: cached fact base + addendum bullets (via the existing `merge_addendum_into_fact_base()`, so the hash-keyed cache is never mutated) + `addendum_skill_calibration` + `familiar_only_skills` parsed from the master CV. Runs before Step 4 so match analysis, tailoring, letters, LinkedIn and interview prep all read the same file.
- **`scripts/claims_guard.py check <prep_dir>` — mandatory Step 5.5.** Runs after the tailored CV and again after letters/LinkedIn; exit 1 blocks DOCX/PDF generation. Rules: (1) no intensity/frequency wording ("quotidien", "tous les jours", "daily") that no source supports; (2) familiar-only skills only under a "Familier / à approfondir" skills heading, never in tagline/summary/letters; (3) every core skill appears literally in the master CV or addendum; (4) master-CV qualifiers are kept ("Python (lecture/adaptation de scripts)"); (5) the consolidated "Expériences antérieures" bullet has one ordered "Employeur :" clause per company in its `metadata_line`, and an employer that also has a full entry carries a disambiguator such as "(Asnières)"; (6) a `job_offer_analysis.technologies` entry absent from CV + addendum must not appear in any output — unless the sentence admits the gap ("pas", "sans", "à apprendre", "reste à", "novice", "to learn"…). Broad words like "nouveau" are deliberately not exemptions: they would let "déployé Kubernetes sur un nouveau projet" through.
- **Prompts.** `tailor_cv.md`, `match_analysis.md`, `generate_motivation_letter.md`, `generate_short_letter.md` and `generate_linkedin_message.md` gain an evidence-discipline section pointing at the merged fact base; `match_analysis.md` caps familiar-only and calibration-limited skills at `transferable`; `tailor_cv.md` adds wording rules for the earlier-experience line.
- **Tests** — `tests/test_claims_guard.py` (15): each rule, addendum/calibration parsing, gap admissions allowed, and a regression test that "nouveau" does not exempt a false claim.

### Added — status history: schema v4 `application_events` (2026-07-28)
- **Status changes are now append-only history, not an overwrite.** Before v4 a status change replaced `applications.status` and bumped `updated_at`, so only the *latest* transition survived — an application at `interview` couldn't say when it was applied to, and "how long do employers take to reply?" was unanswerable. New `application_events` table (`application_id`, `status`, `occurred_at`, `note`) records every transition. `applications.status` stays the cached current value, so every existing query, index, and report keeps working untouched.
- **`--at` / `--note` on `update-status` and `bulk-status`.** `--at` records when a change actually happened (`2026-07-14`, `2026-07-14T09:30`, `today`, `yesterday`) rather than when the tool was told — without it a Friday catch-up makes four Monday applications look same-day and inflates every response-time figure. Dates before the application existed, or in the future, are refused: both are typos that would corrupt the history silently (the out-of-order case leaves `generated` as the newest event, so the row vanishes from `follow-up` and `response-time` rather than reporting something visibly wrong).
- **New reports** — `history <id>` (one application's timeline), `funnel` (applications that *ever reached* each stage, with conversion rates; legitimately larger than `stats --type status`, which can only see where things are *now*), `response-time` (days from applying to the employer's first move), `follow-up` (applications whose latest event is `applied` and that have gone quiet for 21+ days). `timeline` gains `--basis applied|generated` to bucket by when applications were *sent* rather than when packs were generated; the default is unchanged.
- **Migration backfills what is still knowable, and marks it.** Each row gets a `generated` event at `created_at`; rows whose status moved get their current status at `updated_at`; rows past `applied` (`rejected`/`interview`/`offer`) get an inferred `applied` event, because they demonstrably were applied to even though that event was overwritten — without it the funnel undercounted badly (on the first real migration, "ever applied" read 49 against a true 77). Every backfilled row carries a bracketed `[backfill]` marker, and `response-time` excludes them: their dates were inferred from generation dates, so a duration measured against one describes how long a pack sat around, not how fast anyone replied. That report therefore starts empty on a migrated DB and fills with real measurements. The backfill is guarded on an empty table, so reopening never double-inserts.
- **Tests** — `tests/test_job_history_db_v4.py`: migration shape per legacy row type, the inferred-`applied` rule (and that `dropped` is excluded from it, since dropping isn't applying), backfill marking and its exclusion from response times, a hand-typed note that can't masquerade as a backfill marker, idempotency, forward event recording, both backdating guards, follow-up selection, timeline basis, and FK cascade. The v3 suite's version assertions now track `_SCHEMA_VERSION` instead of a hard-coded `3`, so a future migration doesn't fail tests about v3.

### Changed — reduce cross-document repetition in letters & LinkedIn messages (2026-06-16)
- The motivation letter, short letter, and three LinkedIn variants tended to reach for the same hero facts (e.g. "15+ ans C#/.NET", a backup-throughput figure) and the LinkedIn variants read like copies of each other. Added prompt rules: `generate_linkedin_message.md` now requires each variant to take a distinct angle (recruiter → fit/availability; hiring_manager → one concrete technical proof; internal_contact → a genuine question) and to vary which fact leads; `generate_short_letter.md` must lead with a different hook than the cover letter and not reproduce its sentences verbatim; `generate_motivation_letter.md` must not headline the same metric/phrase in more than one paragraph. Applies to all future runs, including the daily scheduled task. Existing packs unchanged (regenerate on demand per pack).


### Fixed — duplicate closing salutation in motivation letters (2026-06-16)
- `scripts/docx_generator.py::generate_letter_docx` now strips trailing body paragraphs that are empty, echo the `signoff`/sender name, or are a closing salutation, before appending the signoff block. The letter generator occasionally emitted the salutation (e.g. "Cordialement,") as the last `paragraphs` item AND in `signoff`, so the rendered DOCX showed it twice. `prompts/generate_motivation_letter.md` now also states the closing salutation belongs only in `signoff`, never in `paragraphs`. Regression test: `tests/test_letter_signoff_dedup.py`.


### Added — network-FS-safe history DB with cross-process locking (2026-06-16)
- **Local mirror + verified write-back.** `JobHistoryDB` now operates on a fast local-disk mirror and copies back to the canonical file only at open and close. SQLite's file locking and rollback journals are unreliable on networked/mounted filesystems (NFS/SMB/9p, many container/VM mounts), which produced `disk I/O error` and `database disk image is malformed`. Each write-back is integrity-checked *off-mount* before and after the swap and retried; a copy that fails to verify is discarded, so a healthy target is never replaced by a corrupt one (the mirror stays the durable copy if all retries fail).
- **Re-entrant cross-process lock.** Each instance holds an exclusive advisory lock (`fcntl` on POSIX / `msvcrt` on Windows, auto-released if the process dies) on a *local* lockfile for its lifetime, serialising the open → operate → write-back critical section across processes so parallel writers can't interleave, lose updates, or duplicate rows. Re-entrant within a process (refcount registry) so it can't self-deadlock; fail-safe — if the lock primitive errors or a 60 s wait times out, the DB still opens (degraded) rather than blocking the tool.
- **Tests** — `tests/test_db_concurrency.py`: lock re-entrancy; serialisation proven via non-overlapping critical-section intervals of parallel subprocess writers; and a teeth test confirming the serialisation assertion *fails* when the lock is disabled (so it isn't vacuous).
- **Docs** — new SKILL.md "Database durability & concurrency" section documents the design and its single-machine boundary (it does not coordinate writers across different hosts). The corruption-recovery note now says to salvage rows row-by-row off-mount first and only delete-and-backfill as a last resort, since backfill can't recover history whose output folders were cleaned.

### Added — `technologies_to_deepen` proficiency tier (2026-06-16)
- **New optional `technologies_to_deepen` field** in `schemas/cv_fact_base.schema.json`. Skills the master CV marks "Familier / à approfondir", or tech only *evaluated and not adopted* (e.g. Kafka when RabbitMQ was chosen), were being flattened into `technologies` and then promoted into core CV skill groups — overstating proficiency. `prompts/extract_cv_data.md` now routes such items into `technologies_to_deepen` (and keeps them out of `technologies`); `prompts/tailor_cv.md` renders them only in a clearly-labelled trailing "Familier / à approfondir" (FR) / "Familiar / to deepen" (EN) section, never a core group, and never presents evaluated-not-adopted tech as a held skill.

### Fixed — grounding tokenizer false positives on compound tech labels (2026-06-16)
- `scripts/_grounding_common.py::split_tokens` now splits parenthetical sub-lists and version ranges, drops bare version/number tokens, and explodes synonym-bearing compounds — so e.g. "C# .NET Framework (3.5 à 4.8)" grounds as `c#` + `.net` instead of being flagged as a single ungrounded token. Removes the recurring false-direct positives that forced requirement labels to be reworded on most runs, while leaving genuinely-ungrounded tech (e.g. RabbitMQ) correctly flagged.

### Fixed — PDF generation docs (2026-06-16)
- SKILL.md error-recovery item 6 corrected: PDF is **cross-platform** (`docx2pdf` → LibreOffice → `pandoc`) and does NOT require Microsoft Word. Removes the misleading "PDF requires Word" wording that caused blanket `--skip-pdf` / DOCX-only output on Linux/CI where the LibreOffice fallback is available.

### Added — aggregator platforms `LesJeudis`, `Station F` (2026-06-16)
- `config/settings.default.yaml § aggregators.known_platforms` += `LesJeudis`, `Station F`. Both surfaced as posting fronts for real employers (Estreem behind LesJeudis, Sekoia behind Station F), so real-employer detection now catches them automatically.

### Changed — repository line-ending normalisation (2026-06-16)
- Added root `.gitattributes` (`* text=auto eol=lf`; binaries marked `binary`; `.bat`/`.cmd` kept CRLF) and set `core.autocrlf=input`. Windows editors had been rewriting tracked files with CRLF, surfacing whole files as EOL-only "modifications". The working tree was normalised to LF; the tracked `.docx` templates were verified byte-identical (binary).


### Added — `dropped` application status (2026-05-26)
- **New `dropped` status** across the CLI and history DB. `cli.py update-status` accepts it as a positional choice, `list --status` documents it, and `JobHistoryDB.update_status()` adds it to its `valid` set. `references/cli.md` regenerated to match; `job-status/SKILL.md` (description + workflow), root `README.md`, and `job-stats/README.md` updated to list it.
- **Dropped applications are excluded from duplicate detection.** `find_duplicates()` now appends `AND status != 'dropped'` to all three checks (exact URL, company+title, company+skill overlap). Rationale: once the user explicitly walks away from a role, a fresh application to the same company/title/URL should not be blocked or warned against. Use `dropped` for jobs you've decided not to pursue.
- **Tests** — `tests/test_dropped_status.py` (6 tests): `update-status` accepts `dropped` / still rejects garbage, each of the three duplicate checks excludes a dropped row (with a live-row control), and a live row is still detected alongside a dropped one to the same company+title. Suite: 175 pass / 2 skip.

### Added — cold-flow slug rebuild helper (2026-05-14)
- **`scripts/common.py::rename_cold_folder_with_canonical_name(folder, canonical_name)`** — companion to `rename_folder_with_fit`. Detects the `cold-DDMMYYYY-` prefix on a cold-prospect output folder, rebuilds the trailing slug via `auto_slug(None, canonical_name)`, renames atomically, and returns the new path. No-op when the slug already matches; raises `FileExistsError` on collision rather than overwriting. Used by `job-cold-prospect` Step 3 to replace the URL-derived placeholder slug with a readable one once research has resolved the canonical company name. See `job-cold-prospect` CHANGELOG 0.10.0 for the full motivation.
- **4 new tests in `tests/test_folder_naming.py`** covering the LinkedIn-URL → canonical-name rename, idempotency, collision refusal, and the defensive no-op on non-cold folders. Folder-naming suite goes from 9 to 13.

### Added — CLI signature drift protection (2026-05-07)
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
