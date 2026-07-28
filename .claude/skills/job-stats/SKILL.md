---
name: job-stats
description: Show job application statistics, reports, and trends from the history database. Use this skill whenever the user asks about their application stats, wants a summary of their job search, asks about skill gaps or trends, wants to see their application pipeline, or asks to export their applications to CSV/Excel. Also triggers for "how many applications", "what companies have I applied to", "what skills am I missing", or "export my applications".
argument-hint: [report-type]
allowed-tools: Read, Bash, Write, Glob
---

# Skill: job-stats

Generate reports and insights from the job application history database.

**Before composing any `cli.py` subcommand**, consult `references/cli.md` (under `.claude/skills/job-application-tailor/`) or run `python scripts/cli.py <subcommand> --help`. That file is the authoritative signature reference — never compose flags from convention.

**Routing**: this skill is read-only. For status mutations (`update-status`, `update-company`, `update-output-folder`) or company-list management, invoke `/job-status` instead — it owns those operations and has the canonical invocations documented.

## Setup

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-application-tailor"   # dev/repo layout
if [ ! -d "$SKILL_BASE" ] && [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_BASE="$CLAUDE_PLUGIN_ROOT/skills/job-application-tailor"   # installed plugin
fi
```

The CLI resolves the history database automatically (`JOB_TAILOR_HOME` env var → legacy repo `resources/` layout → OS app-data dir). Pass `--db <path>` only to target a different file.

**Important**: Paths may contain spaces. Always quote variables in commands — use `"$SKILL_BASE"`, `"$PROJECT_ROOT"`, etc. Do NOT store compound commands in a variable because spaces in the path will break argument splitting. Instead, write the full command each time:

```bash
cd "$SKILL_BASE" && python scripts/cli.py <command> [args...]
```

## Available reports

Parse `$ARGUMENTS` to determine which report(s) the user wants. If no specific report is requested, show the **overview dashboard** (all summaries together).

### Overview dashboard

```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type all
```

### Individual reports

By status only:
```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type status
```

By fit level:
```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type fit
```

By company:
```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type company
```

By domain:
```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type domain
```

By organisation type (cold-flow employer vs ESN vs agency; offer-flow and
legacy rows collapse into a single `(unset)` bucket):
```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type org
```

### Skill gap trends

Shows which required skills appear most often across applications, helping identify what to learn next:

```bash
cd "$SKILL_BASE" && python scripts/cli.py skills --limit 20
```

### Time-based filtering

If the user asks about recent activity (e.g. "this week", "last 30 days", "since March"), add `--since`:

```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type all --since 30d
```

Map natural-language time expressions to `--since` values:
- "this week" -> `this-week`
- "last 7 days" / "last week" -> `7d`
- "last 30 days" / "last month" -> `30d`
- "this month" -> `this-month`
- "since March" -> `2026-03-01` (first of the referenced month)

The `--since` flag works on all commands: `stats`, `skills`, and `count`.

### Segmenting cold vs offer applications

Speculative (cold) applications and offer-based applications share the DB.
`--source offer|cold` narrows any report to one flow, and `--org-type` narrows
to a cold-flow organisation type (`end_employer` / `esn` / `staffing_agency` /
`recruitment_agency` / `unknown`). Both work on `stats`, `skills`, and `count`.

```bash
# How many speculative applications have I sent?
cd "$SKILL_BASE" && python scripts/cli.py count --source cold
# Skills most requested by ESNs specifically
cd "$SKILL_BASE" && python scripts/cli.py skills --org-type esn
# Full offer-flow report for the last month
cd "$SKILL_BASE" && python scripts/cli.py stats --type all --source offer --since 30d
```

Fit-% averages are computed from offer rows only — cold rows carry no fit score
by design, and the SQL average ignores them automatically.

### JSON output

For structured output, add `--json` to any command:
```bash
cd "$SKILL_BASE" && python scripts/cli.py stats --type all --json
```

### CSV export

Export all applications to a CSV file:

```bash
cd "$SKILL_BASE" && python scripts/cli.py export-csv --output "$PROJECT_ROOT/output/applications_export.csv"
```

### Quick count

```bash
cd "$SKILL_BASE" && python scripts/cli.py count
cd "$SKILL_BASE" && python scripts/cli.py count --since 7d
```

### Time-series & trends

The `timeline` subcommand computes the full trend deterministically in one call — per-period volume, average fit % (offer rows only), and per-status counts. Never approximate a trend by subtracting `count --since` windows.

```bash
cd "$SKILL_BASE" && python scripts/cli.py timeline --group-by week
cd "$SKILL_BASE" && python scripts/cli.py timeline --group-by month --since 2026-01-01
cd "$SKILL_BASE" && python scripts/cli.py timeline --group-by month --source offer --json
```

`--since`, `--source`, and `--org-type` work exactly as on `stats`. The text output is a ready-made table (newest period first); add `--json` to reformat it yourself, e.g. as a markdown table with trend arrows or +/- deltas.

By default each period buckets applications by when the **pack was generated**.
Add `--basis applied` to bucket by when the application was actually **sent** —
usually the question being asked when someone says "how many did I send in
June?". Applications never sent drop out of that view entirely.

```bash
cd "$SKILL_BASE" && python scripts/cli.py timeline --group-by month --basis applied
```

## Pipeline history reports

Every status change is recorded with its date (schema v4), which makes three
questions answerable that current-status counting cannot reach.

### Funnel — where applications actually get to

```bash
cd "$SKILL_BASE" && python scripts/cli.py funnel
```

Counts applications that **ever reached** each stage, with conversion rates, and
lists `rejected` / `dropped` separately as exits rather than as stages everyone
fails. These numbers are legitimately larger than `stats --type status`: an
application sitting at `rejected` today still passed through `applied`, and
often `interview` — only the history preserves that.

### Response time — how fast employers reply

```bash
cd "$SKILL_BASE" && python scripts/cli.py response-time
```

Days from applying to the employer's first move, with median, fastest, slowest,
and a count still waiting.

Events reconstructed by the v4 migration are deliberately **excluded** — their
dates were inferred from generation dates, so a duration measured against one
describes how long a pack sat around, not how fast anyone replied. On a
migrated database this report therefore starts out empty and fills in as real
status changes get recorded. If the user asks why it's empty, that's the honest
answer: the data to compute it was overwritten before the history table existed.

### Follow-up — applications that have gone quiet

```bash
cd "$SKILL_BASE" && python scripts/cli.py follow-up
cd "$SKILL_BASE" && python scripts/cli.py follow-up --days 30
```

Applications whose most recent event is `applied`, with no movement for 21+
days (override with `--days`), longest wait first. This is the actionable one —
present it as a to-do list, not a statistic.

All three take `--source`, `--org-type`, and `--json`; `funnel` and
`response-time` also take `--since`.

## Display format

Present reports using clean markdown tables or formatted text. For the overview dashboard, use section headers to separate each report. Highlight actionable insights — for example, if many applications share the same skill gaps, suggest that as a learning priority.
