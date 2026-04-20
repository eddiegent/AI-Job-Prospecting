# job-cold-prospect

A Claude Code skill that generates a speculative (cold-call) application pack for a target company — no job offer required. Sibling to [`job-application-tailor`](../job-application-tailor/); reuses the same master CV, fact base, DOCX generation, and history DB.

## Status

**Launch-ready (Phases A–G).** `/job-cold-prospect <name-or-url>` runs the full cold-prospect pipeline end-to-end:

1. **Research** (B) — WebSearch / WebFetch / Indeed MCP + blacklist re-check → `_prep/company_profile.json`
2. **Role selection** (C) — 1–3 inferred angles, interactive pick → `_prep/selected_role.json`
3. **CV + letters** (D) — tailored CV DOCX/PDF, speculative motivation letter, short letter (`letter_type: "speculative"`)
4. **LinkedIn outreach** (E) — 2 variants per leadership contact, hiring-manager-targeted
5. **Company dossier** (E) — 9-section deliverable replacing the fit-score document with a narrative angle of approach
6. **History DB** (F) — cold row inserted with `source='cold'` + a company-profile snapshot, segmented from offer-flow rows
7. **Tests + docs** (G) — schema validation tests, DB v2 migration tests, documented sample workflow

See `../../COLD_PROSPECT_ROADMAP.md` for the full design and phased build plan.

## When to use this skill

Use `/job-cold-prospect` (or `/job-cold-prospect <company-name-or-url>`) when you want to reach out to a company that has **no advertised vacancy**. If a job offer exists, use `/job-application-tailor` instead.

Typical triggers:
- "Prospect [company]"
- "Speculative application to [company]"
- "Candidature spontanée chez [company]"
- "Cold application for [company]"

## What it produces

| File | Format | Purpose |
|------|--------|---------|
| `CV_<Candidate>_<Role>.docx` / `.pdf` | DOCX + PDF | CV anchored on the user-selected target role + company values |
| `Lettre_de_motivation_<Candidate>_<Role>.docx` / `.pdf` | DOCX + PDF | Speculative cover letter opening with a specific observation about the company |
| `Lettre_courte_<Candidate>_<Role>.txt` | TXT | 500–750-character email-ready version (same hook as the full letter) |
| `LinkedIn_message_<Candidate>_<Role>.txt` | TXT | Cold connection requests + post-acceptance DMs, hiring-manager-targeted |
| `company_dossier.md` | Markdown | 9-section dossier: glance, angle of approach, contacts, objections, openers, interview prep, transition narrative, research gaps |
| `_prep/*.json` + `raw_research.md` | JSON / MD | Audit trail — company profile, role candidates, selected role, tailored CV JSON, letter JSON, LinkedIn JSON, raw research |
| `run_summary.json` | JSON | Company slug, selected role, file paths, status |

Output folders are prefixed `cold-[DDMMYYYY]-[company-slug]/` so they are visually distinct from offer-based packs. Each run is also recorded in the shared `job_history.db` with `source='cold'` and a compact company-profile snapshot for later stats.

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

## Sample run

```
/job-cold-prospect Dassault Aviation
```

Walkthrough:

1. Pre-flight runs the blacklist check on the input name, resolves output folder (`output/cold-20260420-dassault-aviation/`), and loads user customization.
2. Research fetches the company website, Indeed company data, LinkedIn page (best-effort), and recent news; writes `_prep/company_profile.json` and appends each raw source to `_prep/raw_research.md`. Blacklist re-checks the canonical name.
3. Role inference proposes 1–3 candidate angles. You answer with a number, `generalist`, or a free-form title. The pick is written to `_prep/selected_role.json`.
4. CV tailoring, speculative motivation letter, short letter, LinkedIn outreach, and the company dossier generate in sequence. Between artefacts the skill checks that the motivation-letter hook, LinkedIn connection-request opener, and dossier § 3 all reference the same company fact.
5. `generate_outputs.py` renders DOCX + PDF files; the dossier lands at `$OUTPUT_DIR/company_dossier.md`.
6. A row is inserted into `job_history.db` with `source='cold'` and a compact profile snapshot. The application id comes back so you can update status later with `/job-status`.

You can interrupt between any two steps — the `_prep/` JSONs are idempotent anchor points to resume from.

## Setup

Requires `job-application-tailor` installed alongside (imports its scripts and schemas). See `../job-application-tailor/SETUP.md` for the shared setup — place your master CV at `resources/MASTER_CV.docx`.

## Tests

```bash
cd .claude/skills/job-cold-prospect && python -m pytest tests/ -q
cd .claude/skills/job-application-tailor && python -m pytest tests/ -q
```

The cold-prospect suite covers the three cold-specific schemas and the Phase-E extensions to the shared `linkedin.schema.json`. The tailor suite's Phase-F additions cover the v1→v2 `job_history.db` migration, legacy-row preservation, cold-insert round-trip, and rejection of unknown `source` values.
