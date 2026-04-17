---
name: job-cold-prospect
description: Generate a speculative (cold-call) application pack from a company name or URL — no job offer required. Triggers when the user wants to reach out to a specific company without an advertised vacancy, asks for "cold application", "speculative application", "candidature spontanée", "prospect this company", "reach out to [company]", or supplies a company name/URL and asks for an application pack. Does NOT trigger when a job offer is supplied (use job-application-tailor instead), or for generic company research without an application intent.
argument-hint: [company-name-or-url]
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Agent
---

# Skill: job-cold-prospect

## How it works

This skill produces a speculative application pack — CV, motivation letter, short letter, LinkedIn outreach, and a company dossier with interview prep — targeted at a company with no advertised vacancy. Instead of a job offer, the pipeline pivots on a researched **company profile** and a user-selected **target role**.

Shared infrastructure (master CV, fact base, DOCX generation, history DB, user customization) is reused unchanged from the `job-application-tailor` skill. See `.claude/skills/job-application-tailor/SKILL.md` for the hard rules on truthfulness, chronological integrity, and structural consistency — they apply here identically.

## Directory layout

**`PROJECT_ROOT`** (current working directory) holds your data — shared with `job-application-tailor`:
- `resources/MASTER_CV.docx` — source CV (shared)
- `resources/cv_fact_base.json` + `.cv_hash` — cached extraction (shared)
- `resources/job_history.db` — application history (shared, with new `source` column)
- `output/` — generated packs. Cold packs are prefixed `cold-[DDMMYYYY]-[company-slug]/` to distinguish them from offer-based packs.

**`SKILL_BASE`** (`.claude/skills/job-cold-prospect`) — this skill's own assets:
- `prompts/` — cold-specific prompts (added in Phases B–E)
- `schemas/` — `company_profile.schema.json`, `role_candidates.schema.json` (added in Phases B–C)

**`SKILL_BASE_TAILOR`** (`.claude/skills/job-application-tailor`) — sibling skill, imported:
- `scripts/` — DOCX generation, validation, paths, user customization, history DB, common helpers
- `schemas/` — CV fact base, tailored CV, letter, LinkedIn schemas
- `config/` — settings, naming rules
- `references/commands.md` — exact bash commands for shared operations

Resolve all three at the start. When the master CV format changes, both skills must stay aligned — that is why scripts and schemas live in the tailor skill and are imported, not copy-pasted.

## Hard rules

All hard rules from `job-application-tailor` apply unchanged (truthfulness, recent-timeline completeness, chronological integrity, honest gap handling, structural consistency). On top of those, cold-specific rules:

- **Every factual claim about the company cites a source URL** — the dossier links back to where each fact came from.
- **Inferred fields stay inferred** — `tech_stack_hints`, `pain_points_inferred`, and similar must be flagged as inferred in the dossier, never presented as fact.
- **Research gaps are honest** — if a source is gated or missing, record it in `research_gaps` rather than fabricating content.
- **No fit score** — there is no JD, so no scoreable requirements. The dossier replaces the score with a narrative "angle of approach".

## Workflow

Steps 0–2.5 are reused from `job-application-tailor` unchanged. Steps 3–10 diverge. This scaffold leaves the divergent steps as placeholders; they are filled in across Phases B–G of `COLD_PROSPECT_ROADMAP.md`.

### Step 0 — Pre-flight

Follow `job-application-tailor` SKILL.md § Step 0 verbatim for: verify dependencies, read config, check for master CV (run `python -m scripts.init` in the tailor skill if missing), initialise the job history DB, load user customization into `$CUSTOMIZATION`.

