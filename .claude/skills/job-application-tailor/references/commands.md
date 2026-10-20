# Command Reference

This file documents the **workflow** — the bash blocks in pipeline order, with their surrounding context (why this step exists, what artefacts it reads, what it writes). For a flat **signature reference** of every `cli.py` subcommand (positional args, flags, choices, defaults), see [`cli.md`](cli.md) — auto-generated from `cli.py` and kept in lockstep by the pre-commit hook. Always cross-check the signature there before composing a `cli.py` invocation by hand.

All commands assume these variables are set:
- `PROJECT_ROOT` — the git repo root or current working directory
- `SKILL_BASE` — `$PROJECT_ROOT/.claude/skills/job-application-tailor`
- `OUTPUT_DIR` — the output folder for this run (`output_dir` from preflight)
- `PREP_DIR` — `$OUTPUT_DIR/_prep`
- `MASTER_CV` — the master CV path (`master_cv_path` from preflight). Never assume `resources/MASTER_CV.docx`: the user data dir may be `JOB_TAILOR_HOME` or the OS app-data dir.

**Important — paths with spaces**: These paths may contain spaces (e.g. `Job Prospecting`). Always double-quote variable references in bash (`"$PROJECT_ROOT"`, `"$SKILL_BASE"`, etc.). Never store compound commands in a variable — write the full command inline instead.

## Setup

### Resolve paths
```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"   # dev/repo layout
if [ ! -d "$SKILL_BASE" ] && [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_BASE="$CLAUDE_PLUGIN_ROOT/skills/job-application-tailor"   # installed plugin
fi
```

If neither directory exists, stop and tell the user the toolkit is not
installed correctly.

Dependency checks, output-folder creation and history-DB initialisation are all
done by `scripts/preflight.py` (see `job-prep-cv/SKILL.md`) — there is no
separate command to run for them.

## URL Probe (before WebFetch)

WebFetch silently consumes a round-trip on aggregators that block automated requests (e.g. lesjeudis returns 403). Probe with a HEAD request first so the failure is fast and the fallback ("paste below or share a file path") fires immediately.

```bash
cd "$SKILL_BASE" && python scripts/cli.py probe-url "<offer-url>"
```

Prints exactly one line: `OK`, `BLOCKED <code>`, `OTHER_HTTP <code>`, or `OTHER_ERROR <type>: <msg>`.

If the probe prints `BLOCKED <code>`, skip WebFetch and ask the user: *"`<host>` blocks automated requests (HTTP `<code>`). Paste the offer text below, or share a path to a local file."*

If it prints `OTHER_ERROR` (DNS, TLS, corporate proxy, timeout) treat that as inconclusive — try WebFetch normally; the fallback messaging is the same if it fails too. The probe is conservative (5 s timeout, single shot) and exists to fail fast on aggregator 403s, not to be a general-purpose reachability check.

## Cache Raw Offer

Write the raw offer text (WebFetch response or pasted input) to `$PREP_DIR/raw_offer.md` before analysis. Run once per offer, after `$PREP_DIR` exists and before Step 3 analysis.

```bash
cd "$SKILL_BASE" && python scripts/cli.py cache-raw-offer "$OUTPUT_DIR" <<'OFFER'
<paste the WebFetch response or raw offer text here>
OFFER
```

If you already have the text in a variable, pipe it in instead of the heredoc. The file is a sibling of the `_prep/` JSONs; no schema validation — it's a verbatim snapshot.

## Platform Detection

After Step 3 produces `job_offer_analysis.json`, probe the company name against the configured aggregator list. Prints the matched platform (to use as `source_platform`) or an empty line if the company is a direct employer.

```bash
cd "$SKILL_BASE" && python scripts/cli.py detect-platform "$OUTPUT_DIR"
```

After the user supplies the real client, patch `job_offer_analysis.json` directly (read, update `company_name`, set `source_platform` to the old value and `company_is_aggregator` to `false`, re-save, then re-run `gate offer`).

## CV Caching

### Check cache validity / copy cached fact base

