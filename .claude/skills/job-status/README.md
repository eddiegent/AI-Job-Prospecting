# job-status

List, update, and manage job application statuses and company blacklist/whitelist.
Invoke with `/job-status` to list, or `/job-status [company-or-id] [status]` to update.

> Requires `job-application-tailor` to have been run at least once -- reads from `resources/job_history.db`.

## Status Workflow

```
generated --> applied --> interview --> offer
                  \--> rejected
```

Transitions are forward-only -- you cannot move an application back to a previous state.

## Example: Listing Applications

`/job-status`

| ID | Status | Fit | Fit % | Company | Job Title |
|----|-----------|----------|-------|---------------|-------------------------------|
| 23 | applied | Strong | 82% | Dassault Sys. | Senior .NET Developer |
| 22 | generated | Moderate | 65% | Capgemini | Desktop Application Engineer |
| 21 | interview | Strong | 79% | Ubisoft | C# Tools Developer |
| 20 | rejected | Weak | 52% | Sopra Steria | Full-Stack Developer |

Filter with `/job-status --status applied` or `/job-status --company Ubisoft`.

## Example: Updating a Status

```
> /job-status Dassault interview

Application #23: Dassault Sys. -- Senior .NET Developer (currently: applied)
Change status to: interview?

> Yes

Updated application #23 to "interview".
```

## Example: Renaming an Application

When a job is posted by an aggregator (Free-Work, Indeed, LinkedIn, ...) and the real client surfaces afterwards:

```
> /job-status rename 23 --new-company "Omnitech SA"

Renamed: good-01042026-Software-Engineer-Free-Work
     -> good-01042026-Software-Engineer-Omnitech-SA
Patched _prep/job_offer_analysis.json   (source_platform = "Free-Work")
Patched run_summary.json
#23: company "Free-Work" -> "Omnitech SA"
Regenerating outputs...
```

One command swaps the folder, DB row, `_prep/job_offer_analysis.json`, and `run_summary.json`, then rebuilds the DOCX/PDF filenames so they match the new slug. Add `--no-regenerate` to skip the doc rebuild.

## Example: Blacklist / Whitelist

```
> /job-status blacklist add "Consulting Corp" --reason "Poor Glassdoor reviews"
Added "Consulting Corp" to blacklist.

> /job-status blacklist
| Company | List | Reason |
|-----------------|-----------|------------------------|
| Consulting Corp | blacklist | Poor Glassdoor reviews |

> /job-status blacklist remove "Consulting Corp"
Removed "Consulting Corp" from blacklist.
```
