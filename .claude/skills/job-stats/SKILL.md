---
name: job-stats
description: Show job application statistics, reports, and trends from the history database. Use this skill whenever the user asks about their application stats, wants a summary of their job search, asks about skill gaps or trends, wants a funnel / conversion / response-time report, asks which applications have gone quiet and need a follow-up, or asks to export their applications to CSV/Excel. Also triggers for "how many applications", "what companies have I applied to", "what skills am I missing", or "export my applications". Read-only — to change a status or the company lists, use job-status.
argument-hint: "[report-type]"
allowed-tools: Read, Bash, Write, Glob
---

# Skill: job-stats

Reports and insights from the job application history database. **Read-only** — status changes and blacklist/whitelist edits belong to `/job-status`.

## Setup

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"   # dev/repo layout
if [ ! -d "$SKILL_BASE" ] && [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_BASE="$CLAUDE_PLUGIN_ROOT/skills/job-application-tailor"   # installed plugin
fi
```

Run every command as `cd "$SKILL_BASE" && python scripts/cli.py <command> …` — write it out in full each time and quote the paths (they may contain spaces). The CLI finds the database itself; pass `--db <path>` only to target another file. For exact flags, read `$SKILL_BASE/references/cli.md` or run `<command> --help` — never guess a flag.

## Which command

With no specific request, show the overview (`stats --type all`).

| The user asks… | Command |
|---|---|
| overview / summary of my search | `stats --type all` |
| by status / fit level / company / domain / organisation type | `stats --type status` · `fit` · `company` · `domain` · `org` |
| what skills am I missing, what's most requested | `skills --limit 20` |
| how many | `count` |
| trend over time, per week / month | `timeline --group-by week` (or `month`) |
| how many did I **send** in June | `timeline --group-by month --basis applied` |
| where do applications get to, conversion | `funnel` |
| how fast do employers reply | `response-time` |
| what's gone quiet, what should I chase | `follow-up` (default 21 days; `--days N`) |
| export to CSV / Excel | `export-csv --output "$PROJECT_ROOT/output/applications_export.csv"` |

**Filters** (combine freely; `cli.md` lists exactly which command takes which):
- `--since` — "this week" → `this-week`, "last 7 days" / "last week" → `7d`, "last 30 days" / "last month" → `30d`, "this month" → `this-month`, "since March" → `2026-03-01` (first of that month).
- `--source offer|cold` — offer-based vs speculative applications.
- `--org-type end_employer|esn|staffing_agency|recruitment_agency|unknown` — cold-flow organisation type. Offer and legacy rows have none and appear as `(unset)` in `stats --type org`.
- `--json` — structured output, when you want to reformat it yourself (e.g. a markdown table with trend arrows).

## Reading the numbers correctly

- **Trends come from `timeline`, never from subtracting `count --since` windows.** It computes volume, average fit and per-status counts per period in one call. By default periods bucket by when the **pack was generated**; `--basis applied` buckets by when it was **sent** (unsent applications drop out).
- **Fit averages cover offer rows only** — cold rows carry no fit score by design.
- **`funnel` counts applications that ever reached each stage**, so its numbers are legitimately larger than `stats --type status`: an application rejected today still passed through `applied`, often `interview`. `rejected` / `dropped` are listed as exits, not stages.
- **`response-time` excludes `[backfill]` events.** Those dates were reconstructed by the v4 migration from generation dates, so they measure how long a pack sat around, not how fast anyone replied. On a migrated database the report starts empty and fills in as real status changes are recorded — if the user asks why it's empty, that is the honest answer.
- **`follow-up` is a to-do list, not a statistic.** Present it as actions: who to chase, longest wait first.

## Display

Use clean markdown tables, with section headers for the overview. Point out what's actionable — e.g. if many applications share the same skill gap, suggest it as a learning priority.