Both are handled by `scripts/preflight.py` (job-prep-cv's consolidated invocation): a cache hit returns `status: ok` with the fact base already copied into `$PREP_DIR` and verified. There is no separate command to run.

### Save fact base + hash after extraction

```bash
cd "$SKILL_BASE" && python scripts/cli.py save-cv-cache "$OUTPUT_DIR"
```

Runs the metric-drift consistency guard first and refuses (exit 1) if the fact base disagrees with the CV — a stale fact base can never be re-blessed. Pass `--cv <path>` if the master CV is not at the resolved user-data dir.

### Read master CV text
```bash
cd "$SKILL_BASE" && python scripts/cli.py read-cv --cv "$MASTER_CV"
```

Prints every paragraph as `[<style>] <text>`, then each table as `--- TABLE n ---` rows. `--cv` defaults to the resolved user-data dir's `MASTER_CV.docx`.

## Gates

Each pipeline stage has one gate that runs all of its deterministic checks and reports every problem at once. `<folder>` is `$OUTPUT_DIR` (or `$PREP_DIR`).

```bash
cd "$SKILL_BASE" && python scripts/cli.py gate <stage> "$OUTPUT_DIR"
```

| Stage | After writing | Checks |
|---|---|---|
| `factbase` | `cv_fact_base.json` | schema → verify against the master CV (fabricated tech/methodology, metric drift; skill warnings non-blocking). `--cv` overrides the CV path |
| `offer` | `job_offer_analysis.json` | schema |
| `match` | `match_analysis.json` | recount `match_summary` in place → schema → grounding against `cv_fact_base_merged.json` (a `direct` match needs evidence; familiar-only skills are at most `transferable`) |
| `cv` | `tailored_cv.json` | schema → forbidden title labels (`user_prefs.yaml`) → claims check |
| `letters` | `letter.json` + `short_letter.json` | schema → claims check |
| `linkedin` | `linkedin.json` | schema → message lengths (connection request ≤ 300, direct message ≤ 700; other messages warn over 500) → claims check |
| `profile` | `company_profile.json` (cold) | schema |
| `roles` | `role_candidates.json` (cold) | schema → forbidden title labels → stack grounding |
| `selected-role` | `selected_role.json` (cold) | schema → stack grounding |

Exit 0 = pass, 1 = at least one check failed (each failure is listed under its check), 2 = bad folder. `match`, `roles` and `selected-role` fail if `cv_fact_base_merged.json` is missing — run `claims_guard.py merge` (Step 3.9) first. The claims check in `cv` / `letters` / `linkedin` covers only that stage's own files, and each message is prefixed `[rule] <file>:`. A failed schema check stops the stage; otherwise every check runs. The claims check flags unsourced intensity wording ("quotidien"…), familiar-only skills used as strengths, skills absent from the master CV/addendum, dropped skill qualifiers, a malformed "Earlier experience" line, durations no source states ("trente ans", "17 ans chez X" — only those in the master CV, the addendum or implied by a role's dates; a range like "2 à 5 ans" is skipped), and technologies from the job posting (offer) or the company's `tech_stack_hints` (cold) that the CV doesn't support.

**On failure, fix the generated file and re-run.** Never edit the master CV, the addendum or `.cv_hash` to make a gate pass. Match grounding failure → downgrade the flagged requirements to `transferable` (with a concrete `notes`) or `gap`. Fact-base `[metric]` failure → re-extract the figure from the CV, don't delete it.

The individual scripts (`validate.py`, `recount_match_summary.py`, `check_match_grounding.py`, `check_role_grounding.py`, `verify_fact_base.py`, `claims_guard.py check`) still work on their own for debugging.

## Folder Rename (after match analysis)

### Add fit-level prefix AND rebuild the slug (single rename)

The offer flow creates the output folder eagerly with a placeholder slug
derived from the user's input (often a URL). After Step 4 we know the
real `job_title` and `company_name` from `job_offer_analysis.json`, so
this rename rebuilds the slug at the same time as it adds the fit
prefix — collapsing two historical renames into one and producing a
meaningful folder name on the first try.

```bash
cd "$SKILL_BASE" && python scripts/cli.py rename-with-fit "$OUTPUT_DIR"
```

The command reads `overall_fit_pct`, `job_title`, and `company_name` from the
`_prep/` JSONs and prints the new folder path. Update `$OUTPUT_DIR` and
`$PREP_DIR` to point to it.

The cold flow uses `rename-cold-folder` instead (no fit score to anchor on —
the slug is rebuilt from `company_profile.company_name`; the `cold-` prefix is
preserved):

```bash
cd "$SKILL_BASE" && python scripts/cli.py rename-cold-folder "$OUTPUT_DIR"
```

## Job History Database

### Duplicate Detection

Preferred: the `check-duplicate` subcommand wraps all three history checks (exact URL, company+title, fuzzy skill overlap), the same-company context surface, and the blacklist lookup in one call. It reads company/title/skills/URL from `_prep/job_offer_analysis.json`.

```bash
cd "$SKILL_BASE" && python scripts/cli.py check-duplicate "$PREP_DIR" --url "<offer-url-if-not-in-JSON>"
```

- Accepts either the folder (`$OUTPUT_DIR` or `$PREP_DIR`) or the `_prep/job_offer_analysis.json` path directly.
- `--url` is optional — pass it when the offer JSON doesn't carry `source_url` (the analysis schema doesn't yet).
- `--json` emits a structured payload with `blacklist`, `duplicates`, `same_company_context`.
- Exit codes: `0` = clean, `1` = flagged (duplicate or blacklisted), `2` = bad input (missing/invalid JSON).

