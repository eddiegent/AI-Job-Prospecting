---
name: job-status
description: Update the status of a job application (generated, applied, rejected, interview, offer), list recent applications and their statuses, or manage the company blacklist/whitelist. Use this skill whenever the user wants to update an application status, check application progress, mark a job as applied/rejected/interview/offer, add or remove a company from the blacklist or whitelist, or asks about their application pipeline.
argument-hint: [company-or-id] [status]
allowed-tools: Read, Bash, Glob
---

# Skill: job-status

Update application statuses and manage company lists in the job history database.

## Setup

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"
DB_PATH="$PROJECT_ROOT/resources/job_history.db"  # configurable in config/settings.yaml → paths.database
```

## What it does

This skill interacts with the SQLite database at `resources/job_history.db` (managed by the `job-application-tailor` skill). It supports:

1. **Listing applications** — show recent applications with their current status
2. **Updating status** — change an application's status to: `generated`, `applied`, `rejected`, `interview`, or `offer`
3. **Managing company lists** — add/remove companies from the blacklist or whitelist

## Workflow

### If the user wants to update a status

1. Parse `$ARGUMENTS` for a company name, job title, or application ID, plus the new status.
2. If ambiguous, list matching applications and ask the user to pick one.
3. Update the status using the database module.

```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')
# List recent applications
apps = db.list_applications(limit=20)
for a in apps:
    print(f\"#{a['id']} | {a['status']:10s} | {a['fit_level']:9s} | {a['fit_pct']:5.1f}% | {a['company_name']} — {a['job_title']}\")
db.close()
"
```

To update:
```bash
cd "$SKILL_BASE" && python -c "
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')
db.update_status(<app_id>, '<new_status>')
db.close()
print('Status updated')
"
```

### If the user wants to manage company lists

Add to blacklist/whitelist:
```bash
cd "$SKILL_BASE" && python -c "
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')
db.add_company_to_list('<company_name>', '<blacklist_or_whitelist>', reason='<optional reason>')
db.close()
print('Done')
"
```

Remove from list:
```bash
cd "$SKILL_BASE" && python -c "
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')
db.remove_company_from_list('<company_name>')
db.close()
print('Removed')
"
```

Show lists:
```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')
for lt in ['blacklist', 'whitelist']:
    entries = db.get_company_list(lt)
    if entries:
        print(f'\n{lt.upper()}:')
        for e in entries:
            reason = f\" — {e['reason']}\" if e.get('reason') else ''
            print(f\"  {e['company_name']}{reason}\")
db.close()
"
```

## Display format

When listing applications, present them as a clean table with columns: ID, Status, Fit Level, Fit %, Company, Job Title. Use the status to guide the user — highlight any that are still at "generated" (haven't been submitted yet).
