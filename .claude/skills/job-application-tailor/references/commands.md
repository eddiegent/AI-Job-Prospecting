# Command Reference

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
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"
```

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

## Cache Raw Offer

Write the raw offer text (WebFetch response or pasted input) to `$PREP_DIR/raw_offer.md` before analysis. Run once per offer, after `$PREP_DIR` exists and before Step 3 analysis.

```bash
python -u -c "
import sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
Path('$PREP_DIR/raw_offer.md').write_text(sys.stdin.read(), encoding='utf-8')
print('Cached raw offer ->', '$PREP_DIR/raw_offer.md')
" <<'OFFER'
<paste the WebFetch response or raw offer text here>
OFFER
```

If you already have the text in a variable, pipe it in instead of the heredoc. The file is a sibling of the `_prep/` JSONs; no schema validation — it's a verbatim snapshot.

## Platform Detection

After Step 3 produces `job_offer_analysis.json`, probe the company name against the configured aggregator list. Returns the matched platform (to use as `source_platform`) or empty string if the company is a direct employer.

```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.common import matched_aggregator
from scripts.paths import load_settings
from pathlib import Path
import json
settings = load_settings()
platforms = settings.get('aggregators', {}).get('known_platforms', [])
job = json.loads(Path('$PREP_DIR/job_offer_analysis.json').read_text(encoding='utf-8'))
hit = matched_aggregator(job.get('company_name', ''), platforms)
print(hit or '')
"
```

After the user supplies the real client, patch `job_offer_analysis.json` directly (read, update `company_name`, set `source_platform` to the old value and `company_is_aggregator` to `false`, re-save, re-validate).

## CV Caching

### Check cache validity
```bash
cd "$SKILL_BASE" && python -c "
from scripts.common import cv_cache_is_valid
from pathlib import Path
print('VALID' if cv_cache_is_valid(Path('$PROJECT_ROOT/resources/MASTER_CV.docx')) else 'STALE')
"
```

### Copy cached fact base to prep dir
```bash
cd "$SKILL_BASE" && python -c "
from scripts.common import copy_cached_cv_fact_base
from pathlib import Path
copy_cached_cv_fact_base(Path('$PROJECT_ROOT/resources/MASTER_CV.docx'), Path('$PREP_DIR'))
"
```

### Save fact base + hash after extraction
```bash
cd "$SKILL_BASE" && python -c "
from scripts.common import save_cv_fact_base
from pathlib import Path
save_cv_fact_base(Path('$PROJECT_ROOT/resources/MASTER_CV.docx'), Path('$PREP_DIR'))
"
```

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

### Catch contamination from job offer keywords
```bash
cd "$SKILL_BASE" && python scripts/verify_fact_base.py "$PROJECT_ROOT/resources/MASTER_CV.docx" "$PREP_DIR/cv_fact_base.json"
```

If this fails (exit code 1), technologies or methodologies were fabricated.
Remove the flagged items from `cv_fact_base.json` and re-run verification before proceeding.
Warnings about skills are non-blocking — review them but they may be valid abstractions.

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

### Add fit-level prefix
```bash
cd "$SKILL_BASE" && python -c "
from scripts.common import rename_folder_with_fit, load_json
from pathlib import Path
match = load_json(Path('$PREP_DIR/match_analysis.json'))
pct = match['match_summary']['overall_fit_pct']
new_path = rename_folder_with_fit(Path('$OUTPUT_DIR'), pct)
print(new_path)
"
```
Update `$OUTPUT_DIR` and `$PREP_DIR` to point to the renamed folder.

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
cd "$SKILL_BASE" && python scripts/cli.py --db "$PROJECT_ROOT/resources/job_history.db" \
  check-duplicate "$PREP_DIR" --url "<offer-url-if-not-in-JSON>"
```

