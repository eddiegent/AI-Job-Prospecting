# CLI Reference

**Auto-generated** by `scripts/gen_cli_reference.py` from `scripts/cli.py`.
Do not edit by hand — the pre-commit hook regenerates this file.

All commands assume `--db <path>` is set against `resources/job_history.db`:

```bash
cd "$SKILL_BASE" && python scripts/cli.py --db "$DB_PATH" <subcommand> [args...]
```

## Subcommands

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
count [--since <since>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--since` | optional | Only count apps since date |

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

### `list`

List applications

**Signature:**

```
list [--status <status>] [--company <company>] [--limit <limit>] [--since <since>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--status` | optional | Filter by status (generated/applied/rejected/interview/offer/dropped) |
| `--company` | optional | Filter by company name |
| `--limit` | optional | Max results (default: 50) (default: `50`) |
| `--since` | optional | Only include apps since date (7d/30d/this-week/this-month/ISO) |
| `--json` | flag | Output as JSON |

### `record-application`

Step 10 — read _prep/ artefacts and insert the history row

**Signature:**

```
record-application <target> [--url <url>] [--source <source>] [--language <language>] [--dry-run]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `target` | positional | Application id (integer) or path to an output folder |
| `--url` | optional | Override source URL when the offer JSON / profile lacks one |
| `--source` | optional | Override the auto-detected flow (default: 'cold' for cold-* folders, 'offer' otherwise) — choices: `offer`, `cold` |
| `--language` | optional | Detected language for cold flow (default: 'fr'). Ignored for offer flow — that one reads detected_language from job_offer_analysis.json. |
| `--dry-run` | flag | Print the kwargs that would be inserted, then exit (no DB write) |

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

### `skills`

Show skill gap trends

**Signature:**

```
skills [--limit <limit>] [--since <since>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--limit` | optional | Max skills to show (default: `20`) |
| `--since` | optional | Only include apps since date |
| `--json` | flag | Output as JSON |

### `stats`

Show statistics

**Signature:**

```
stats [--type <type>] [--since <since>] [--json]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `--type` | optional |  — choices: `all`, `status`, `fit`, `company`, `domain`, `skills` (default: `all`) |
| `--since` | optional | Only include apps since date |
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
update-status <id> <status> [--expect-company <expect_company>]
```

| Arg | Kind | Description |
| --- | --- | --- |
| `id` | positional | Application ID |
| `status` | positional |  — choices: `generated`, `applied`, `rejected`, `interview`, `offer`, `dropped` |
| `--expect-company` | optional | Safety guard: refuse if application <id> is not this company (ids can point elsewhere after a DB restore — see `doctor`) |
