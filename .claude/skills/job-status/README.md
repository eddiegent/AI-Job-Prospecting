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