- Accepts either the folder (`$OUTPUT_DIR` or `$PREP_DIR`) or the `_prep/job_offer_analysis.json` path directly.
- `--url` is optional — pass it when the offer JSON doesn't carry `source_url` (the analysis schema doesn't yet).
- `--json` emits a structured payload with `blacklist`, `duplicates`, `same_company_context`.
- Exit codes: `0` = clean, `1` = flagged (duplicate or blacklisted), `2` = bad input (missing/invalid JSON).

Low-level primitives remain available for scripting beyond this step: `db.find_duplicates(...)`, `db.find_same_company(...)`, `db.check_company_list(...)` in `scripts/job_history_db.py`.

### Company Lists
```bash
cd "$SKILL_BASE" && python -c "
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$PROJECT_ROOT/resources/job_history.db')
result = db.check_company_list('<company_name>')
if result:
    print(f\"{result['list_type'].upper()}: {result['company_name']} — {result.get('reason', 'no reason given')}\")
else:
    print('Not on any list')
db.close()
"
```

### Record Application
```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
from scripts.common import load_json
from pathlib import Path
db = JobHistoryDB('$PROJECT_ROOT/resources/job_history.db')
job = load_json(Path('$PREP_DIR/job_offer_analysis.json'))
match = load_json(Path('$PREP_DIR/match_analysis.json'))
ms = match['match_summary']
# Derive fit_level from folder name
import re
folder_name = Path('$OUTPUT_DIR').name
fit_level = 'low'
for prefix in ('very_good', 'good', 'medium'):
    if folder_name.startswith(prefix + '-'):
        fit_level = prefix
        break
app_id = db.add_application(
    company_name=job['company_name'],
    job_title=job['job_title'],
    location=job.get('location'),
    source_url=job.get('source_url'),
    domain=job.get('domain'),
    seniority=job.get('seniority'),
    fit_level=fit_level,
    fit_pct=ms['overall_fit_pct'],
    direct_count=ms.get('direct_count'),
    transferable_count=ms.get('transferable_count'),
    gap_count=ms.get('gap_count'),
    output_folder=str(Path('$OUTPUT_DIR')),
    detected_language=job.get('detected_language'),
    required_skills=job.get('required_skills', []),
    preferred_skills=job.get('preferred_skills', []),
)
db.close()
print(f'Recorded application #{app_id}')
"
```

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
cd "$SKILL_BASE" && python scripts/cli.py --db "$PROJECT_ROOT/resources/job_history.db" \
  regenerate-outputs "$OUTPUT_DIR"
```

Accepts either a filesystem path or an integer application id (resolved via the DB). Add `--check` to validate `_prep/` completeness without running generation (exit 0 = ready, 1 = missing files). Add `--skip-pdf` to produce DOCX only.

## Rename Application (post-fact)

When the real client surfaces after generation (the Free-Work / Omnitech case), `rename-application` is the atomic wrapper that swaps the folder, DB row, `_prep/job_offer_analysis.json`, and `run_summary.json` in one shot, then runs `regenerate-outputs` so DOCX/PDF filenames pick up the new slug.

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$PROJECT_ROOT/resources/job_history.db" \
  rename-application <app_id> --new-company "<real client name>"
```

- Auto-slug keeps `{fit_level}-{date}-` and uses `{job_title}-{new_company}` for the rest. Override with `--new-slug "<slug>"`.
- `--no-regenerate` skips the doc rebuild (DB + metadata patch only).
- If the old company matched a known aggregator (`config/settings.default.yaml § aggregators.known_platforms`), the old name is preserved as `source_platform` on the offer JSON for audit.
- If the folder is already renamed manually on disk, the command detects the missing old path and proceeds with DB + JSON patch only. If the target folder already exists, the command refuses; pick a different `--new-slug`. If a DOCX/PDF inside is open in Word/Acrobat, the rename fails with a clear "close any open documents" message — close and re-run.

For DB-only fixes (no filesystem change), use the lower-level primitives `update-company` / `update-output-folder` instead.
