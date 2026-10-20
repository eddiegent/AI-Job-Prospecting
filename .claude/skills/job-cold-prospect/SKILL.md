---
name: job-cold-prospect
description: Generate a speculative (cold-call) application pack from a company name or URL — no job offer required. Triggers when the user wants to reach out to a specific company without an advertised vacancy, asks for "cold application", "speculative application", "candidature spontanée", "prospect this company", "reach out to [company]", or supplies a company name/URL and asks for an application pack. Does NOT trigger when a job offer is supplied (use job-application-tailor instead), or for generic company research without an application intent.
argument-hint: "[company-name-or-url]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebFetch, WebSearch, Agent
---

# Skill: job-cold-prospect

## How it works

This skill produces a speculative application pack — CV, motivation letter, short letter, LinkedIn outreach, and a company dossier with interview prep — for a company with no advertised vacancy. Instead of a job offer, the pipeline pivots on a researched **company profile** and a user-selected **target role**.

Everything except the cold-specific prompts and schemas is shared with `job-application-tailor` (master CV, fact base, guards, DOCX generation, history DB, customization), so both flows stay aligned when the CV format changes.

## Directory layout

**`PROJECT_ROOT`** — your data, shared with `job-application-tailor` (master CV, cached fact base, `job_history.db`). Cold packs go in `output/cold-[DDMMYYYY]-[company-slug]/`.

**`SKILL_BASE`** (`.claude/skills/job-cold-prospect`) — this skill's `prompts/` and `schemas/` (`company_profile`, `role_candidates`, `selected_role`).

**`SKILL_BASE_TAILOR`** (`.claude/skills/job-application-tailor`) — everything shared: `scripts/cli.py`, the CV/letter/LinkedIn schemas, `prompts/cv_rules.md`, `config/`, `references/commands.md`, `references/cli.md`, `references/troubleshooting.md`.

Every command below runs as `cd "$SKILL_BASE_TAILOR" && python scripts/cli.py …`. Quote every path.

## Hard rules

All hard rules from `job-application-tailor` SKILL.md apply unchanged (truthfulness, recent-timeline completeness, chronological integrity, honest gap handling, structural consistency), and so does its § Gates: run the named gate after each file, never continue past a failing one, and fix the output — never the master CV, addendum or `.cv_hash`. Cold-specific rules on top:

- **Every factual claim about the company cites a source URL** — the dossier links back to where each fact came from.
- **Classify the organisation type, and let it reframe the pack.** Step 3 sets `company_profile.org_type` (`end_employer` / `esn` / `staffing_agency` / `recruitment_agency` / `unknown`). For an intermediary (ESN/SSII/régie, intérim, cabinet de recrutement) the candidate would be placed on a client's mission or represented to a hiring company — not work on this organisation's own mission. So the role inference, both letters, the LinkedIn target and the dossier switch from "join your team/mission" to "here is the profile I offer for your missions / for you to represent". A "your mission moves me" letter to an ESN is the cold flow's worst tell. Every downstream prompt reads `org_type` and branches.
- **Inferred fields stay inferred** — `tech_stack_hints`, `pain_points_inferred` and similar are flagged as inferred in the dossier, never presented as fact.
- **Research gaps are honest** — a gated or missing source goes in `research_gaps`, never fabricated content.
- **No fit score** — there is no JD to score against. The dossier replaces the score with a narrative "angle of approach".

## Workflow

### Steps 0–2.5 — CV preparation (delegated)

Read `job-prep-cv/SKILL.md` — a sibling of this skill's folder (`.claude/skills/job-prep-cv/` in the repo, `$CLAUDE_PLUGIN_ROOT/skills/job-prep-cv/` when installed as a plugin) — and follow it with:

- `$FLOW = "cold"` (folder `cold-[date]-[slug]/`)
- `$INPUT_SEED = $ARGUMENTS` (company name or URL — seeds a placeholder slug)
- `$EARLY_BLACKLIST_NAME = $ARGUMENTS` (catches obvious hits early; Step 3 re-checks the canonical name)

Then resolve this skill's own base:

```bash
SKILL_BASE="$PROJECT_ROOT/.claude/skills/job-cold-prospect"   # dev/repo layout
if [ ! -d "$SKILL_BASE" ] && [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_BASE="$CLAUDE_PLUGIN_ROOT/skills/job-cold-prospect"   # installed plugin
fi
```

**Language.** Default `fr`; `$CUSTOMIZATION["prefs"]["default_language"]` or an explicit user request overrides it. There is no JD to detect it from. Call the result `$PACK_LANG` (not `$LANG`, which is the shell locale) — Step 4c stores it in `selected_role.json`.

### Step 3 — Company research

Every later artefact is anchored on this profile.

**Cache raw sources as you go.** Append each fetched source to `$PREP_DIR/raw_research.md` under a heading like `## [website] https://…` — the audit trail if the company's site changes.

