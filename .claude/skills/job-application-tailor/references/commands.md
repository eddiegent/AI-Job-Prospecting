# Command Reference

This file documents the **workflow** — the bash blocks in pipeline order, with their surrounding context (why this step exists, what artefacts it reads, what it writes). For a flat **signature reference** of every `cli.py` subcommand (positional args, flags, choices, defaults), see [`cli.md`](cli.md) — auto-generated from `cli.py` and kept in lockstep by the pre-commit hook. Always cross-check the signature there before composing a `cli.py` invocation by hand.

All commands assume these variables are set:
- `PROJECT_ROOT` — the git repo root or current working directory
- `SKILL_BASE` — `$PROJECT_ROOT/.claude/skills/job-application-tailor`
- `OUTPUT_DIR` — the output folder for this run (set in Step 0d)
- `PREP_DIR` — `$OUTPUT_DIR/_prep`

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

### Check dependencies
```bash
cd "$SKILL_BASE" && python -c "import docx, yaml, jsonschema; print('OK')"
```
If this fails: `pip install -r "$SKILL_BASE/requirements.txt"`

### Create output folder
```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.common import slug_for_filename, ensure_dir, current_date_ddmmyyyy
from pathlib import Path
date = current_date_ddmmyyyy()
slug = slug_for_filename('<job-title-slug>')
folder = Path('$PROJECT_ROOT/output') / f'{date}-{slug}'
ensure_dir(folder / '_prep')
print(folder)
"
```

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

After the user supplies the real client, patch `job_offer_analysis.json` directly (read, update `company_name`, set `source_platform` to the old value and `company_is_aggregator` to `false`, re-save, re-validate).

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
python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
doc = Document('$PROJECT_ROOT/resources/MASTER_CV.docx')
for p in doc.paragraphs:
    if p.text.strip(): print(f'[{p.style.name}] {p.text}')
for ti, t in enumerate(doc.tables):
    print(f'--- TABLE {ti} ---')
    for r in t.rows: print(' | '.join(c.text.strip() for c in r.cells))
"
```

## Verify Fact Base Against Raw CV

### Catch contamination from job offer keywords and metric drift
```bash
cd "$SKILL_BASE" && python scripts/verify_fact_base.py "$PROJECT_ROOT/resources/MASTER_CV.docx" "$PREP_DIR/cv_fact_base.json"
```

If this fails (exit code 1), either a technology/methodology was fabricated
(`[technologies]` / `[methodologies]`) or a salient numeric metric drifted from
the CV (`[metric]`). Remove a fabricated tech/methodology; for a `[metric]`
failure re-extract or correct the figure to match the CV — do not delete the
number blindly and do not refresh `.cv_hash` by hand. Re-run verification before
proceeding. Warnings about skills are non-blocking — review them but they may be
valid abstractions.

## Recount Match Summary

After writing `match_analysis.json`, run this before validation. Overwrites
`match_summary` with deterministically counted values from `matches[]`.
Idempotent — safe to run on already-correct data.

```bash
cd "$SKILL_BASE" && python scripts/recount_match_summary.py "$PREP_DIR/match_analysis.json"
```

Prints `OK (already correct)` when the LLM-authored summary was already
in sync, or `Updated match_summary: <before> -> <after>` when the script
fixed a drift. Exit code 0 on success.

## Match Grounding Check

After validating `match_analysis.json`, run this guard against false-direct
claims — `match_type: "direct"` requires the requirement's tech tokens to
actually appear in `cv_fact_base.json`. If the LLM marked something direct
without grounding (e.g. a JD asks for Kubernetes and there is no Kubernetes
evidence in the fact base), the script flags it and exits 1.

```bash
cd "$SKILL_BASE" && python scripts/check_match_grounding.py \
  --match-analysis "$PREP_DIR/match_analysis.json" \
  --job-offer "$PREP_DIR/job_offer_analysis.json" \
  --cv-fact-base "$PREP_DIR/cv_fact_base.json"
