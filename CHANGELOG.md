# Changelog

Build history for the job-prospecting toolkit. Kept out of the individual
`SKILL.md` bodies so those stay lean (a SKILL.md loads into context on every
trigger; historical notes don't need to ride along). Newest entries first
within each section.

## Unreleased

- **Gate gaps from the comparison runs (2026-11-17)** — skills in a tailored CV
  must come from the master CV's skills table or the addendum; two new addendum
  sections, `## Skill translations` (FR = EN pairs, so an English CV can list a
  skill the CV states in French) and `## Skill level caps` (skills a match row may
  rate at most `transferable`: Python at reading level, training-only tools); the
  interview prep's figures are checked; "qu'en formation" / "encore à approfondir"
  admit a gap; intensity words are checked only in sentences about the candidate;
  load-bearing older roles are found from a short name ("JFC (Asnières)"); the
  humanizer guard warns when the pass changed nothing; "R&D" is one token.

## v1.2.0 — 2026-11-17

Third release (git tags `v1.2.0` and `job-prospecting--v1.2.0`): a humanizer pass on letters and LinkedIn
messages behind a guard, figures checked against the CV, match rows fixed by the offer analysis with the
required skills missing shown next to an unweighted fit score, `gate offer` and `gate dossier`, rerunning a
pack in place, and letter PDFs. Everything below up to v1.1.0 is part of it.

- **Comparison-run fixes: one row per fact, example lists, read-only audits
  (2026-11-17)** — rerunning the last five packs with all of the above found
  four problems, now fixed. A technology a skill item already names ("Jira"
  next to "Jira, Confluence") no longer gets its own match row, so one fact
  isn't scored twice. Lists marked "etc." / "e.g." / "such as" / "comme" /
  "tels que" count as "one of these", like "ou" / "or". `gate --check` audits
  a pack without writing to it (`gate match` used to rewrite the file it
  checked). `gate interview` counts required skills missing from the match
  rows, so its result no longer depends on which gate ran first.
- **Cold flow: dossier gate, hook check, shared evidence rules (2026-11-17)** —
  `gate dossier` blocks an incomplete company dossier (length, the nine
  sections, Quick Reference / Why you / Research gaps, source links) and warns
  when the letter's opening and the first connection request share too few
  words to carry the same hook. The evidence rules now live once in
  `prompts/evidence_discipline.md`, used by the offer and cold letter,
  LinkedIn, interview-prep and dossier prompts (the cold ones had none).
- **`gate offer` checks the analysis against the cached offer (2026-11-17)** —
  a listed technology the offer never names ("C#" for a ".Net" offer, "GitHub
  Copilot" for "Copilot") is blocked, since each one becomes a scored match
  row; 14 of 102 packs since June had one. It also warns when an English offer
  is analysed as French.
- **Required skills missing, next to an unweighted fit score (2026-11-17)** —
  weighting required skills was simulated on 144 packs: every scheme mostly
  inflated scores and moved packs across the 50% cut-off, with no outcome data
  behind it. The score stays unweighted; `match_summary.required_gaps` and a
  "Required skills missing: N" line in the interview-prep banner carry the
  screening risk instead.
- **Match rows fixed by the offer analysis (2026-11-17)** — one row per
  required skill, preferred skill, technology and responsibility
  (`cli.py match-rows`); `gate match` blocks any other row set, and a
  technology the candidate lacks must be a `gap`. Two independent runs on the
  same offer now produce the same rows (64% / 67%; the spread is per-row
  judgment, where it used to reach 13 points).
- **Rerun a pack in place; stale folder paths (2026-11-17)** —
  `preflight --reuse-dir` and `record-application --update <id>` rerun a pack
  in its folder and refresh its history row without touching its status or
  history. Commands that take an id find packs whose stored path came from
  another machine; `repair-output-folders` (preview by default, `--apply`)
  fixes the rows.
- **Figures checked, humanizer pass fenced (2026-11-17)** — the claims check
  blocks any number in the CV, letters or LinkedIn messages that the master CV
  or addendum doesn't state. `gate letters|linkedin --draft` snapshots the
  draft before the humanizer pass; the gate after it blocks an added number or
  name or a changed field outside the prose.
- **Letter PDF (2026-11-17)** — the rebuild converts the motivation letter to
  PDF as well as the CV, so an old letter PDF can't sit next to a new DOCX.
- **Humanizer pass (2026-11-17)** — letters and LinkedIn messages (both flows)
  go through the `humanizer:humanizer` skill before their final gate; style
  only, skipped when the plugin isn't installed.
- **Backup: long paths (2026-11-02)** — `backup_user_data.py` copies files
  whose backup path exceeds Windows MAX_PATH instead of failing partway.
- **Bootcamp key skills on the education line (2026-11-02)** — a relevant
  training's line may end with "— compétences clés : X, Y, Z", taken from that
  training's own fact-base entry or the addendum.
- **Four gate gaps closed (2026-11-02)** — found by regenerating packs
  #144–#148: `gate cv` checks the timeline (recent roles in full, no training
  in experience, dateless earlier-experience line), `gate letters` the
  short-letter length, match grounding treats "X, Y ou équivalents" as
  alternatives, and a familiar-only skill may be named as a gap.

- **Interview prep runs in parallel, behind a new gate (2026-10-21)** —
  offer-flow Step 8 joins Steps 6 and 7 as a third parallel subagent, taking
  a serial LLM generation off the critical path. Interview prep is Markdown
  with no schema, so a new `cli.py gate interview` catches a missing,
  truncated or stale prep: at least 3,000 characters and 8 `##` sections, a
  Quick Reference block, and a fit-score banner within 1 point of
  `match_summary.overall_fit_pct`. Calibrated on 117 real packs, all of
  which pass. Speedup 2 of `docs/roadmaps/PIPELINE_SPEEDUPS_ROADMAP.md`.
- **Company research runs after the fit gate (2026-10-21)** — offer-flow
  Step 3.6 is now Step 4.5, between the fit gate and CV tailoring. Nothing up
  to Step 4 reads the research, so a run stopped below 50% and every dry run
  no longer pay for web searches whose results were thrown away. The
  `company_size` back-fill still lands before Step 5 reads it. Speedup 1 of
  `docs/roadmaps/PIPELINE_SPEEDUPS_ROADMAP.md`.
- **Docs fixes (2026-10-20)** — the addendum's `## Skill calibration` section
  is now documented (template, README, technical reference); the overview no
  longer claims a PDF motivation letter (only the CV gets a PDF) and its pack
  count is current; the `job-application-tailor` SKILL.md layout section
  describes the user data folder instead of only the old `resources/` layout;
  CLAUDE.md lists the docs-drift pre-commit check.

## v1.1.0 — 2026-10-20

Second release (git tags `v1.1.0` and `job-prospecting--v1.1.0`): the claims
guard, status history (schema v4), one `gate` command per pipeline stage, and
the marketplace catalog. Everything below up to v1.0.0 is part of it.

- **Two more gate checks (2026-10-20)** — `gate linkedin` now checks message
  lengths: a connection request over 300 characters (LinkedIn truncates it) or
  a direct message over 700 fails; offer-flow messages only warn over the
  prompt's 500. The claims guard gains rule 7, durations: every "N ans /
  années / mois / years / months", digits or spelled out ("trente ans"), must
  match a duration the master CV or addendum states, or one implied by a
  role's own dates ("Mars 2005 – Juin 2010" = 5 years). Ranges ("2 à 5 ans")
  are skipped, and a duration quoted from the offer or company profile passes
  outside a first-person sentence. Across the 141 existing packs it flags 8
  real problems ("17 ans chez Oodrive", "depuis trois ans" for a 2025 move,
  "12+ ans en C++") and no false alarms. Also: `cache-raw-offer` no longer
  garbles accents or line endings on Windows.

- **Skill simplification: one gate per stage (2026-10-20)** — a new
  `cli.py gate <stage> <folder>` runs every deterministic check for a pipeline
  stage in one call and reports all failures at once. Stages: `factbase`,
  `offer`, `match`, `cv`, `letters`, `linkedin` and, for the cold flow,
  `profile`, `roles`, `selected-role`. It replaces the separate validate /
  recount / grounding / forbidden-label / claims-check calls in the skills (the
  standalone scripts still work, for debugging), so the tailor's separate
  Step 5.5 claims check is gone — it now runs inside `gate cv`, `gate letters`
  and `gate linkedin`. The **cold flow now runs the claims guard** too: a new
  Step 3.9 builds the merged fact base, and with no job offer the contagion
  rule blocks `company_profile.tech_stack_hints` technologies absent from the
  CV and addendum. Cold Step 4 is now 4a (candidates + `gate roles`), 4b (ask
  the user), 4c (save the selection + `gate selected-role`). Claims guard: the
  hard-coded Python qualifier rule becomes "keep any qualifier the master CV
  puts on a skill", and addendum sentences that forbid or negate a skill no
  longer count as a source for it. Match grounding reads the merged fact base
  and refuses a `direct` on a familiar-only skill. Review fixes before merge: `match` / `roles` / `selected-role` fail when the merged fact base is missing instead of silently falling back; negated addendum lines ("Pas de X à ce poste") no longer ground X; negation is detected per clause ("no-code" is not a negation, `## Hidden skills` is never filtered); each gate checks only its own files and every claims message names its file; the earlier-experience check accepts English "Employer: …" typography; the offer flow re-runs `gate letters` / `gate linkedin` in the main context after the subagents return. `regenerate-outputs` is now
  the first-build command for both flows (cold-aware: title and language from
  `selected_role.json`, dossier instead of interview prep; new `--language` /
  `--job-title` overrides); `selected_role.json` gains a required `language`;
  new `read-cv` prints the master CV for extraction. A shared
  `prompts/cv_rules.md` holds the CV rules for both flows (the cold flow had
  drifted: it lacked the evidence ledger and the earlier-experience wording
  rules), and `tailor_cv.md` / `tailor_cv_cold.md` keep only their
  flow-specific parts. The SKILL.md files were rewritten around the gates
  (1207 → 615 lines); maintainer notes (DB durability, PDF converters,
  permissions) moved to `references/troubleshooting.md`. Also: the `job-status`
  frontmatter was invalid YAML, so the skill never auto-triggered — fixed; dead
  keys removed from `config/settings.default.yaml` (`paths.*`, `outputs.*`,
  `cv_filename_keyword`, `keep_*_roles_*`, top-level language keys) along with
  a duplicate Lesjeudis platform entry; `commands.md` reads the master CV from
  preflight's `master_cv_path` instead of a hard-coded
  `resources/MASTER_CV.docx`.

- **Partial company search (2026-10-19)** — `list --company` now matches part
  of a company name, case-insensitively: `--company opus` finds "Opus
  Recruitment Solutions" and `--company canal+` finds "CANAL+ Group". It used
  to require the full normalised name and silently returned nothing otherwise.
  Full detail in `.claude/skills/job-application-tailor/CHANGELOG.md`.

- **Claims guard (2026-10-05)** — a new `claims_guard.py` stops the offer flow
  from over-claiming. `merge` (mandatory Step 3.9, before match analysis)
  writes a per-run `cv_fact_base_merged.json` combining the cached fact base,
  the addendum, its skill-calibration notes and the master CV's
  "Familier / à approfondir" skills, so the addendum can't be skipped silently.
  `check` (mandatory Step 5.5, before any DOCX/PDF) blocks unsourced intensity
  wording ("au quotidien"), familiar-only skills sold as strengths, skills
  absent from CV/addendum, dropped qualifiers, job-posting technologies leaking
  into the output, and an earlier-experience line that blends technologies
  across employers. Full detail in
  `.claude/skills/job-application-tailor/CHANGELOG.md`.

- **Status history — schema v4 (2026-07-28)** — status changes are now appended
  to an `application_events` table instead of overwriting a single column, so an
  application's path through the pipeline survives. `update-status` /
  `bulk-status` gain `--at` (when it actually happened) and `--note`; four new
  reports arrive — `history`, `funnel`, `response-time`, `follow-up` — and
  `timeline` gains `--basis applied`. The migration reconstructs what pre-v4
  rows still support and marks every reconstructed row `[backfill]`, which
  `response-time` filters out because those dates were inferred rather than
  observed. `applications.status` stays the cached current value, so existing
  queries are unaffected. Full detail in
  `.claude/skills/job-application-tailor/CHANGELOG.md`.

- **Marketplace catalog (2026-07-15)** — `.claude-plugin/marketplace.json`
  makes the repo its own plugin marketplace (`ai-job-prospecting`). The plugin
  entry uses `source: "./"` with skill discovery overridden to
  `./.claude/skills/`, so the marketplace install reuses the dev layout — no
  committed dist tree. Live `/plugin install` flow verified on Windows in an
  isolated `CLAUDE_CONFIG_DIR`/`CLAUDE_CODE_PLUGIN_CACHE_DIR`: marketplace
  add → install (v1.0.0 resolved from `plugin.json`) → all five skills
  discovered (`job-prep-cv` correctly hidden) → headless
  `/job-prospecting:job-status` ran its CLI from the cached tree and honored
  `JOB_TAILOR_HOME`. Caveat documented in the README: adding a marketplace
  from a **local path** copies the working tree verbatim (ignores
  `.gitignore`) — test from a clean clone; GitHub installs clone the git tree.

## v1.0.0 — 2026-07-15

First tagged release (git tags `v1.0.0` and `job-prospecting--v1.0.0`, the
latter being the marketplace version convention). The packaged bundle passed
the Windows fresh-environment smoke test (onboarding → preflight → CLI →
schema validation → full DOCX/PDF pack); Mac/Linux smoke and the live
`/plugin install` flow remain open items in `PLUGIN_ROADMAP.md` § Phase 5.
Everything below is part of this release.

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
