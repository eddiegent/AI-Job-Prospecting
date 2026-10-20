---
name: job-status
description: Update the status of a job application (generated, applied, rejected, interview, offer, dropped), list recent applications and their statuses, fix an application's company name or folder, or manage the company blacklist/whitelist. Use this skill whenever the user wants to update an application status, says they applied / got rejected / got an interview or offer, wants to see or check a specific application or its history, mark a job as dropped, correct the real client behind a platform posting, or add or remove a company from the blacklist or whitelist. For aggregate statistics, trends and reports, use job-stats.
argument-hint: "[company-or-id] [status]"
allowed-tools: Read, Bash, Glob
---

# Skill: job-status

List applications, change their status, correct their metadata, and manage the company lists in the job history database.

## Setup

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"   # dev/repo layout
if [ ! -d "$SKILL_BASE" ] && [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_BASE="$CLAUDE_PLUGIN_ROOT/skills/job-application-tailor"   # installed plugin
fi
```

Run every command as `cd "$SKILL_BASE" && python scripts/cli.py <command> …` — write it out in full each time and quote the paths (they may contain spaces). The CLI finds the database itself; pass `--db <path>` only to target another file. For exact flags, read `$SKILL_BASE/references/cli.md` or run `<command> --help` — never guess a flag. Never edit the database directly; the commands below cover every case.

Statuses: `generated`, `applied`, `rejected`, `interview`, `offer`, `dropped` (`dropped` = decided not to pursue; duplicate detection ignores it).

## Listing and looking up

| The user wants… | Command |
|---|---|
| recent applications | `list` (default limit 50; `--limit N`) |
| one status only | `list --status rejected` |
| one company | `list --company "Acme"` — partial, case-insensitive (`"acme"` finds "Acme Robotics SAS"; a short query may match several) |
| a time window | `list --since 30d` (`7d`, `30d`, `this-week`, `this-month`, or an ISO date) |
| one flow / organisation type | `list --source cold` · `list --org-type esn` |
| one application's details | `get <id>` |
| one application's status history | `history <id>` — `[backfill]` entries were reconstructed by the v4 migration, so treat their dates as approximate |

Filters combine. Show lists as a table: ID, Status, Fit Level, Fit %, Company, Job Title — and point out any still at `generated` (not yet sent).

## Updating a status

**Resolve by company, never by a remembered id.** Ids are not stable across a DB restore — `105` can point at a different company in a later session. So even when the user gives an id:

1. Parse the company / title / id and the new status from the request.
2. Re-resolve now: `list --company "<name>"`. Several matches → show them and ask which one.
3. Show the change and ask for confirmation:
   > Application #<id>: <company> — <title> (currently: <old_status>)
   > Change status to: <new_status>?
4. Once confirmed, pass `--expect-company` so a stale id fails (exit 2, nothing changed) instead of silently updating the wrong record:

```bash
cd "$SKILL_BASE" && python scripts/cli.py update-status <id> <new_status> --expect-company "<company>" [--at <date>] [--note "<context>"]
```

**`--at` — record when it happened.** Whenever the user mentions a day ("I applied to Acme on Tuesday", "I sent that one last week"), convert it and pass `--at` (`2026-07-14`, `2026-07-14T09:30`, `today`, `yesterday`). Without it the change is stamped now — and a Friday catch-up session makes four applications sent on Monday look same-day, which quietly inflates every response-time figure. Dates before the application existed, or in the future, are refused as typos.

**`--note`** is optional free text worth keeping ("no answer after 3 weeks", "rejected after technical round").

**Several applications, same status** ("mark 104, 102 and 98 as applied"): confirm the ids and status with the user, then run one `bulk-status 104 102 98 --status applied` (also takes `--at` / `--note`). It prints each row's company/title as it changes — check they're the ones the user meant, since bulk has no `--expect-company`. Missing ids are reported, skipped, and make it exit non-zero.

Every mutation snapshots the DB to `db-backups/` first, so a wrong write is recoverable.

## Correcting the company or folder

Typical case: the offer was posted by a platform (Free-Work…) and the real client is now known.

- **`rename-application <id> --new-company "<name>"`** — the normal fix. Renames the folder, updates the DB, patches `_prep/job_offer_analysis.json` and `run_summary.json`, and rebuilds the DOCX/PDF so filenames pick up the new slug. If the old name was a known platform, it is kept as `source_platform`. Options: `--new-slug "<slug>"` to override the folder slug (default keeps `{fit_level}-{date}-` and uses `{job_title}-{new_company}`); `--no-regenerate` to skip the rebuild.
  - Folder already renamed by hand → it detects that and patches DB + JSON only.
  - Target folder exists → it refuses; pick a different `--new-slug`.
  - A DOCX/PDF is open in Word/Acrobat → `PermissionError`; ask the user to close it and re-run.
- **`update-company <id> "<name>" --expect-company "<old name>"`** / **`update-output-folder <id> "<path>"`** — DB-only fixes, when nothing on disk should change. `update-company` also refreshes the normalised name used by duplicate detection.

## Company lists

| The user wants… | Command |
|---|---|
| see both lists | `company-list` |
| check one company | `company-check "<name>"` |
| add one | `company-add "<name>" --list-type blacklist --reason "<optional reason>"` (or `whitelist`) |
| remove one | `company-remove "<name>"` |
