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
DB_PATH="$PROJECT_ROOT/resources/job_history.db"
```

**Important**: Paths may contain spaces. Always quote variables in commands — use `"$DB_PATH"`, `"$SKILL_BASE"`, etc. Do NOT store compound commands in a variable (e.g. `CLI="python ... $DB_PATH"`) because spaces in the path will break argument splitting. Instead, write the full command each time:

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" <command> [args...]
```

## What it does

This skill interacts with the SQLite database at `resources/job_history.db` (managed by the `job-application-tailor` skill). It supports:

1. **Listing applications** — show recent applications with their current status
2. **Updating status** — change an application's status to: `generated`, `applied`, `rejected`, `interview`, or `offer`
3. **Managing company lists** — add/remove companies from the blacklist or whitelist

## Workflow

### If the user wants to list applications

List all recent applications (default limit 50):
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" list
```

Filter by status (e.g. only rejected, only applied):
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" list --status rejected
```

Filter by company:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" list --company "Cegid"
```

Combine filters:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" list --status applied --company "OPEN" --limit 10
```

If the user mentions a time period (e.g. "this week", "last 30 days"), add `--since`:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" list --since 30d
```

Supported `--since` values: `7d`, `30d`, `this-week`, `this-month`, or an ISO date (`2026-03-01`).

### If the user wants to update a status

1. Parse `$ARGUMENTS` for a company name, job title, or application ID, plus the new status.
2. If ambiguous, list matching applications and ask the user to pick one.
3. **Before executing the update**, show the user the current application details and the proposed change:
   > Application #<id>: <company> — <title> (currently: <old_status>)
   > Change status to: <new_status>?
   Ask for confirmation before proceeding.
4. Once confirmed, update:

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" update-status <app_id> <new_status>
```

To look up an application's current details first:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" get <app_id>
```

### If the user wants to manage company lists

Show blacklist and whitelist:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" company-list
```

Check if a specific company is listed:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" company-check "<company_name>"
```

Add to blacklist or whitelist:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" company-add "<company_name>" --list-type blacklist --reason "optional reason"
```

Remove from lists:
```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" company-remove "<company_name>"
```

## Display format

When listing applications, present them as a clean table with columns: ID, Status, Fit Level, Fit %, Company, Job Title. Use the status to guide the user — highlight any that are still at "generated" (haven't been submitted yet).
