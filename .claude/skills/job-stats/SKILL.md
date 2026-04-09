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
DB_PATH="$PROJECT_ROOT/resources/job_history.db"
CLI="python scripts/cli.py --db $DB_PATH"
```

## Available reports

Parse `$ARGUMENTS` to determine which report(s) the user wants. If no specific report is requested, show the **overview dashboard** (all summaries together).

### Overview dashboard

```bash
cd "$SKILL_BASE" && $CLI stats --type all
```

### Individual reports

By status only:
```bash
cd "$SKILL_BASE" && $CLI stats --type status
```

By fit level:
```bash
cd "$SKILL_BASE" && $CLI stats --type fit
```

By company:
```bash
cd "$SKILL_BASE" && $CLI stats --type company
```

By domain:
```bash
cd "$SKILL_BASE" && $CLI stats --type domain
```

### Skill gap trends

Shows which required skills appear most often across applications, helping identify what to learn next:

```bash
cd "$SKILL_BASE" && $CLI skills --limit 20
```

### Time-based filtering

If the user asks about recent activity (e.g. "this week", "last 30 days", "since March"), add `--since`:

```bash
cd "$SKILL_BASE" && $CLI stats --type all --since 30d
```

Map natural-language time expressions to `--since` values:
- "this week" -> `this-week`
- "last 7 days" / "last week" -> `7d`
- "last 30 days" / "last month" -> `30d`
- "this month" -> `this-month`
- "since March" -> `2026-03-01` (first of the referenced month)

The `--since` flag works on all commands: `stats`, `skills`, and `count`.

### JSON output

For structured output, add `--json` to any command:
```bash
cd "$SKILL_BASE" && $CLI stats --type all --json
```

### CSV export

Export all applications to a CSV file:

```bash
cd "$SKILL_BASE" && $CLI export-csv --output "$PROJECT_ROOT/output/applications_export.csv"
```

### Quick count

```bash
cd "$SKILL_BASE" && $CLI count
cd "$SKILL_BASE" && $CLI count --since 7d
```

## Display format

Present reports using clean markdown tables or formatted text. For the overview dashboard, use section headers to separate each report. Highlight actionable insights — for example, if many applications share the same skill gaps, suggest that as a learning priority.
