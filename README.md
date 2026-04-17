# Job Prospecting — a Claude Code plugin

Three [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills that automate a job search end-to-end: generate a fully tailored application pack from a job offer and your master CV, track every application in SQLite, and report on your pipeline.

## What you get

`/job-application-tailor` takes a job offer (URL or pasted text) and your master CV, and produces:

- **Tailored CV** (DOCX + PDF) — restructured for the specific role, every bullet grounded in your master CV
- **Motivation letter** and a **short letter** — natural-voice, not template-generated
- **LinkedIn outreach messages** — with real recruiter/hiring-manager names when they can be found
- **Interview prep guide** — company research, likely questions, talking points
- **Fit score** — honest assessment, not a sales pitch

Nothing is invented. If a claim isn't in your master CV (or your `cv_addendum.md`), it doesn't appear in the output.

### Satellite skills

| Skill | Description |
|-------|-------------|
| `/job-status` | Update application statuses (applied, rejected, interview, offer), filter by status/company, manage blacklist/whitelist, atomically rename an application when the real client surfaces post-fact (e.g. an aggregator-posted job) |
| `/job-stats` | Application statistics, trends, skill gap analysis, exports |

## Install

The plugin is distributed as a Claude Code plugin bundle. You have three install paths.

### A. From a marketplace (once published)

```
/plugin marketplace add <owner>/<repo>
/plugin install job-prospecting@<marketplace-name>
```

### B. From a local directory (dev / trial)

Clone this repo and point Claude Code at it:

```
claude --plugin-dir /path/to/job-prospecting
```

Skills become `/job-prospecting:job-application-tailor`, `/job-prospecting:job-stats`, `/job-prospecting:job-status`.

### C. From a built bundle

```bash
cd .claude/skills/job-application-tailor
python -m scripts.package /path/to/job-prospecting /path/to/dist
# produces dist/job-prospecting/  (tree)
#          dist/job-prospecting.zip
```

The packager runs the full test suite before bundling and refuses to proceed if anything is red. Pass `--skip-tests` to override (not recommended for a release).

## First run

On first invocation the skill creates a user data directory under the OS-standard location:

- **Linux**: `$XDG_DATA_HOME/job-application-tailor/` (falls back to `~/.local/share/...`)
- **macOS**: `~/Library/Application Support/job-application-tailor/`
- **Windows**: `%APPDATA%\job-application-tailor\`

Override with the `JOB_TAILOR_HOME` environment variable.

Inside that directory you'll place:

| File | Required? | Purpose |
|------|-----------|---------|
| `MASTER_CV.docx` | **yes** | Your source-of-truth CV; everything is grounded in this |
| `cv_addendum.md` | no | Off-CV facts, extra experience entries, hidden skills |
| `user_prefs.yaml` | no | Tone directives, forbidden title labels, team-context companies |
| `settings.yaml` | no | Overrides on top of `config/settings.default.yaml` |

Templates for all three optional files ship under `samples/`. Running `python -m scripts.init` copies them into place without ever overwriting existing files.

## Dependencies

Python 3.10+ and the packages in `.claude/skills/job-application-tailor/requirements.txt`:

```
pip install -r .claude/skills/job-application-tailor/requirements.txt
```

PDF generation is cross-platform with three fallbacks in order: `docx2pdf` (Word), LibreOffice (`soffice`), pandoc. DOCX always works; PDF works if any of the three is installed. See `requirements.txt` for per-OS install hints.

## Migrating from a loose project install

If you already used this repo before it became a plugin, your data currently lives at `<repo>/resources/` and `<repo>/output/`. Migrate it with:

```bash
# 1. Take a pre-flight backup (required — migration refuses without it)
cd .claude/skills/job-application-tailor
python -m scripts.backup_user_data /path/to/repo

# 2. Dry run the migration to see the plan
python -m scripts.migrate --legacy /path/to/repo

# 3. Apply it
python -m scripts.migrate --legacy /path/to/repo --apply
```

The migration copies (never moves) every file, rewrites the DB's `output_folder` column to point at the new location, and is idempotent on a second run. Rollback is `python -m scripts.migrate --rollback`.

## Privacy

Your master CV, generated outputs, and application history never enter the repo — everything sits under the user data directory or behind `.gitignore`. The packaging script has a test-enforced exclusion list that blocks user data from ever being bundled.

## Contributing

Implementation roadmap and architectural decisions: [PLUGIN_ROADMAP.md](PLUGIN_ROADMAP.md).

## License

MIT
