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
- **Classify the organisation type, and let it reframe the pack.** Step 3 sets `company_profile.org_type` (`end_employer` / `esn` / `staffing_agency` / `recruitment_agency` / `unknown`). It is **not** cosmetic: for an intermediary (ESN/SSII/régie, intérim, or cabinet de recrutement), the candidate would be placed on a client's mission or represented to a hiring company — they would *not* work on this organisation's own mission. So the role inference, both letters, the LinkedIn target, and the dossier all switch from "join your team/mission" to "here is the profile I offer for your missions / for you to represent". Writing a "your mission moves me" letter to an ESN is the cold flow's worst tell. Every downstream prompt reads `org_type` and branches.
- **Inferred fields stay inferred** — `tech_stack_hints`, `pain_points_inferred`, and similar must be flagged as inferred in the dossier, never presented as fact.
- **Research gaps are honest** — if a source is gated or missing, record it in `research_gaps` rather than fabricating content.
- **No fit score** — there is no JD, so no scoreable requirements. The dossier replaces the score with a narrative "angle of approach".

## Workflow

Steps 0–2.5 are delegated to the shared `job-prep-cv` sub-skill. Steps 3–10 are cold-flow specific.

### Steps 0–2.5 — CV preparation (delegated)

Read `.claude/skills/job-prep-cv/SKILL.md` and follow its instructions. Pass:

- `$FLOW = "cold"` (selects the `cold-[date]-[slug]/` folder naming, distinct from offer-based packs)
- `$INPUT_SEED = $ARGUMENTS` (the company name or URL — used for the initial folder slug)
- `$EARLY_BLACKLIST_NAME = $ARGUMENTS` (the user's input string — the canonical-name re-check happens in Step 3 once research resolves the real name, so this first pass catches obvious hits early)

Resolve `$SKILL_BASE` for this skill on top of what `job-prep-cv` already set:

```bash
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-cold-prospect"
```

`job-prep-cv` returns with `$PROJECT_ROOT`, `$SKILL_BASE_TAILOR`, `$OUTPUT_DIR`, `$PREP_DIR`, `$CUSTOMIZATION` set, and `$PREP_DIR/cv_fact_base.json` verified.

**Default language.** Cold flow defaults to French (`fr`). Override via `$CUSTOMIZATION["prefs"]["default_language"]` or an explicit user request. There is no JD to auto-detect from.

### Step 3 — Company research

Produce a structured profile of the target company. This step anchors every downstream artefact.

**Cache raw research first.** Before assembling the profile, save every raw source you fetch into `$PREP_DIR/raw_research.md` so the pack has an audit trail if the company changes their site. Append one section per source with a heading like `## [website] https://…` and the fetched body.

**Follow the prompt.** Read `prompts/research_company.md` in full — it spells out the source priority (company website → Indeed MCP → LinkedIn → news → tech hints), the hard rules (cite every fact, flag inferences, record gaps), the **organisation-type classification** (`org_type` + `org_type_evidence`, distinguishing a real employer from an ESN/SSII, an intérim agency, or a cabinet de recrutement), and the output structure. The careers/About pages are the primary `org_type` signal — does the org sell its own product, or sell consultants/missions?

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
cd "$SKILL_BASE_TAILOR" && python -u -c "
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
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

**Canonicalise the folder slug.** Preflight built the output folder slug from the raw `$INPUT_SEED` — usually a URL, often unreadable (e.g. `cold-14052026-https-wwwlinkedincom-company-francebillet/`). Now that research has resolved `company_profile.company_name`, rebuild the slug in one shot. Idempotent — when the slug already matches, this prints the same path back and stops.

```bash
cd "$SKILL_BASE_TAILOR" && python -u -c "
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path
from scripts.common import rename_cold_folder_with_canonical_name
profile = json.loads(Path(r'$PREP_DIR/company_profile.json').read_text(encoding='utf-8'))
new = rename_cold_folder_with_canonical_name(Path(r'$OUTPUT_DIR'), profile['company_name'])
print(str(new))
"
```

Capture the printed path and reassign the orchestrator's shell variables before continuing — every later step reads from these:

```bash
OUTPUT_DIR="<printed path>"
PREP_DIR="$OUTPUT_DIR/_prep"
```

The rename happens **before** `selected_role.json`, the tailored CV, the letters, the LinkedIn output, the dossier, the DOCX/PDF files, the `run_summary.json`, and the history-DB insert are produced — so nothing downstream needs path fix-up. If the target folder already exists (left over from a previous run on the same company), the helper raises `FileExistsError`; surface the error to the user and let them decide whether to delete the old pack or pick a different angle.

**Phase B stop point.** For now the pipeline ends here: the research has produced `company_profile.json` plus the cached raw research, and the output folder is named after the canonical company. Summarise the profile back to the user — company name, **organisation type** (and whether it's inferred), size band, mission, 3–5 top findings, research gaps — and note that Phases C+ (role inference, tailoring, letters, dossier) are not yet implemented. Do **not** attempt to generate a CV, letter, or LinkedIn pack in Phase B.

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
cd "$SKILL_BASE_TAILOR" && python -u -c "
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
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

**4b-bis. Stack-grounding post-check.** Run `scripts/check_role_grounding.py` to confirm no tech listed in `company_profile.tech_stack_hints` has leaked into the candidates' `emphasis_areas` or rationale unless that tech is actually in the candidate's fact base. This is the deterministic guard the 4a prompt cannot enforce on its own.

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/check_role_grounding.py \
  --target "$PREP_DIR/role_candidates.json" --kind candidates \
  --company-profile "$PREP_DIR/company_profile.json" \
  --cv-fact-base "$PREP_DIR/cv_fact_base.json"
```

If the script exits non-zero, **regenerate 4a** with the offending techs surfaced to the prompt — do not ship candidates with stack-mirroring leaks. The check looks at every emphasis_areas item and at rationale prose; it ignores domain phrases (e.g. "Architecture de services") because those don't appear in `tech_stack_hints`.

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

**Stack-grounding re-check.** A user override (or even a candidate-pick whose rationale was edited in flight) can reintroduce a leak after 4b. Run the same guard a second time:

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/check_role_grounding.py \
  --target "$PREP_DIR/selected_role.json" --kind selected \
  --company-profile "$PREP_DIR/company_profile.json" \
  --cv-fact-base "$PREP_DIR/cv_fact_base.json"
```

If non-zero, surface the violations to the user, ask them to amend the override (or revisit the pick), and only proceed once the check passes — Step 5 onward consumes `selected_role.emphasis_areas` directly and any leak here propagates into the CV, letters, LinkedIn, and dossier.

**Phase C stop point.** For now the pipeline ends here: research + selected role are locked. Summarise the pick back to the user — title, source, emphasis areas, risk notes — and note that Phases D+ (CV tailoring, letters, LinkedIn, dossier) are not yet implemented.

### Step 5 — Tailor the CV

Read `prompts/tailor_cv_cold.md`. Anchor = `selected_role.json` + `company_profile.json`. All structural rules from `job-application-tailor` SKILL.md § Step 5 apply unchanged (contact line, skills-section granularity, `role_line` / `metadata_line` split, date format, education/languages conventions, earlier-experience compression).

**Before invoking the prompt**, merge the user's addendum into the in-memory fact base and pass `$CUSTOMIZATION["prefs"]` as context:

```python
from scripts.user_customization import merge_addendum_into_fact_base
fact_base_for_tailoring = merge_addendum_into_fact_base(fact_base, $CUSTOMIZATION["addendum"])
```

The merged fact base must NOT be written back to `resources/cv_fact_base.json`.

Save the output to `$PREP_DIR/tailored_cv.json` and validate against the tailor skill's schema:

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/validate.py \
  "$PREP_DIR/tailored_cv.json" \
  "$SKILL_BASE_TAILOR/schemas/tailored_cv.schema.json"
```

**Forbidden-title post-check** — same as the tailor skill:

```python
from scripts.user_customization import find_forbidden_title_label_violations
violations = find_forbidden_title_label_violations(tailored_cv, $CUSTOMIZATION["prefs"])
# if violations: surface them and regenerate
```

### Step 6 — Speculative motivation letter + short letter

Read `prompts/generate_motivation_letter_cold.md`. Use the fact base, company profile, selected role, and `$CUSTOMIZATION["prefs"]` (especially `tone_directives` and `team_context_companies`) as context. The letter must:

- Open with a specific observation from the company profile (prefer `recent_news`, then `mission_statement`, then `products_services`).
- Explicitly frame the outreach as speculative — no posting reference.
- Set `letter_type: "speculative"` for the audit trail.

Save to `$PREP_DIR/letter.json` and validate against the tailor skill's letter schema (which now accepts `letter_type`):

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/validate.py \
  "$PREP_DIR/letter.json" \
  "$SKILL_BASE_TAILOR/schemas/letter.schema.json"
```

Then read `prompts/generate_short_letter_cold.md`, pass it the full letter as context, save to `$PREP_DIR/short_letter.json`, validate against the same schema. Body between 500–750 characters, same cold-flow hook.

### Step 7 — Cold LinkedIn outreach

Read `prompts/generate_linkedin_cold.md` in full. Pass it: the fact base, `company_profile.json`, `selected_role.json`, the speculative motivation letter (so hooks stay aligned), and `$CUSTOMIZATION["prefs"]`.

The prompt targets **hiring managers / CTO / tech leads** (from `company_profile.leadership[]`), **not recruiters**, and produces two variants per contact — a ≤300-char connection request and a ≤700-char post-acceptance direct message. If `leadership[]` is empty, it falls back to a single `hiring_manager` pair with `[Prénom]` placeholder and flags the missing name as a research gap.

Save to `$PREP_DIR/linkedin.json` and validate against the tailor skill's linkedin schema (now extended with optional `outreach_type` and `target_role`):

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/validate.py \
  "$PREP_DIR/linkedin.json" \
  "$SKILL_BASE_TAILOR/schemas/linkedin.schema.json"
```

**Set `outreach_type: "cold"` and `target_role: "<selected_role.title>"`** at the root of the JSON — these are the cold-flow audit signals carried into the dossier and the run summary.

### Step 8 — Company dossier + interview prep

The merged deliverable that replaces the fit-score document. It is the candidate-facing artefact the user opens before any conversation with the company.

Read `prompts/generate_dossier_cold.md` in full. Pass it: the fact base, `company_profile.json`, `selected_role.json`, the tailored CV JSON, the motivation letter JSON, the LinkedIn outreach JSON, and `$CUSTOMIZATION["prefs"]`.

The dossier has nine sections in order: Quick reference, Company at a glance, Why you / why them (the narrative angle of approach — replaces fit score), Who to contact, Likely objections + answers, Conversation openers, Role-specific interview prep (STAR scaffolds), Transition narrative, and Research gaps.

**Write the Markdown source to `_prep/`** — the dossier is generated as Markdown (easiest for the model to author and for the user to re-run), then Step 9 renders it into the shipped deliverable as responsive HTML (`company_dossier.html`). Markdown reads poorly in a phone/tablet viewer, and the dossier is the artefact the user opens just before a conversation:

```bash
# The LLM output is pure markdown — write it to $PREP_DIR/company_dossier.md via the Write tool.
# Step 9 converts it to $OUTPUT_DIR/company_dossier.html (styled, mobile-friendly).
```

**Alignment check.** Before moving to Step 9, confirm the opening hook is consistent across the motivation letter (§ 1), the LinkedIn connection request for the top contact (first variant), and § 3 "Why you, why them" in the dossier. Mismatched hooks across artefacts is the single most preventable cold-flow mistake. If they diverge, regenerate the LinkedIn or dossier step that drifted — do not ship the pack as-is.

### Step 9 — Generate output files

With Phases D–E complete, the tailor skill's `scripts/generate_outputs.py` receives CV + letters, the LinkedIn JSON, AND the dossier Markdown. Passing `--dossier-markdown` makes the script render `$PREP_DIR/company_dossier.md` into `$OUTPUT_DIR/company_dossier.html` (responsive, mobile-friendly) — the same treatment the offer flow gives its interview prep.

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/generate_outputs.py \
  --tailored-cv-json "$PREP_DIR/tailored_cv.json" \
  --letter-json "$PREP_DIR/letter.json" \
  --short-letter-json "$PREP_DIR/short_letter.json" \
  --linkedin-json "$PREP_DIR/linkedin.json" \
  --dossier-markdown "$PREP_DIR/company_dossier.md" \
  --output-dir "$OUTPUT_DIR" \
  --job-title "<selected_role.title>" \
  --language "<fr|en>"
```

Pass the selected role's title as `--job-title`. The file-naming patterns in `config/naming_rules.yaml` substitute it into filenames like `CV_<Candidate>_<Role>.docx`, `Lettre_de_motivation_<Candidate>_<Role>.docx`, and `LinkedIn_message_<Candidate>_<Role>.txt`. The `cold-` prefix on `$OUTPUT_DIR` already distinguishes the folder from offer-based packs. `--interview-markdown` is deliberately **omitted** in the cold flow — the dossier (passed via `--dossier-markdown`) replaces the interview prep deliverable.

Final pack contents after Step 9:
- `CV_<Candidate>_<Role>.docx` + `.pdf`
- `Lettre_de_motivation_<Candidate>_<Role>.docx` + `.pdf` (`Cover_letter_…` in English)
- `Lettre_courte_<Candidate>_<Role>.txt` (`Short_cover_letter_…` in English)
- `LinkedIn_message_<Candidate>_<Role>.txt`
- `company_dossier.html` (responsive, mobile-friendly; Markdown source kept at `_prep/company_dossier.md`)
- `_prep/` with all intermediate JSONs (`company_profile.json`, `role_candidates.json`, `selected_role.json`, `tailored_cv.json`, `letter.json`, `short_letter.json`, `linkedin.json`) + `company_dossier.md` + `raw_research.md`
- `run_summary.json`

### Step 10 — Record in job history

Insert the generated pack into the shared `job_history.db` so it segments cleanly from offer-based applications. The shared DB is v2: `applications.source` (`'offer'` / `'cold'`) and `applications.company_profile_snapshot` (compact JSON subset of the company profile). Legacy v1 DBs migrate in place on first open.

Use the `record-application` wrapper. The `cold-` folder prefix tells it to take the cold-flow path: read `selected_role.json` + `company_profile.json`, build the snapshot subset, set `source='cold'`, and leave the offer-only scoring columns (`fit_*`, `direct_count`, `transferable_count`, `gap_count`) NULL. `job_skills` rows stay empty by design — the cold flow has no JD to extract requirements from.

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py --db "$PROJECT_ROOT/resources/job_history.db" \
  record-application "$OUTPUT_DIR" --language "<fr|en>"
```

Pass the language explicitly — there is no JD to auto-detect from. Defaults to `fr` if omitted, matching the cold-flow default. The wrapper reads `company_profile.canonical_url` for `source_url`; pass `--url` if you want a different URL recorded (e.g. the leadership page used to anchor the outreach). See `$SKILL_BASE_TAILOR/references/commands.md` § Record Application for the full flag reference.

**Do not touch `job-stats` yet.** Its existing queries keep working because `source` defaults to `'offer'` for legacy rows; cold rows simply show up in counts alongside offer rows until the stats skill gains a `source` filter (tracked as follow-up in `COLD_PROSPECT_ROADMAP.md` Phase F second pass).

After Step 10 completes, summarise back to the user: output folder path, selected role, source URLs referenced, any `research_gaps` the dossier flagged, and the application id for later status updates via `/job-status`.

## Build status

- **Phase A (scaffold)** — done.
- **Phase B (research pipeline)** — done. Steps 0–3 produce `_prep/company_profile.json` + `_prep/raw_research.md`.
- **Phase C (role inference loop)** — done. Step 4 produces `_prep/role_candidates.json`, prompts the user, writes `_prep/selected_role.json`.
- **Phase D (CV + letters)** — done. Steps 5, 6, and a Phase-D variant of Step 9 produce the tailored CV DOCX, motivation-letter DOCX, and short-letter TXT. `letter_type: "speculative"` is recorded.
- **Phase E (LinkedIn + dossier)** — done. Step 7 produces cold-flow LinkedIn messages (2 variants per leadership contact, hiring-manager-targeted, `outreach_type: "cold"` recorded). Step 8 produces `company_dossier.md` — a 9-section deliverable replacing the fit-score document with a narrative angle of approach. `linkedin.schema.json` extended with optional `outreach_type` and `target_role` fields (backwards-compatible).
- **Phase F (history DB)** — done. Shared DB schema bumped to v2: `applications.source` (`'offer'` / `'cold'`) + `applications.company_profile_snapshot`. Existing DBs migrate in place on first open via `ALTER TABLE ADD COLUMN`; legacy rows default to `source='offer'`. Step 10 writes a cold row with a compact snapshot subset of the company profile. `add_application()` rejects unknown `source` values.
- **Phase G (tests + docs)** — done. Cold-prospect skill has a `tests/` directory with 17 schema-validation tests (including backwards-compat checks on the shared LinkedIn schema). Tailor skill has 8 new DB tests covering v1→v2 migration, legacy-row preservation, cold-insert round-trip, bad-source rejection, fresh-DB-at-v2, reopen idempotency, and half-migrated-state recovery. README walkthrough, CHANGELOG, and roadmap all updated. Full suites: **tailor 112 pass / 2 skip**, **cold-prospect 17 pass**.
- **Organisation-type awareness (2026-06-22)** — done. Step 3 now classifies `company_profile.org_type` (`end_employer` / `esn` / `staffing_agency` / `recruitment_agency` / `unknown`) with a citable `org_type_evidence` + `org_type_inferred` flag. Both fields are required in `company_profile.schema.json`. Every downstream prompt (role inference, motivation letter, short letter, LinkedIn, dossier) branches on it: for an intermediary the pack pivots from "join your team/mission" to "the profile I offer for your missions / for you to represent", the LinkedIn target flips from CTO/hiring-manager to business-manager/recruiter, and the dossier's objection-prep swaps in the intermediary's real questions (mission types, TJM, mobility, availability). Cold-prospect suite: **36 pass** (was 17 schema → 25 with 4 new org_type tests, + 11 role-grounding).
- **Post-launch refactor (2026-05-04)** — done. Steps 0–2.5 (pre-flight, master-CV read, fact-base extract, fact-base verify) extracted to a shared `job-prep-cv` sub-skill at `.claude/skills/job-prep-cv/SKILL.md` (`disable-model-invocation: true`). Both `job-application-tailor` and `job-cold-prospect` now delegate to it via a single ~10-line block, eliminating the verbatim "follow tailor SKILL.md § Step X" stubs that previously linked across skills. Folder naming is the only flow-aware branch inside the sub-skill (`[date]-[slug]/` for offer, `cold-[date]-[slug]/` for cold). No Python touched. Test suites unchanged: **tailor 112/2 skip**, **cold-prospect 17 pass**.

**Skill is launch-ready.** `/job-cold-prospect <name>` runs fully end-to-end: research → role pick → tailored CV → motivation letter + short letter → LinkedIn messages → company dossier → history insert.