**Follow `prompts/research_company.md` in full.** It sets the source priority, the rules (cite every fact, flag inferences, record gaps), the **organisation-type classification** (`org_type` + `org_type_evidence` — does the org sell its own product, or sell consultants/missions? the careers/About pages are the main signal), and the output structure. Tools per source:

1. Company website (About, Careers, Products, Team / Leadership): **WebFetch**
2. Indeed company data: **`mcp__claude_ai_Indeed__get_company_data`** with the company name — cite the Indeed company URL
3. LinkedIn company page: **WebFetch**, best-effort (gated → `research_gaps`)
4. News from the last 12 months: **WebSearch** (e.g. scoped with `after:<date 12 months ago>`)
5. Tech hints: **WebFetch** / **WebSearch** on Stack Share, the company's GitHub org, or job listings (aggregators included)

Web tools need foreground approval — don't use a subagent for this step.

Write `$PREP_DIR/company_profile.json` and run **`gate profile`**.

**Re-check the blacklist with the canonical name** — research may resolve "acme" to "Acme Robotics SAS":

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py company-check "<company_profile.company_name>"
```

Blacklisted → stop and give the reason. Whitelisted → mention it as a positive signal and continue.

**Job board instead of an employer.** If `company_profile.company_is_aggregator` is `true`, the company is a job board / recruitment portal (Aerocontact, Free-Work…), not necessarily the employer behind the role that brought the user here. Stop and ask:

> "[Company] looks like a job board / channel, not usually the employer. Did you arrive here via a posting for a specific company? Name the real client to prospect them instead, or say 'the board itself' to continue prospecting [Company] (e.g. to build their platform)."

- Real client named → set `source_platform` to the board's name, make the client `company_name`, and **redo Step 3 research on the client** (the current profile describes the board).
- "The board itself" → continue; the board is a legitimate `end_employer` for its own product.

**Rename the folder** from the placeholder slug to the canonical company name (idempotent):

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py rename-cold-folder "$OUTPUT_DIR"
```

Set `OUTPUT_DIR` to the printed path and `PREP_DIR="$OUTPUT_DIR/_prep"`. Every later file is written after this, so nothing needs path fix-up. If the target folder already exists (an earlier run on the same company), it raises `FileExistsError` — tell the user and let them delete the old pack or pick a different angle.

**Checkpoint.** Summarise the profile for the user — company name, **organisation type** (and whether inferred), size band, mission, 3–5 top findings, research gaps — then continue.

