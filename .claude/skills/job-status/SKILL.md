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

### If the user wants to correct the company name or output folder on an existing application

Use when the real hiring company wasn't known at generation time (e.g. the offer was posted via a platform like Free-Work) and has since been identified, or when the output folder was renamed on disk.

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" update-company <app_id> "<new name>"
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" update-output-folder <app_id> "<new path>"
```

Both commands update `updated_at`. `update-company` also refreshes `company_name_norm` so future duplicate detection sees the new name. Do not edit the database directly — these two primitives cover the common cases.

### If the user wants the full atomic rename (folder + DB + JSON + run_summary)

When the real client surfaces after generation (the classic "Free-Work posted on behalf of Omnitech SA" case), `rename-application` does the whole dance in one shot: filesystem rename, DB updates, `_prep/job_offer_analysis.json` patch, `run_summary.json` path rewrite, and a regenerate-outputs pass so DOCX/PDF filenames pick up the new slug.

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" rename-application <app_id> \
  --new-company "Omnitech SA"
```

- `--new-slug "<slug>"` — override the auto-derived folder slug (default keeps the prefix `{fit_level}-{date}-` and uses `{job_title}-{new_company}`).
- `--no-regenerate` — skip the regenerate-outputs step (use when you only want the metadata fixed).

If the old company matched a known aggregator (`Free-Work`, `Indeed`, `LinkedIn`, etc. from `config/settings.default.yaml`), the old name is preserved as `source_platform` in the `_prep/job_offer_analysis.json` for audit.

**When to use which command**:
- `update-company` / `update-output-folder` — DB-only fixes; the disk hasn't changed and you don't want the rename overhead.
- `rename-application` — the disk *should* change too (folder rename + filenames + JSON content). This is the normal post-fact correction.

**Edge cases**:
- Folder already renamed manually on disk → command detects the missing old path and proceeds with DB + JSON patch only.
- Target folder already exists → command refuses to overwrite; pick a different `--new-slug`.
- Word/Acrobat has the DOCX/PDF open → `PermissionError` surfaces with a clear "close any open documents" message; rerun once the file is released.

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
