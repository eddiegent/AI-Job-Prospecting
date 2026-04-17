# job-cold-prospect

A Claude Code skill that generates a speculative (cold-call) application pack for a target company — no job offer required. Sibling to [`job-application-tailor`](../job-application-tailor/); reuses the same master CV, fact base, DOCX generation, and history DB.

## Status

**Phase C — role inference loop.** `/job-cold-prospect <name-or-url>` now runs Steps 0–4 end-to-end. On top of Phase B's research pipeline, Step 4 proposes 1–3 credible target-role angles (title, rationale, seniority, emphasis areas, risk notes), presents them interactively, and writes the user's pick to `_prep/selected_role.json`. Three selection paths: candidate number, "generalist" (open-to-discussion framing), or a free-form title override. The pipeline then stops — tailoring, letters, LinkedIn outreach, dossier, and history DB work land in Phases D–G.

See `../../COLD_PROSPECT_ROADMAP.md` for the full design and phased build plan.

## When to use this skill

Use `/job-cold-prospect` (or `/job-cold-prospect <company-name-or-url>`) when you want to reach out to a company that has **no advertised vacancy**. If a job offer exists, use `/job-application-tailor` instead.

Typical triggers:
- "Prospect [company]"
- "Speculative application to [company]"
- "Candidature spontanée chez [company]"
- "Cold application for [company]"

## What it will produce (once Phases B–G land)

| File | Format | Purpose |
|------|--------|---------|
| Tailored CV | DOCX + PDF | CV anchored on the user-selected target role + company values |
| Motivation letter | DOCX + PDF | Speculative cover letter opening with a specific observation about the company |
| Short motivation letter | TXT | 4-line email-ready version |
| LinkedIn outreach | TXT/JSON | Cold connection request + follow-up message, targeting hiring managers not HR |
| Company dossier | MD | Company profile + angle of approach + contacts + objections + interview prep |
| Run summary | JSON | Company slug, selected role, file paths, research gaps |

Output folders are prefixed `cold-[DDMMYYYY]-[company-slug]/` so they are visually distinct from offer-based packs.

## Shared infrastructure

This skill does not duplicate the tailor skill's Python or schemas. It imports them from `.claude/skills/job-application-tailor/`:

- `scripts/generate_outputs.py`, `scripts/validate.py`, `scripts/paths.py`, `scripts/user_customization.py`, `scripts/job_history.py`, `scripts/cli.py`, `scripts/common.py`
- All CV / letter / LinkedIn schemas
- `config/settings.default.yaml` + `config/naming_rules.yaml`

When the master CV format changes, both skills stay aligned because there is only one source of truth for the extractor and the DOCX generator.

## Hard rules

All hard rules from `job-application-tailor` apply here unchanged — truthfulness, chronological integrity, structural consistency, honest gap handling. Cold-specific additions:

- Every factual claim about the company cites a source URL.
- Inferred fields (tech stack, pain points) are flagged as inferred, not stated as fact.
- Research gaps are recorded honestly, never papered over.
- No fit score — replaced by a narrative "angle of approach" in the dossier.

## Setup

Requires `job-application-tailor` installed alongside (imports its scripts and schemas). See `../job-application-tailor/SETUP.md` for the shared setup — place your master CV at `resources/MASTER_CV.docx`.