**Resolve paths** — both skills must be on disk:

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-cold-prospect"
SKILL_BASE_TAILOR="$PROJECT_ROOT/.claude/skills/job-application-tailor"
```

**Check dependencies** — same Python stack as the tailor skill:

```bash
cd "$SKILL_BASE_TAILOR" && python -c "import docx, yaml, jsonschema; print('OK')"
```

**Blacklist pre-check against the input name.** The user's input may be an informal short name — the full canonical-name re-check happens in Step 3 once research resolves the real name, so this first pass catches obvious hits early:

```bash
cd "$SKILL_BASE_TAILOR" && python -c "
from scripts.job_history_db import JobHistoryDB
db = JobHistoryDB('$PROJECT_ROOT/resources/job_history.db')
result = db.check_company_list('<input-company-name>')
if result:
    print(f\"{result['list_type'].upper()}: {result['company_name']} — {result.get('reason', 'no reason given')}\")
else:
    print('Not on any list')
db.close()
"
```

If the input hits the blacklist, stop and surface the reason to the user — only proceed on explicit override.

**Create the output folder** — cold packs use a distinct `cold-` prefix so they are visually separate from offer-based packs:

```bash
cd "$SKILL_BASE_TAILOR" && python -u -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from scripts.common import slug_for_filename, ensure_dir, current_date_ddmmyyyy
from pathlib import Path
date = current_date_ddmmyyyy()
slug = slug_for_filename('<company-name-or-url>')
folder = Path('$PROJECT_ROOT/output') / f'cold-{date}-{slug}'
ensure_dir(folder / '_prep')
print(folder)
"
```

Capture the printed path as `$OUTPUT_DIR`, and set `$PREP_DIR="$OUTPUT_DIR/_prep"`.

**Default language.** Cold flow defaults to French (`fr`). Override via `$CUSTOMIZATION["prefs"]["default_language"]` or an explicit user request. There is no JD to auto-detect from.

### Step 1 — Read the master CV

Reused. Follow `job-application-tailor` SKILL.md § Step 1.

### Step 2 — Extract CV fact base (cached)

Reused. Follow `job-application-tailor` SKILL.md § Step 2. The fact base cache is shared with the tailor skill — if the CV has not changed, the cached extraction is reused.

### Step 2.5 — Verify fact base against raw CV

Reused, and mandatory. Follow `job-application-tailor` SKILL.md § Step 2.5. This must complete **before** any company research runs, so the fact base is locked before external context enters the window.

### Step 3 — Company research

Produce a structured profile of the target company. This step anchors every downstream artefact.

**Cache raw research first.** Before assembling the profile, save every raw source you fetch into `$PREP_DIR/raw_research.md` so the pack has an audit trail if the company changes their site. Append one section per source with a heading like `## [website] https://…` and the fetched body.

**Follow the prompt.** Read `prompts/research_company.md` in full — it spells out the source priority (company website → Indeed MCP → LinkedIn → news → tech hints), the hard rules (cite every fact, flag inferences, record gaps), and the output structure.

**Sources — exact tool choices**:

1. Company's own website (About, Careers, Products, Team / Leadership): **WebFetch**
2. Indeed company data: **`mcp__claude_ai_Indeed__get_company_data`** — call with the company name, cite the Indeed company URL
3. LinkedIn company page: **WebFetch** (best-effort; gated results go into `research_gaps`)
4. Recent news (last 12 months): **WebSearch** scoped to `site:news.example OR after:2025-04-17` etc.
5. Tech radar hints: **WebFetch** / **WebSearch** for Stack Share, the company's GitHub org, or job listings even on aggregators

Web tools require foreground approval — do not spawn a subagent for this step.

**Write and validate**:

```bash
# Write the JSON to $PREP_DIR/company_profile.json (via the Write tool), then:
cd "$SKILL_BASE_TAILOR" && python scripts/validate.py \
  "$PREP_DIR/company_profile.json" \
  "$SKILL_BASE/schemas/company_profile.schema.json"
```

Validation must pass before continuing. If it fails, fix the flagged fields and re-run.

**Blacklist re-check against the canonical name.** Research may resolve "acme" to "Acme Robotics SAS" — that new name might itself be on the blacklist, so re-check:

```bash
cd "$SKILL_BASE_TAILOR" && python -c "
import json
from pathlib import Path
from scripts.job_history_db import JobHistoryDB
profile = json.loads(Path('$PREP_DIR/company_profile.json').read_text(encoding='utf-8'))
db = JobHistoryDB('$PROJECT_ROOT/resources/job_history.db')
result = db.check_company_list(profile['company_name'])
if result:
    print(f\"{result['list_type'].upper()}: {result['company_name']} — {result.get('reason', 'no reason given')}\")
else:
    print('Not on any list')
db.close()
"
```

If the canonical name is blacklisted, stop and surface the reason. If the whitelist hits, flag it to the user as a positive signal but continue.

**Phase B stop point.** For now the pipeline ends here: the research has produced `company_profile.json` plus the cached raw research. Summarise the profile back to the user — company name, size band, mission, 3–5 top findings, research gaps — and note that Phases C+ (role inference, tailoring, letters, dossier) are not yet implemented. Do **not** attempt to generate a CV, letter, or LinkedIn pack in Phase B.

### Step 4 — Target-role inference

Without a JD, pick a plausible target role to anchor CV tailoring and letter framing. Always interactive — never auto-select.

**4a. Generate candidates.** Read `prompts/infer_target_role.md` in full. Pass it:
- `cv_fact_base` — from `$PREP_DIR/cv_fact_base.json` (already present after Step 2)
- `company_profile` — from `$PREP_DIR/company_profile.json` (from Step 3)
- `user_prefs` — from `$CUSTOMIZATION["prefs"]`
- any free-form user hints from the invocation

Write the LLM output to `$PREP_DIR/role_candidates.json` and validate:

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/validate.py \
  "$PREP_DIR/role_candidates.json" \
  "$SKILL_BASE/schemas/role_candidates.schema.json"
```

**4b. Forbidden-label post-check.** The prompt tells the LLM to respect `forbidden_title_labels`, but surface-check in Python as a safety net (same spirit as `find_forbidden_title_label_violations` in the tailor skill):

```bash
cd "$SKILL_BASE_TAILOR" && python -c "
import json
from pathlib import Path
candidates = json.loads(Path(r'$PREP_DIR/role_candidates.json').read_text(encoding='utf-8'))
# $CUSTOMIZATION['prefs']['forbidden_title_labels'] — pass in from context
forbidden = $FORBIDDEN_LABELS_PYTHON_LIST  # e.g. ['Backend']
hits = [(i, c['title']) for i,c in enumerate(candidates['candidates'])
        for lbl in forbidden if lbl.lower() in c['title'].lower()]
if hits:
    print('VIOLATIONS:', hits)
else:
    print('OK')
"
```

If violations appear, regenerate 4a — do not ship candidates with forbidden labels.

**4c. Present candidates to the user.** Format the list as a plain-text menu so the user can answer with a number, "generalist", or a free-form title:

```
Based on my research, here are the angles I'd consider for [Company]:

  1. [title] (seniority: [band])
     [rationale — 1-2 lines]
     Emphasises: [emphasis_areas joined]
     Risk: [risk_notes joined]

  2. …

Options:
  - Reply with a number (1–N) to pick that angle
  - Reply "generalist" for an open-to-discussion framing (available: [yes/no based on allow_generalist])
  - Reply with a different title to override

Which one?
```

Wait for the user's response. Do not proceed to Step 5 without one.

**4d. Persist the selection.** Based on the user's reply, build `$PREP_DIR/selected_role.json` conforming to `schemas/selected_role.schema.json`:

| User reply | `source` | `title` | `candidate_index` | Other fields |
|---|---|---|---|---|
| A number `N` | `candidate_pick` | from `candidates[N-1].title` | `N-1` | copy `seniority_band`, `emphasis_areas`, `risk_notes`, `rationale` from the picked candidate |
| `generalist` (only if `allow_generalist: true`) | `generalist` | synthetic — e.g. `"Senior .NET — Desktop & Services, open to scope"` built from CV headline + `preferred_title_labels` | `null` | `seniority_band` inferred from fact base; `emphasis_areas` may be empty; `rationale` notes the open-to-discussion framing |
| Free-form title | `user_override` | user's exact words | `null` | `seniority_band` inferred or `"unspecified"`; `emphasis_areas` empty unless the user volunteered some; `rationale` records it is a user override |

If the user picks `generalist` when `allow_generalist: false`, confirm they want to override before proceeding — small/deep-specialist shops often read "open to discussion" as lack of focus.

Validate the result:

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/validate.py \
  "$PREP_DIR/selected_role.json" \
  "$SKILL_BASE/schemas/selected_role.schema.json"
```

**Phase C stop point.** For now the pipeline ends here: research + selected role are locked. Summarise the pick back to the user — title, source, emphasis areas, risk notes — and note that Phases D+ (CV tailoring, letters, LinkedIn, dossier) are not yet implemented.

### Step 5 — Tailor CV *(placeholder — Phase D)*

Reuses `scripts/generate_outputs.py` and `schemas/tailored_cv.schema.json` from the tailor skill. New prompt `prompts/tailor_cv_cold.md` anchors emphasis on company values/domain instead of JD keywords. **Not implemented in Phase A.**

### Step 6 — Speculative motivation letter + short letter *(placeholder — Phase D)*

New prompts `prompts/generate_motivation_letter_cold.md` and `prompts/generate_short_letter_cold.md`. Reuses `schemas/letter.schema.json`. **Not implemented in Phase A.**

### Step 7 — Cold LinkedIn outreach *(placeholder — Phase E)*

New prompt `prompts/generate_linkedin_cold.md`. Extends `schemas/linkedin.schema.json` with `outreach_type: "cold"`. **Not implemented in Phase A.**

### Step 8 — Company dossier + interview prep *(placeholder — Phase E)*

Merged deliverable replacing the fit-score document. New prompt `prompts/generate_dossier_cold.md`, output to `$OUTPUT_DIR/company_dossier.md`. **Not implemented in Phase A.**

### Step 9 — Generate output files *(placeholder — Phase D/E)*

Reuses `scripts/generate_outputs.py` with new flags `--letter-type speculative` and `--dossier-source`. **Not implemented in Phase A.**

### Step 10 — Record in job history *(placeholder — Phase F)*

Inserts with `source='cold'` and a `company_profile_snapshot`. Requires a migration to add the `source` column. **Not implemented in Phase A.**

## Build status

- **Phase A (scaffold)** — done.
- **Phase B (research pipeline)** — done. Steps 0–3 produce `_prep/company_profile.json` + `_prep/raw_research.md`.
- **Phase C (role inference loop)** — done. Step 4 produces `_prep/role_candidates.json`, prompts the user, writes `_prep/selected_role.json`. `/job-cold-prospect <name>` now runs Steps 0–4 and stops.
- **Phases D–G** — not yet implemented. See `COLD_PROSPECT_ROADMAP.md`.
