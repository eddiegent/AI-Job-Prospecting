# CLI Reference

**Auto-generated** by `scripts/gen_cli_reference.py` from `scripts/cli.py`.
Do not edit by hand — the pre-commit hook regenerates this file.

All commands assume `--db <path>` is set against `resources/job_history.db`:

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" <subcommand> [args...]
```

## Subcommands

### `bulk-status`

Set the same status on several applications at once (one backup covers the batch)

**Signature:**

```
bulk-status <ids> --status <status> [--at <at>] [--note <note>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `ids` | positional | One or more application IDs |
| `--status` | required |  — choices: `generated`, `applied`, `rejected`, `interview`, `offer`, `dropped` |
| `--at` | optional | When the change actually happened (2026-07-14, 'today', 'yesterday', or a full ISO timestamp). Defaults to now — set it when you're catching up on paperwork, otherwise response-time stats inherit the delay. |
| `--note` | optional | Free-text context stored with the status change |

### `cache-raw-offer`

Write stdin verbatim to <run>/_prep/raw_offer.md as the audit snapshot

**Signature:**

```
cache-raw-offer <target>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Output folder for this run (or its _prep/ subfolder) |

### `check-duplicate`

Step 3.5 — check duplicate / same-company / blacklist against a job_offer_analysis.json

**Signature:**

```
check-duplicate <target> [--url <url>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Path to _prep/job_offer_analysis.json, or a folder containing one |
| `--url` | optional | Override source URL if missing from the offer JSON |
| `--json` | flag | Output as JSON |

### `check-forbidden-labels`

Check titles in a generated JSON against user_prefs.forbidden_title_labels (exit 1 on violation)

**Signature:**

```
check-forbidden-labels <json_file>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `json_file` | positional | tailored_cv.json, role_candidates.json, or selected_role.json to check |

### `company-add`

Add company to list

**Signature:**

```
company-add <name> --list-type <list_type> [--reason <reason>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `name` | positional | Company name |
| `--list-type` | required |  — choices: `blacklist`, `whitelist` |
| `--reason` | optional | Reason for listing |

### `company-check`

Check if company is on a list

**Signature:**

```
company-check <name>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `name` | positional | Company name |

### `company-list`

Show blacklist/whitelist

**Signature:**

```
company-list [--type <type>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--type` | optional |  — choices: `all`, `blacklist`, `whitelist` (default: `all`) |

### `company-remove`

Remove company from list

**Signature:**

```
company-remove <name>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `name` | positional | Company name |

### `count`

Show total application count

**Signature:**

```
count [--since <since>] [--source <source>] [--org-type <org_type>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--since` | optional | Only count apps since date |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |

### `detect-platform`

Print the known aggregator matching the offer's company_name (empty if none)

**Signature:**

```
detect-platform <target>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Output folder for this run (or its _prep/ subfolder) |

### `doctor`

Read-only DB health/fingerprint report; surfaces the temp mirror and any divergence

**Signature:**

```
doctor [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--json` | flag | Emit the report as JSON |

### `export-csv`

Export applications to CSV

**Signature:**

```
export-csv [--output <output>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--output` | optional | Output file path (prints to stdout if omitted) |

### `follow-up`

Applications with no movement since you applied

**Signature:**

```
follow-up [--days <days>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--days` | optional | Minimum days of silence to flag (default: 21) (default: `21`) |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `funnel`

Applications that ever reached each stage, with conversion rates

**Signature:**

```
funnel [--since <since>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--since` | optional | Only include apps since date |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `get`

Get a single application

**Signature:**

```
get <id> [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `--json` | flag | Output as JSON |

### `history`

Show one application's status history

**Signature:**

```
history <id> [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `--json` | flag | Output as JSON |

### `list`

List applications

**Signature:**

```
list [--status <status>] [--company <company>] [--limit <limit>] [--since <since>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--status` | optional | Filter by status (generated/applied/rejected/interview/offer/dropped) |
| `--company` | optional | Filter by company name |
| `--limit` | optional | Max results (default: 50) (default: `50`) |
| `--since` | optional | Only include apps since date (7d/30d/this-week/this-month/ISO) |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `probe-url`

HEAD-probe an offer URL before WebFetch (prints OK / BLOCKED <code> / OTHER_*)

**Signature:**

```
probe-url <url>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `url` | positional | Job-offer URL to probe with a HEAD request |

### `record-application`

Step 10 — read _prep/ artefacts and insert the history row

**Signature:**

```
record-application <target> [--url <url>] [--source <source>] [--language <language>] [--dry-run] [--supersede]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Application id (integer) or path to an output folder |
| `--url` | optional | Override source URL when the offer JSON / profile lacks one |
| `--source` | optional | Override the auto-detected flow (default: 'cold' for cold-* folders, 'offer' otherwise) — choices: `offer`, `cold` |
| `--language` | optional | Detected language for cold flow (default: 'fr'). Ignored for offer flow — that one reads detected_language from job_offer_analysis.json. |
| `--dry-run` | flag | Print the kwargs that would be inserted, then exit (no DB write) |
| `--supersede` | flag | Mark any prior live application to the same company+role as 'dropped' before recording this one, so a re-prospect doesn't leave a parallel active row |

### `regenerate-outputs`

Rebuild DOCX/PDF/TXT/MD from existing _prep/ JSONs (Step 9 only)

**Signature:**

```
regenerate-outputs <target> [--check] [--skip-pdf]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Application id (integer) or path to an output folder |
| `--check` | flag | Only report which _prep/ files are present or missing |
| `--skip-pdf` | flag | Skip PDF conversion (DOCX only) |

### `rename-application`

Atomically rename folder + DB + _prep JSON + run_summary; optionally regenerate outputs

**Signature:**

```
rename-application <id> --new-company <new_company> [--new-slug <new_slug>] [--no-regenerate]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `--new-company` | required | New company name |
| `--new-slug` | optional | Override the auto-derived folder slug (defaults to '{job_title}-{new_company}') |
| `--no-regenerate` | flag | Skip the regenerate-outputs step at the end (rename + DB + JSON only) |

### `rename-cold-folder`

Cold Step 3 — rename the run folder from company_profile.company_name; prints the new path

**Signature:**

```
rename-cold-folder <target>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Cold-flow output folder for this run |

### `rename-with-fit`

Offer Step 4 — rename the run folder with the fit prefix + rebuilt slug; prints the new path

**Signature:**

```
rename-with-fit <target>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Output folder for this run |

### `response-time`

Days between applying and the first employer response

**Signature:**

```
response-time [--since <since>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--since` | optional | Only include apps since date |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `save-cv-cache`

Save _prep/cv_fact_base.json as the shared cache (+ .cv_hash) after the drift guard passes

**Signature:**

```
save-cv-cache <target> [--cv <cv>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Output folder (or _prep/) holding the freshly extracted cv_fact_base.json |
| `--cv` | optional | Master CV path (default: <user-data-dir>/MASTER_CV.docx) |

### `skills`

Show skill gap trends

**Signature:**

```
skills [--limit <limit>] [--since <since>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--limit` | optional | Max skills to show (default: `20`) |
| `--since` | optional | Only include apps since date |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `stats`

Show statistics

**Signature:**

```
stats [--type <type>] [--since <since>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--type` | optional |  — choices: `all`, `status`, `fit`, `company`, `domain`, `org`, `skills` (default: `all`) |
| `--since` | optional | Only include apps since date |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `timeline`

Per-week / per-month application trend (volume, avg fit, status counts)

**Signature:**

```
timeline [--group-by <group_by>] [--basis <basis>] [--since <since>] [--source <source>] [--org-type <org_type>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--group-by` | optional | Bucket size for the trend (default: week) — choices: `week`, `month` (default: `week`) |
| `--basis` | optional | Bucket by pack generation date (default) or by when the application was actually sent — choices: `generated`, `applied` (default: `generated`) |
| `--since` | optional | Only include apps since date |
| `--source` | optional | Only include applications from this flow (offer vs cold/speculative) — choices: `offer`, `cold` |
| `--org-type` | optional | Only include cold-flow rows with this organisation type — choices: `end_employer`, `esn`, `staffing_agency`, `recruitment_agency`, `unknown` |
| `--json` | flag | Output as JSON |

### `update-company`

Rename the company on an application

**Signature:**

```
update-company <id> <name> [--expect-company <expect_company>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `name` | positional | New company name |
| `--expect-company` | optional | Safety guard: refuse if application <id> is not currently this company |

### `update-output-folder`

Update the output_folder path on an application

**Signature:**

```
update-output-folder <id> <path>
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `path` | positional | New output folder path |

### `update-status`

Update application status

**Signature:**

```
update-status <id> <status> [--expect-company <expect_company>] [--at <at>] [--note <note>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `status` | positional |  — choices: `generated`, `applied`, `rejected`, `interview`, `offer`, `dropped` |
| `--expect-company` | optional | Safety guard: refuse if application <id> is not this company (ids can point elsewhere after a DB restore — see `doctor`) |
| `--at` | optional | When the change actually happened (2026-07-14, 'today', 'yesterday', or a full ISO timestamp). Defaults to now — set it when you're catching up on paperwork, otherwise response-time stats inherit the delay. |
| `--note` | optional | Free-text context stored with the status change |