```

On violation: regenerate Step 4 with the offending requirements surfaced
to the prompt. Downgrade unfounded `direct` claims to `transferable` (with
a concrete `notes` explanation) or to `gap`. Do not proceed to Step 5 with
false directs — the inflated `overall_fit_pct` may push a low-fit role
through the 50% gate, and the tailored CV will inherit the unfounded
claim.

Warnings about transferable matches with empty `notes` are non-blocking
but should be addressed — `match_analysis.md` requires the explanation.

## Validation

### Validate any JSON against its schema
```bash
cd "$SKILL_BASE" && python scripts/validate.py "<json-path>" "schemas/<schema-name>.schema.json"
```

Schema mapping:
| File | Schema |
|------|--------|
| `cv_fact_base.json` | `cv_fact_base.schema.json` |
| `job_offer_analysis.json` | `job_offer_analysis.schema.json` |
| `match_analysis.json` | `match_analysis.schema.json` |
| `tailored_cv.json` | `tailored_cv.schema.json` |
| `letter.json` | `letter.schema.json` |
| `short_letter.json` | `letter.schema.json` |
| `linkedin.json` | `linkedin.schema.json` |

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

### Initialise database (and backfill if needed)
```bash
cd "$SKILL_BASE" && python -c "
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$PROJECT_ROOT/resources/job_history.db')
count = db.total_count()
db.close()
print(f'DB ready: {count} applications')
"
```

If count is 0 and output folders exist:
```bash
cd "$SKILL_BASE" && python scripts/backfill_history.py \
  --output-dir "$PROJECT_ROOT/output" \
  --db-path "$PROJECT_ROOT/resources/job_history.db"
```

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
- `--language <code>` — cold-flow language code (default `fr`). Ignored for offer flow — that one reads `detected_language` from `job_offer_analysis.json`.
- `--dry-run` — print the kwargs JSON that would be inserted, then exit (no DB write). Use this when verifying the wrapper is composing things correctly.
- `--supersede` — before inserting, mark any prior **live** application to the same company + same role as `dropped`, so a re-prospect on a later date leaves one active row per role instead of a parallel duplicate (`#41` vs `#100`). Matches strictly on the natural key (company + normalised title) — a different role at the same company is left untouched. A single pre-mutation backup covers the whole operation.

On success the command prints `Recorded application #<id>` on stdout, preceded by one `Superseded #<id> … -> dropped` line per row it retired. Exit codes: `0` = inserted (or dry-run completed), `1` = unknown id, `2` = missing/invalid `_prep/` artefacts.

## Generate Final Output Files

```bash
cd "$SKILL_BASE/scripts" && python generate_outputs.py \
  --tailored-cv-json "$PREP_DIR/tailored_cv.json" \
  --letter-json "$PREP_DIR/letter.json" \
  --short-letter-json "$PREP_DIR/short_letter.json" \
  --linkedin-json "$PREP_DIR/linkedin.json" \
  --interview-markdown "$PREP_DIR/interview_prep.md" \
  --match-analysis-json "$PREP_DIR/match_analysis.json" \
  --output-dir "$OUTPUT_DIR" \
  --job-title "<detected job title>" \
  --settings "$SKILL_BASE/config/settings.default.yaml" \
  --naming-rules "$SKILL_BASE/config/naming_rules.yaml" \
  --language "<detected language>"
```

Pass `--skip-pdf` to produce DOCX only.

## Regenerate Outputs

For subsequent runs against an existing folder, `regenerate-outputs` is the one-line wrapper. It reads `job_title` and `detected_language` from `_prep/job_offer_analysis.json` and invokes `generate_outputs.py` with all ten flags already composed. Use this for Step 9 regeneration (deterministic doc rebuilding); steps 5-8 still need the skill's LLM flow.

```bash
cd "$SKILL_BASE" && python scripts/cli.py regenerate-outputs "$OUTPUT_DIR"
```

Accepts either a filesystem path or an integer application id (resolved via the DB). Add `--check` to validate `_prep/` completeness without running generation (exit 0 = ready, 1 = missing files). Add `--skip-pdf` to produce DOCX only.

## Rename Application (post-fact)

When the real client surfaces after generation (the Free-Work / Omnitech case), `rename-application` is the atomic wrapper that swaps the folder, DB row, `_prep/job_offer_analysis.json`, and `run_summary.json` in one shot, then runs `regenerate-outputs` so DOCX/PDF filenames pick up the new slug.

```bash
cd "$SKILL_BASE" && python scripts/cli.py rename-application <app_id> --new-company "<real client name>"
```

- Auto-slug keeps `{fit_level}-{date}-` and uses `{job_title}-{new_company}` for the rest. Override with `--new-slug "<slug>"`.
- `--no-regenerate` skips the doc rebuild (DB + metadata patch only).
- If the old company matched a known aggregator (`config/settings.default.yaml § aggregators.known_platforms`), the old name is preserved as `source_platform` on the offer JSON for audit.
- If the folder is already renamed manually on disk, the command detects the missing old path and proceeds with DB + JSON patch only. If the target folder already exists, the command refuses; pick a different `--new-slug`. If a DOCX/PDF inside is open in Word/Acrobat, the rename fails with a clear "close any open documents" message — close and re-run.

For DB-only fixes (no filesystem change), use the lower-level primitives `update-company` / `update-output-folder` instead.
