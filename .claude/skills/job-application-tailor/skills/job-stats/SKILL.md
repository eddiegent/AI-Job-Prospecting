---
name: job-stats
description: Show job application statistics, reports, and trends from the history database. Use this skill whenever the user asks about their application stats, wants a summary of their job search, asks about skill gaps or trends, wants to see their application pipeline, or asks to export their applications to CSV/Excel. Also triggers for "how many applications", "what companies have I applied to", "what skills am I missing", or "export my applications".
argument-hint: [report-type]
allowed-tools: Read, Bash, Write, Glob
---

# Skill: job-stats

Generate reports and insights from the job application history database.

## Setup

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"
DB_PATH="$PROJECT_ROOT/resources/job_history.db"  # configurable in config/settings.yaml → paths.database
```

## Available reports

Parse `$ARGUMENTS` to determine which report(s) the user wants. If no specific report is requested, show the **overview dashboard** (all summaries together).

### Overview dashboard

Run all summary queries and present a combined view:

```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')

total = db.total_count()
print(f'Total applications: {total}')

print('\n--- By Status ---')
for r in db.stats_by_status():
    print(f\"  {r['status']:12s} {r['count']}\")

print('\n--- By Fit Level ---')
for r in db.stats_by_fit_level():
    print(f\"  {r['fit_level']:12s} {r['count']}\")

print('\n--- By Company ---')
for r in db.stats_by_company():
    print(f\"  {r['company_name']:30s} {r['count']}\")

print('\n--- By Domain ---')
for r in db.stats_by_domain():
    print(f\"  {r['domain']:40s} {r['count']}\")

print('\n--- Most Requested Skills (across all applications) ---')
for r in db.skill_gap_trends(limit=15):
    print(f\"  {r['skill']:40s} appears in {r['appearances']} apps (avg fit: {r['avg_fit_pct']}%)\")

db.close()
"
```

### Skill gap trends

Shows which required skills appear most often across applications, helping identify what to learn next:

```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$DB_PATH')
trends = db.skill_gap_trends(limit=20)
print('Skills most frequently required across your applications:')
for r in trends:
    print(f\"  {r['skill']:40s} {r['appearances']} apps, avg fit {r['avg_fit_pct']}%\")
db.close()
"
```

### CSV export

Export all applications to a CSV file:

```bash
cd "$SKILL_BASE" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.job_history_db import JobHistoryDB
from pathlib import Path
db = JobHistoryDB('$DB_PATH')
PROJECT_ROOT = '$(git rev-parse --show-toplevel 2>/dev/null || pwd)'
export_path = Path(PROJECT_ROOT) / 'output' / 'applications_export.csv'
db.export_csv(export_path)
count = db.total_count()
db.close()
print(f'Exported {count} applications to {export_path}')
"
```

## Display format

Present reports using clean markdown tables or formatted text. For the overview dashboard, use section headers to separate each report. Highlight actionable insights — for example, if many applications share the same skill gaps, suggest that as a learning priority.
