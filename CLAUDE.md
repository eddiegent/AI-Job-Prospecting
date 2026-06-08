# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This is a Job Prospecting toolkit — a collection of Claude Code skills for automating and streamlining job search activities.

## Adding Skills

Skills live in `.claude/skills/<skill-name>/SKILL.md`. Each skill is a markdown file with YAML frontmatter:

```yaml
---
name: skill-name
description: When and why to use this skill
---

Instructions for Claude when this skill is invoked.
Use $ARGUMENTS for user-provided input.
```

Key frontmatter fields:
- `name` — becomes the `/slash-command` (lowercase, hyphens, numbers only)
- `description` — tells Claude when to use it
- `disable-model-invocation: true` — only allow manual `/` invocation
- `allowed-tools` — restrict which tools the skill can use
- `argument-hint` — autocomplete hint, e.g. `[job-url]`

Use `!`shell-command`` in skill body to inject dynamic context at invocation time.

## CLI signatures — single source of truth

The `cli.py` argparse parser is the canonical reference. Auto-generated docs live at `.claude/skills/job-application-tailor/references/cli.md`. **Before composing any `cli.py` invocation**, read that file or run `python scripts/cli.py <subcommand> --help` — never compose flags from convention.

A pre-commit hook (`.githooks/pre-commit`) keeps this in sync:
- Regenerates `references/cli.md` when `scripts/cli.py` is staged.
- Lints staged `*.md` files for invocations referencing flags that don't exist on the named subcommand.

One-time setup on a fresh clone:

```bash
git config core.hooksPath .githooks
```

Run manually:

```bash
python .claude/skills/job-application-tailor/scripts/gen_cli_reference.py        # regenerate
python .claude/skills/job-application-tailor/scripts/gen_cli_reference.py --check  # verify
python .claude/skills/job-application-tailor/scripts/lint_cli_usage.py            # lint all *.md
```