Low-level primitives remain available for scripting beyond this step: `db.find_duplicates(...)`, `db.find_same_company(...)`, `db.check_company_list(...)` in `scripts/job_history_db.py`.

### Company Lists
```bash
cd "$SKILL_BASE" && python scripts/cli.py company-check "<company_name>"
```

### Record Application

`record-application` is the one-line wrapper for Step 10. It auto-detects offer vs. cold flow from the folder prefix (`cold-…` → cold), reads the appropriate `_prep/` artefacts (`job_offer_analysis.json` + `match_analysis.json` for offer; `selected_role.json` + `company_profile.json` for cold), composes the `add_application()` kwargs once, and inserts.

```bash
cd "$SKILL_BASE" && python scripts/cli.py record-application "$OUTPUT_DIR"
```

Accepts either a filesystem path or an integer application id (resolved via the DB — useful when re-recording an already-renamed run). Flags:

- `--url <url>` — populate `source_url` when the offer JSON / company profile lacks one (e.g. older runs predating the schema field).
- `--source {offer,cold}` — override the auto-detected flow. The default is `cold` for `cold-` prefixed folders and `offer` otherwise; only pass this when the folder name disagrees with the actual flow.
- `--language <code>` — cold-flow language code (default: `selected_role.language`, else `fr`). Ignored for offer flow — that one reads `detected_language` from `job_offer_analysis.json`.
- `--dry-run` — print the kwargs JSON that would be inserted, then exit (no DB write). Use this when verifying the wrapper is composing things correctly.
- `--supersede` — before inserting, mark any prior **live** application to the same company + same role as `dropped`, so a re-prospect on a later date leaves one active row per role instead of a parallel duplicate. Matches strictly on the natural key (company + normalised title) — a different role at the same company is left untouched. A single pre-mutation backup covers the whole operation.

On success the command prints `Recorded application #<id>` on stdout, preceded by one `Superseded #<id> … -> dropped` line per row it retired. Exit codes: `0` = inserted (or dry-run completed), `1` = unknown id, `2` = missing/invalid `_prep/` artefacts.

## Build / Regenerate Outputs

`regenerate-outputs` builds the final files from `_prep/` — on the first run and on every rebuild, for both flows. The folder prefix picks the flow:

- **offer** — title and language from `_prep/job_offer_analysis.json`; renders `interview_prep.md` to HTML; passes `match_analysis.json` for the run summary.
- **cold** (`cold-…`) — title from `selected_role.title`, language from `selected_role.language` (default `fr`); renders `company_dossier.md` to HTML instead of interview prep.

Offer filenames use the folder slug (title + company), so every rebuild overwrites the same files. Packs built before this command was the first-build path may carry different names (the raw job title, or a hand-shortened cold title); pass `--job-title "<old title>"` to rebuild under the old names instead of creating a second set. `--language` overrides the language. It only rebuilds documents — steps that generate content still need the skill's LLM flow.

```bash
cd "$SKILL_BASE" && python scripts/cli.py regenerate-outputs "$OUTPUT_DIR"
```

Accepts either a filesystem path or an integer application id (resolved via the DB). Add `--check` to validate `_prep/` completeness without running generation (exit 0 = ready, 1 = missing files). Add `--skip-pdf` to produce DOCX only.

## Rename Application (post-fact)

When the real client surfaces after generation (a platform such as Free-Work posted on behalf of a client), `rename-application` is the atomic wrapper that swaps the folder, DB row, `_prep/job_offer_analysis.json`, and `run_summary.json` in one shot, then runs `regenerate-outputs` so DOCX/PDF filenames pick up the new slug.

```bash
cd "$SKILL_BASE" && python scripts/cli.py rename-application <app_id> --new-company "<real client name>"
```

- Auto-slug keeps `{fit_level}-{date}-` and uses `{job_title}-{new_company}` for the rest. Override with `--new-slug "<slug>"`.
- `--no-regenerate` skips the doc rebuild (DB + metadata patch only).
- If the old company matched a known aggregator (`config/settings.default.yaml § aggregators.known_platforms`), the old name is preserved as `source_platform` on the offer JSON for audit.
- If the folder is already renamed manually on disk, the command detects the missing old path and proceeds with DB + JSON patch only. If the target folder already exists, the command refuses; pick a different `--new-slug`. If a DOCX/PDF inside is open in Word/Acrobat, the rename fails with a clear "close any open documents" message — close and re-run.

For DB-only fixes (no filesystem change), use the lower-level primitives `update-company` / `update-output-folder` instead.
