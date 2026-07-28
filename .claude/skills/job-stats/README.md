# job-stats

Show job application statistics, reports, and trends from the history database.
Invoke with `/job-stats` or `/job-stats [report-type]` (e.g. `/job-stats fit`, `/job-stats skills`).

> Requires `job-application-tailor` to have been run at least once -- the reports read from `resources/job_history.db`.

## Example: Overview Dashboard

### By Status

| Status | Count | Avg Fit % |
|-----------|-------|-----------|
| generated | 5 | 62% |
| applied | 12 | 74% |
| rejected | 3 | 58% |
| interview | 2 | 81% |
| offer | 1 | 85% |

**Total: 23 applications**

### By Fit Level

| Fit Level | Count | Avg Fit % |
|-----------|-------|-----------|
| Strong | 8 | 82% |
| Moderate | 11 | 67% |
| Weak | 4 | 48% |

### By Company

| Company | Apps | Avg Fit % | Statuses |
|---------------|------|-----------|---------------------|
| Dassault Sys. | 3 | 76% | applied, interview |
| Sopra Steria | 2 | 69% | applied, rejected |
| Capgemini | 2 | 71% | applied |
| Ubisoft | 1 | 84% | offer |

## Example: Skill Gap Trends

`/job-stats skills`

| # | Skill | Appearances | You Have It? |
|---|-------------------|-------------|--------------|
| 1 | Kubernetes | 14 | No |
| 2 | Azure DevOps | 11 | Yes |
| 3 | React | 9 | No |
| 4 | Microservices | 8 | Yes |
| 5 | Terraform | 7 | No |

> **Insight:** Kubernetes and Terraform appear frequently -- consider prioritising these for upskilling.

## Example: Pipeline history

Every status change is recorded with its date, which makes three questions
answerable that counting current statuses cannot reach.

`/job-stats funnel`

| Stage | Count | Conversion |
|-----------|-------|------------------|
| generated | 124 | — |
| applied | 77 | 62% of previous |
| interview | 4 | 5% of previous |
| offer | 0 | — |

Counts applications that **ever reached** each stage, so they are legitimately
larger than the by-status table above: an application sitting at `rejected`
today still passed through `applied`, and often `interview`. `rejected` and
`dropped` are listed separately as exits rather than as stages everyone fails.

`/job-stats follow-up`

| ID | Waiting | Applied | Company |
|-----|---------|------------|-------------------|
| 7 | 126d | 2026-03-24 | Attineos Applications |
| 1 | 125d | 2026-03-24 | Alpha-CIM |
| 15 | 124d | 2026-03-26 | Canopee Group |

Applications whose most recent event is `applied`, silent for 21+ days
(`--days` overrides). Read this as a to-do list, not a statistic.

`/job-stats response-time` reports days from applying to the employer's first
move — median, fastest, slowest, and how many are still waiting.

> **On an empty response-time report:** events reconstructed by the schema-v4
> migration are deliberately excluded, because their dates were inferred from
> pack-generation dates — a duration measured against one describes how long a
> pack sat around, not how fast anyone replied. The report fills in as real
> status changes get recorded, which is why `--at` on `/job-status` matters.

## Time Filtering

Add a time period to any report: `/job-stats status last 30 days`, `/job-stats skills this week`.

Timeline trends bucket by pack-generation date by default; `--basis applied`
buckets by when applications were actually sent, which is usually the question
being asked by "how many did I send in June?".

## Export

`/job-stats export` writes all applications to `output/applications_export.csv`.

## Status mutations

This skill is read-only. To change an application's status (`applied`, `rejected`, `interview`, `offer`, `dropped`) or manage the company blacklist/whitelist, use `/job-status`.

## CLI reference

The skill calls `cli.py` under the hood. The authoritative signature reference is `.claude/skills/job-application-tailor/references/cli.md` (auto-generated from `cli.py`).
