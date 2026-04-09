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

## Time Filtering

Add a time period to any report: `/job-stats status last 30 days`, `/job-stats skills this week`.

## Export

`/job-stats export` writes all applications to `output/applications_export.csv`.