### Step 3.9 — Build the merged fact base (never skip)

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/claims_guard.py merge "$PREP_DIR"
```

Writes `$PREP_DIR/cv_fact_base_merged.json` (fact base + addendum bullets + skill calibration + familiar-only skills). **Every later step reads this file** as "the fact base". It is per-run — never write it back to `resources/`.

### Step 4 — Target-role inference

Without a JD, pick a plausible target role to anchor the CV and letters. Always interactive — never auto-select.

**4a. Candidates.** Follow `prompts/infer_target_role.md` in full, passing the merged fact base, `company_profile.json`, `$CUSTOMIZATION["prefs"]` and any hints from the user's request. Write `$PREP_DIR/role_candidates.json` and run **`gate roles`** — schema, forbidden title labels, and stack grounding (no `tech_stack_hints` technology in a candidate's `emphasis_areas` or rationale unless it is in the fact base; domain phrases are ignored). On failure, regenerate 4a with the flagged labels/technologies named in the prompt.

**4b. Ask the user.** Present a plain-text menu they can answer with a number, "generalist", or a free-form title:

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

Wait for the reply. Do not continue without one.

**4c. Save the selection** as `$PREP_DIR/selected_role.json`, with `language` set to `$PACK_LANG`:

| User reply | `source` | `title` | `candidate_index` | Other fields |
|---|---|---|---|---|
| A number `N` | `candidate_pick` | `candidates[N-1].title` | `N-1` | copy `seniority_band`, `emphasis_areas`, `risk_notes`, `rationale` from the candidate |
| `generalist` (only if `allow_generalist: true`) | `generalist` | synthetic — e.g. `"Senior Java — Platform & APIs, open to scope"` built from the CV headline + `preferred_title_labels` | `null` | `seniority_band` inferred from the fact base; `emphasis_areas` may be empty; `rationale` notes the open-to-discussion framing |
| Free-form title | `user_override` | the user's exact words | `null` | `seniority_band` inferred or `"unspecified"`; `emphasis_areas` empty unless the user gave some; `rationale` records the override |

If the user picks `generalist` while `allow_generalist: false`, confirm first — small or deep-specialist shops often read "open to discussion" as lack of focus.

Run **`gate selected-role`**. An override (or an edited rationale) can reintroduce a stack leak after 4a, and Step 5 onward consumes `emphasis_areas` directly — so on failure, show the violations, ask the user to amend the override or revisit the pick, and re-run.

**Checkpoint.** Summarise the pick — title, source, emphasis areas, risk notes — then continue.

### Step 5 — Tailor the CV

Follow `prompts/tailor_cv_cold.md` (it starts by loading `$SKILL_BASE_TAILOR/prompts/cv_rules.md`, the same CV rules the offer flow uses). Anchor = `selected_role.json` + `company_profile.json`. Pass the merged fact base, `$CUSTOMIZATION["prefs"]` and the `experience_compression_cutoff_year` from settings. Write `$PREP_DIR/tailored_cv.json` and run **`gate cv`** (schema + forbidden title labels + claims check, which here also blocks `tech_stack_hints` technologies absent from the CV).

### Step 6 — Speculative motivation letter + short letter

Follow `prompts/generate_motivation_letter_cold.md` with the merged fact base, company profile, selected role and `$CUSTOMIZATION["prefs"]` (especially `tone_directives` and `team_context_companies`). The letter:

- opens with a specific observation from the profile (prefer `recent_news`, then `mission_statement`, then `products_services`);
- frames the outreach explicitly as speculative — no posting reference;
- sets `letter_type: "speculative"`.

Save `letter.json`. Then follow `prompts/generate_short_letter_cold.md` with the full letter as context → `short_letter.json` (body 500–750 characters, same hook). Run **`gate letters`**.

### Step 7 — Cold LinkedIn outreach

Follow `prompts/generate_linkedin_cold.md` in full, passing the merged fact base, `company_profile.json`, `selected_role.json`, the motivation letter (so hooks stay aligned) and `$CUSTOMIZATION["prefs"]`. It targets **hiring managers / CTO / tech leads** from `company_profile.leadership[]`, not recruiters, with two variants per contact: a ≤300-char connection request and a ≤700-char follow-up message. If `leadership[]` is empty it falls back to one `hiring_manager` pair with a `[Prénom]` placeholder and flags the missing name as a research gap.

Set `outreach_type: "cold"` and `target_role: "<selected_role.title>"` at the root of `linkedin.json`, then run **`gate linkedin`**.

### Step 8 — Company dossier + interview prep

The candidate-facing document the user opens before any conversation with the company; it replaces the fit-score document. Follow `prompts/generate_dossier_cold.md` in full, passing the merged fact base, `company_profile.json`, `selected_role.json`, the tailored CV, the letter, the LinkedIn JSON and `$CUSTOMIZATION["prefs"]`.

Nine sections, in order: Quick reference, Company at a glance, Why you / why them (the angle of approach), Who to contact, Likely objections + answers, Conversation openers, Role-specific interview prep (STAR scaffolds), Transition narrative, Research gaps. Write the Markdown to `$PREP_DIR/company_dossier.md`; Step 9 renders it as mobile-friendly HTML.

**Alignment check.** The opening hook must match across the letter (§ 1), the top contact's connection request, and dossier § 3 "Why you, why them". Mismatched hooks are the most preventable cold-flow mistake — if they diverge, regenerate the LinkedIn or dossier step that drifted.

### Step 9 — Build the output files

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py regenerate-outputs "$OUTPUT_DIR"
```

The `cold-` prefix selects the cold build: title from `selected_role.title` (used in filenames such as `CV_<Candidate>_<Role>.docx`), language from `selected_role.language`, and the dossier instead of interview prep. Result:

- `CV_<Candidate>_<Role>.docx` + `.pdf`
- `Lettre_de_motivation_<Candidate>_<Role>.docx` (`Cover_letter_…` in English; only the CV is converted to PDF)
- `Lettre_courte_<Candidate>_<Role>.txt` (`Short_cover_letter_…` in English)
- `LinkedIn_message_<Candidate>_<Role>.txt`
- `company_dossier.html` (Markdown source kept in `_prep/`)
- `run_summary.json`, plus every intermediate file in `_prep/`

### Step 10 — Record in job history

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py record-application "$OUTPUT_DIR"
```

The `cold-` prefix makes it record `source='cold'`, the `org_type`, and a compact company-profile snapshot, with the offer-only score columns left empty. Language comes from `selected_role.json`; `source_url` from `company_profile.canonical_url` (pass `--url` to record a different page, e.g. the leadership page used for outreach).

**Re-prospecting a company.** A run on a later date lands in a new folder and, by default, records a second live row. First check what exists:

```bash
cd "$SKILL_BASE_TAILOR" && python scripts/cli.py list --company "<company>"
```

If this is a deliberate refresh of the **same role**, add `--supersede` to `record-application`: it marks the earlier live application for that company + role as `dropped`, leaving one active row. A different role at the same company is untouched.

Finally, tell the user: output folder, selected role, source URLs referenced, any `research_gaps` the dossier flagged, and the application id (for `/job-status` updates). Cold rows can be segmented in `/job-stats` with `--source cold` and `--org-type`.
