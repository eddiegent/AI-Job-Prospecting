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
```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$PROJECT_ROOT/resources/job_history.db')
dupes = db.find_duplicates(
    company_name=job['company_name'],
    job_title=job['job_title'],
    source_url=job.get('source_url'),
    required_skills=job.get('required_skills', []),
)
if dupes:
    for d in dupes:
        print(f\"Match: {d['company_name']} / {d['job_title']} ({d['fit_level']}, {d['fit_pct']}%) — {d['match_reason']}\")
        print(f\"  Output: {d['output_folder']}\")
        print(f\"  Date: {d['created_at']}\")
else:
    print('No duplicates found')
# Also check for same-company context
context = db.find_same_company('<company_name>')
if context and not dupes:
    for c in context:
        print(f\"Previous: {c['company_name']} / {c['job_title']} ({c['fit_pct']}%) on {c['created_at']}\")
db.close()
"
```

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
