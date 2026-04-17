# Skill Improvements Roadmap

Multi-session improvement plan for the `job-application-tailor` and `job-status` skills. Drafted 2026-04-17 after the Omnitech SA / Free-Work run surfaced several rough edges. Read this before starting work on any of the five items below — context matters for scope decisions.

## Context

**What already shipped** (commit `8671d27`, pushed to origin):

1. `scripts/generate_outputs.py` — `from scripts.paths` → `from paths` so it runs from `scripts/` without `PYTHONPATH`.
2. `JobHistoryDB.update_company()` + `update_output_folder()`, exposed via `cli.py` as `update-company` and `update-output-folder`.
3. `job-status/SKILL.md` documents the new commands.
4. `job-application-tailor/SKILL.md` adds a Write-permission note to Steps 6-7.
5. `.claude/settings.local.json` pre-approves `Write(output/**)` (local only, gitignored).

**What prompted the roadmap**: the offer at the centre of that session was posted by Free-Work (a platform/aggregator). Only after generation did we learn the real client was Omnitech SA, which required a manual rename dance across folder, DB, `_prep/*.json`, `run_summary.json`, `interview_prep.md`, `linkedin.json`, and `company_research.md`. The five items below aim to make that flow, and adjacent friction, cheap.

## Rollout order

Status checkboxes track progress across sessions. Each item is one commit so any of them can be reverted independently.

- [x] **#1. Audit import consistency** — ~30 min, no risk
- [ ] **#2. Detect platform-vs-real-client at Step 3** — ~1.5 h, high user value
- [x] **#3. Cache raw offer text** — ~20 min, trivial
- [ ] **#4. Atomic `rename-application` CLI wrapper** — ~2.5 h, composes #2's `source_platform` field
- [ ] **#5. `regenerate-outputs` CLI helper** — ~1 h, independent

Total budget ~6 hours. Suggested cadence:
- **Session A**: #1 + #3 + #5 (low-risk, high-utility)
- **Session B**: #2 (biggest recurring win)
- **Session C**: #4 (benefits from #2 being in place)

---

## #1 — Audit import consistency across `scripts/`

**Goal**: kill the same latent bug class that hit `generate_outputs.py`.

**Changes**:
- Grep `.claude/skills/job-application-tailor/scripts/*.py` for `from scripts\.` and `import scripts\.`. Any file mixing flat imports (`from common import …`) with package-style imports gets normalised to flat, matching post-fix convention.
- Entry points to smoke-test after: `cli.py`, `generate_outputs.py`, `backfill_history.py`, `verify_fact_base.py`, `init.py`, `validate.py`. Invoke each with `--help` from both the `scripts/` CWD and the skill-base CWD — both must succeed.

**No schema changes, no doc changes.**

**Effort**: 30 min.

---

## #2 — Detect "platform vs real client" in Step 3

**Goal**: catch aggregators at analysis time so you never have to rename after-the-fact.

**Changes**:

- `config/settings.default.yaml` — add:
  ```yaml
  aggregators:
    known_platforms:
      - Free-Work
      - Indeed
      - Welcome to the Jungle
      - LinkedIn
      - reservoirjobs
      - jooble
      - APEC
      - Hellowork
      - Monster
      - Glassdoor
      - France Travail
  ```

- `scripts/common.py` — new helper:
  ```python
  def is_aggregator(name: str, platforms: list[str]) -> bool
  ```

- `schemas/job_offer_analysis.schema.json` — add optional fields `company_is_aggregator: bool` and `source_platform: string`.

- `prompts/analyze_job_offer.md` — instruct the LLM to flag `company_is_aggregator` when the posting company matches the config list (or let the helper post-annotate after validation).

- `SKILL.md § Step 3` — when `company_is_aggregator=true`, prompt the user: *"Free-Work is a platform, not usually the employer. Who's the real client? (blank = proceed as-is)"*. If the user provides a name, rewrite `company_name` to the real client and preserve `source_platform="Free-Work"` for duplicate detection + history.

**Edge case**: user is legitimately applying TO the platform company (e.g. working at Free-Work itself). Provide a `--force-company` / "I really mean this one" escape hatch in the prompt.

**Effort**: 1.5 h.

---

