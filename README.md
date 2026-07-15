# Job Prospecting — a Claude Code plugin

Five [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills — four user-facing plus a shared internal sub-skill (`job-prep-cv`) — that automate a job search end-to-end: generate a fully tailored application pack from a job offer and your master CV, send speculative (cold) applications to companies with no advertised vacancy, track every application in SQLite, and report on your pipeline.

**Current release: v1.0.0** (2026-07-15) — git tags `v1.0.0` and `job-prospecting--v1.0.0` (the marketplace version convention). See [CHANGELOG.md](CHANGELOG.md).

## What you get

`/job-application-tailor` takes a job offer (URL or pasted text) and your master CV, and produces:

- **Tailored CV** (DOCX + PDF) — restructured for the specific role, every bullet grounded in your master CV
- **Motivation letter** and a **short letter** — natural-voice, not template-generated
- **LinkedIn outreach messages** — with real recruiter/hiring-manager names when they can be found
- **Interview prep guide** — company research, likely questions, talking points
- **Fit score** — honest assessment, not a sales pitch

Nothing is invented. If a claim isn't in your master CV (or your `cv_addendum.md`), it doesn't appear in the output.

`/job-cold-prospect` does the same for companies with **no advertised vacancy**. Give it a company name or URL and it researches a company profile, helps you pick a target role, and produces a full speculative pack — tailored CV, motivation letter, short letter, LinkedIn outreach, and a company dossier with interview prep. Instead of a fit score (there's no job description to score against), the dossier gives you a narrative "angle of approach", and every factual claim about the company cites a source URL.

It also tells apart **real employers from intermediaries** — an ESN/SSII, an intérim agency, or a cabinet de recrutement — and reframes the whole pack accordingly. For an intermediary you don't get a "your mission moves me" letter aimed at the CTO; you get a profile offer aimed at the business manager or recruiter who actually owns placement.

### Satellite skills

| Skill | Description |
|-------|-------------|
| `/job-status` | Update application statuses (applied, rejected, interview, offer, dropped), filter by status/company, manage blacklist/whitelist, atomically rename an application when the real client surfaces post-fact (e.g. an aggregator-posted job) |
| `/job-stats` | Application statistics, weekly/monthly timeline trends, skill gap analysis, exports |

## Documentation

Full documentation lives in [`docs/`](docs/) as self-contained HTML pages — open any of them directly in a browser. Start at the hub:

**→ [`docs/index.html`](docs/index.html)** — a bilingual (FR / EN) landing page linking every page below.

| Page | 🇬🇧 English | 🇫🇷 Français |
|------|------------|-------------|
| **Overview** — non-technical walkthrough: what it does, the pipeline, the truthfulness guardrail, and a getting-started guide | [overview](docs/job-prospecting-with-ai.html) | [vue d'ensemble](docs/job-prospecting-with-ai.fr.html) |
| **Technical reference** — architecture, end-to-end pipeline, CLI, scripts, database schema, and guardrails | [reference](docs/job-prospecting-technical-reference.html) | [référence](docs/job-prospecting-technical-reference.fr.html) |

> These pages are hand-authored. A pre-commit gate reminds you to update them (and keep the EN/FR versions in step) whenever doc-relevant source changes — see [CLAUDE.md](CLAUDE.md).

## Install

The plugin is distributed as a Claude Code plugin bundle. You have three install paths.

### A. From the marketplace

```
/plugin marketplace add https://github.com/eddiegent/AI-Job-Prospecting
/plugin install job-prospecting@ai-job-prospecting
```

Use the full HTTPS URL — the `owner/repo` shorthand clones over SSH and fails unless you have GitHub SSH keys configured. The `@ai-job-prospecting` suffix is **required** — it disambiguates plugins that share a name across marketplaces; there is no bare-name install. The repo hosts its own [`.claude-plugin/marketplace.json`](https://code.claude.com/docs/en/plugin-marketplaces) catalog: the plugin's source is the repo root, with skill discovery pointed at `.claude/skills/`, so the marketplace install and the dev checkout share one layout.

Note for marketplace testing: `/plugin marketplace add <local-path>` copies the **working tree verbatim** into the plugin cache — it does not respect `.gitignore`. Test local marketplace changes from a clean clone, not from a working copy that holds personal data (`resources/`, `output/`). Installs from GitHub clone the git tree and are unaffected.

### B. From a clone (project skills — dev / trial)

Clone the repo (optionally at the release tag) and open Claude Code inside it — the five skills under `.claude/skills/` load as **project skills**, no plugin install needed:

```bash
git clone --branch v1.0.0 https://github.com/eddiegent/AI-Job-Prospecting.git
cd AI-Job-Prospecting && claude
```

Note: `claude --plugin-dir` must point at a **built bundle** (option C's `dist/job-prospecting/`), not at this repo — plugin auto-discovery scans `skills/` at the plugin root, and the repo keeps its skills under `.claude/skills/`. With the bundle, skills become `/job-prospecting:job-application-tailor`, `/job-prospecting:job-cold-prospect`, `/job-prospecting:job-stats`, `/job-prospecting:job-status`.

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

A pre-commit hook keeps CLI documentation in sync with `cli.py` and lints markdown for stale invocations. One-time setup on a fresh clone:

```bash
git config core.hooksPath .githooks
```

Tests run as two pytest invocations (the suites can't share one process — both declare a `tests` package):

```bash
python -m pytest ".claude/skills/job-application-tailor" -q
python -m pytest ".claude/skills/job-cold-prospect" -q
```

See [CLAUDE.md](CLAUDE.md) for details. The canonical CLI reference is auto-generated at [.claude/skills/job-application-tailor/references/cli.md](.claude/skills/job-application-tailor/references/cli.md).

## License

MIT
