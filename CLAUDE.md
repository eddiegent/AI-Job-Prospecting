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

## CV fact base must be RE-EXTRACTED when the master CV changes — never "blessed"

The CV fact base (`resources/cv_fact_base.json`) is a cached extraction keyed on
the master CV's SHA-256 hash (`resources/.cv_hash`). When `MASTER_CV.docx`
changes, `preflight` returns **`cache_stale`**. That status is a hard signal to
**re-extract the fact base from the current CV** (job-prep-cv Steps 1–2.5), not
a suggestion.

**Forbidden shortcut:** do NOT reuse the previous fact base and refresh
`.cv_hash` to mark it valid. Historically `verify_fact_base.py` only checked
that technologies/methodologies appear in the CV — it did **not** compare
numeric metrics, so a changed figure (the real incident: CV updated "40+ → 100+
applications" while the fact base still said "40+") passed verification and
shipped stale data into the CV/letter. **That hole is now closed** (see
Guardrail) — the shortcut raises instead of silently succeeding.

**Guardrail (wired into the skill).** Metric drift is now a blocking check:

- `verify_fact_base.py` fails (exit 1) on any salient fact-base metric (carrying
  `+`, `%`, or PB/TB/GB) absent from the CV, alongside the existing
  tech/methodology check.
- `common.save_cv_fact_base()` runs the consistency check **before** writing
  `.cv_hash` and raises `RuntimeError` on drift — so re-blessing a stale fact
  base by hand is impossible, not merely discouraged.
- `preflight` runs the same check on the cache-hit path, downgrading a drifted
  cache to `cache_stale` (forcing re-extraction).

The logic lives once in
`.claude/skills/job-application-tailor/scripts/factbase_consistency.py`
(canonical); the standalone `tools/factbase_consistency.py` re-exports it for
manual / CI use, and a pre-commit hook runs it too:

```bash
python tools/factbase_consistency.py resources/MASTER_CV.docx resources/cv_fact_base.json --check-hash
```

Exit 1 = the fact base is out of sync — re-extract it (job-prep-cv Steps 1–2.5);
do not refresh `.cv_hash` by hand. `tools/factbase_guardrail_WIRING.md` documents
the wiring (now applied).