## #3 — Cache raw offer text

**Goal**: audit trail + survives the posting getting pulled.

**Changes**:
- `SKILL.md § Step 3` — after WebFetch returns, write the full LLM response to `$PREP_DIR/raw_offer.md` before analysis. If the user pasted text instead of a URL, save that instead.
- `references/commands.md § Step 3` — document the one-line Python snippet.
- No schema change; `raw_offer.md` is a sibling of the `_prep/` JSONs.

**Effort**: 20 min.

---

## #4 — Atomic `rename-application` CLI wrapper

**Goal**: one command for the dance we did during the Omnitech session (rename folder → update DB → rewrite run_summary → patch job_offer_analysis → optionally regenerate outputs).

**Changes**:
- `scripts/cli.py` — new subcommand:
  ```
  rename-application <id> --new-company "<name>" [--new-slug "<slug>"] [--no-regenerate]
  ```
- Pipeline:
  1. `db.get_application(id)` — bail if missing.
  2. Derive new folder name: keep `{fit_prefix}-{date}-` and swap the slug portion (from `--new-slug` or auto-generated from `--new-company`).
  3. `os.rename(old_folder, new_folder)` — on Windows, catch `PermissionError` (file open in Word) and surface a clear message telling the user to close the doc.
  4. Compose the two primitives: `db.update_company()` + `db.update_output_folder()`.
  5. Rewrite `_prep/job_offer_analysis.json` → set `company_name` to new name. If #2 is in place and the old name was an aggregator, set `source_platform` to the old name.
  6. Rewrite `run_summary.json` paths (str-replace old folder → new folder).
  7. Unless `--no-regenerate`, re-run `generate_outputs.py` so filenames reflect any slug change.
- `job-status/SKILL.md` — document the command and explain **when to use it vs the two primitives**: primitives when you don't want the filesystem rename (just DB patch); this command when you want the whole atomic swap.

**Edge cases**:
- Folder already renamed manually on disk — detect by checking whether the old path exists; if not, skip step 3 and just update DB.
- Target folder already exists — refuse to overwrite, tell user to pick another slug.
- `generate_outputs.py` failure after rename — DB + filesystem are already consistent, so worst case user re-runs step 7 manually.

**Effort**: 2-3 h including Windows path-with-spaces testing.

---

## #5 — `regenerate-outputs` CLI helper

**Goal**: cut the 10-flag `generate_outputs.py` invocation down to one line; catch missing `_prep/` files early.

**Scope note**: LLM-driven regeneration (tailor/letter/linkedin/interview_prep) stays in the skill flow — a CLI can't invoke an LLM directly without adding an API-key dependency. This item is scoped to **Step 9 only**: deterministic doc rebuilding from existing `_prep/` JSONs.

**Changes**:
- `scripts/cli.py` — new subcommand:
  ```
  regenerate-outputs <app-folder-or-id> [--check] [--skip-pdf]
  ```
- Logic:
  1. Resolve the folder argument — accepts either an integer id (looked up in DB) or a path.
  2. `--check`: inspect `_prep/` and print which required JSONs + markdown files exist vs missing. Exit 0 if ready, 1 if missing anything.
  3. Default: read `detected_language`, `job_title` etc. from `job_offer_analysis.json`, assemble the 10-flag command, invoke `generate_outputs.py`. Pass `--skip-pdf` through.
- `SKILL.md § Re-running individual steps` — replace the manual-flag instructions for Step 9 with `regenerate-outputs`. Keep steps 5/6/7/8 as manual since they genuinely need the skill's LLM calls.

**Effort**: 1 h.

---

## Out of scope (for now)

Ideas that came up but were deemed bigger than this roadmap:

- **LLM-driven step regeneration via CLI** — would need API key plumbing, prompt assembly, token accounting. Real scope-creep. Skill flow handles this today; revisit only if manual regen becomes a recurring pain.
- **Auto-blacklist after N rejections** — a `job-stats` enhancement, not a job-application-tailor one. Separate roadmap item if ever wanted.
- **Structural fix to fit_level derivation in `Record Application`** — currently parses the folder prefix; brittle if folder is later renamed. Fix is cheap (pass fit_level explicitly from `match_analysis`) but not urgent. Can piggyback on #4.
