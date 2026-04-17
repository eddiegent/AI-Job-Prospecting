# Cold Prospect Roadmap

Design and multi-session build plan for a new sibling skill, `job-cold-prospect`, that produces a speculative (cold-call) application pack from a company name or URL — no job offer required. Drafted 2026-04-17. Read this before starting any of the phases below.

## Motivation

`job-application-tailor` is offer-driven: every downstream step (tailor CV, motivation letter, LinkedIn, interview prep) reads from `_prep/job_offer_analysis.json`. That leaves a gap for the cold-call / speculative-application workflow, where the user targets a company of interest without an advertised vacancy.

The cold flow pivots on a **company profile** instead of a job offer, and on an **inferred target role** instead of a parsed JD. The rest of the pipeline (CV extraction, DOCX generation, history DB, user customization) is reused unchanged.

## Answered design questions

| # | Question | Decision |
|---|----------|----------|
| 1 | Research sources | Public web (WebSearch + WebFetch) **plus** MCP calls — notably `mcp__claude_ai_Indeed__get_company_data`. LinkedIn/Glassdoor via WebFetch where accessible. |
| 2 | Target-role inference | **Always prompt** the user to pick from 1–3 inferred candidate roles. No silent auto-pick. |
| 3 | Output folder naming | `cold-[YYYY-MM-DD]-[company-slug]/` — distinct prefix from offer-based packs. |
| 4 | Fit score | **Dropped.** No JD means no scoreable requirements. Replaced by a narrative "angle of approach" section in the dossier. |
| 5 | Default language | **French** (`fr`). Override via user prefs or explicit flag. No auto-detection step since there is no JD to detect from. |

## Architecture

**New skill, shared infrastructure.**

- **New** (`.claude/skills/job-cold-prospect/`):
  - `SKILL.md` — cold-specific step flow
  - `prompts/` — new prompts where behaviour diverges (see § Prompts)
  - `schemas/company_profile.schema.json` — new schema
  - `schemas/role_candidates.schema.json` — new schema
  - `README.md`, `CHANGELOG.md`, `plugin.json`

- **Reused** (imported from `job-application-tailor/scripts/` via relative path or packaged shim):
  - `scripts/generate_outputs.py` — DOCX generation
  - `scripts/validate.py` — JSON schema validation
  - `scripts/paths.py` — user data dir resolution
  - `scripts/user_customization.py` — addendum + prefs layer
  - `scripts/job_history.py` + `cli.py` — history DB
  - `scripts/common.py` — helpers (aggregator detection etc.)
  - All existing schemas referenced from tailor_cv / letters / linkedin output

- **Touched**:
  - `schemas/job_history.schema.sql` (or migration) — new `source` column, values `"offer"` (default) | `"cold"`
  - `config/settings.default.yaml` — new `cold_prospect:` block

**Skill-resolution convention.** The cold skill reads `SKILL_BASE_TAILOR=.claude/skills/job-application-tailor` at setup time and pulls scripts/schemas from there. Avoid copy-paste duplication — when the master CV format changes, both skills must stay aligned.

## Pipeline

| Step | Action | New vs. reused |
|------|--------|----------------|
| 0 | Pre-flight: dependencies, config, **blacklist check on company name**, load `$CUSTOMIZATION` | reused |
| 1 | Read master CV DOCX | reused |
| 2 | Extract / load cached fact base | reused |
| 2.5 | Verify fact base against raw CV | reused |
| **3** | **Company research** → `_prep/company_profile.json` | **new** (§ Step 3) |
| **4** | **Target-role inference** → `_prep/role_candidates.json`, user picks one → `_prep/selected_role.json` | **new** (§ Step 4) |
| 5 | Tailor CV anchored on selected role + company values | reused script, **new prompt variant** |
| 6 | Speculative motivation letter + short letter | **new prompts** |
| 7 | Cold LinkedIn outreach (contacts + messages) | **new prompt** |
| 8 | **Company dossier + interview prep** (merged deliverable) | **new prompt** |
| 9 | Generate DOCX/PDF outputs | reused |
| 10 | History DB insert with `source="cold"` + profile snapshot | reused + migration |

## Step 3 — Company research

**Goal**: build a structured profile of the target company to anchor everything downstream.

**Inputs**: company name (or URL); optional user hints like "they do embedded software for medical devices."

**Sources, in priority order**:
1. Company's own website (About, Careers, Products, Team/Leadership pages) — WebFetch
2. `mcp__claude_ai_Indeed__get_company_data` — size, ratings, industry, review snippets
3. LinkedIn company page — WebFetch (best-effort; often gated)
4. Recent news — WebSearch scoped to last 12 months
5. Tech radar hints — Stack Share, GitHub org, job listings from aggregators (even if the company has no current opening matching Eddie's profile, other listings reveal their stack)

**Output** — `_prep/company_profile.json` conforming to a new schema:

```jsonc
{
  "company_name": "…",
  "canonical_url": "https://…",
  "industry": "…",
  "size_band": "startup|scaleup|midmarket|enterprise",
  "headcount_estimate": 250,
  "locations": ["Paris, FR", "…"],
  "founded_year": 2012,
  "mission_statement": "…",                 // their own words, quoted
  "products_services": ["…"],
  "tech_stack_hints": ["…"],                // inferred, flagged as such
  "values_culture_signals": ["…"],
  "recent_news": [
    {"date": "2026-02-14", "headline": "…", "url": "…", "relevance": "…"}
  ],
  "leadership": [
    {"name": "…", "role": "CTO", "source_url": "…"}
  ],
  "hiring_signals": ["currently hiring 3 .NET roles per LinkedIn"],
  "pain_points_inferred": ["…"],             // always flagged as inferred
  "research_gaps": ["could not access LinkedIn page"],
  "sources": [{"url": "…", "fetched_at": "2026-04-17T…"}]
}
```

**Hard rules** (mirrored from the tailor skill's truthfulness stance):
- Every factual claim cites a source URL.
- Inferred fields (`tech_stack_hints`, `pain_points_inferred`) must be marked as inferred in the dossier, not presented as fact.
- If research is thin, `research_gaps` must be non-empty rather than fabricating content.

**Blacklist re-check**: once the canonical name is resolved (might differ from input), re-run the blacklist check before continuing.

**Effort**: ~3 h including schema + prompt + MCP wiring.

## Step 4 — Target-role inference

**Goal**: without a JD, pick a plausible target role to anchor CV tailoring and letter framing.

**Flow**:
1. Read fact base (Eddie's profile: .NET / Desktop & Services, seniority, domains) + company profile.
2. LLM proposes 1–3 candidate roles with: `title`, `rationale` (why this company, why this role, why Eddie), `seniority_band`, `emphasis_areas` (which parts of the CV this angle elevates), `risk_notes` (gaps to expect). Output → `_prep/role_candidates.json`.
3. **Always prompt the user** to pick one, or accept a free-form "generalist / open to discussion" option.
4. Selection persisted to `_prep/selected_role.json`.

**Schema sketch** (`schemas/role_candidates.schema.json`):
```jsonc
{
  "candidates": [
    {
      "title": "Tech Lead .NET – Desktop & Services",
      "rationale": "…",
      "seniority_band": "senior|lead|principal",
      "emphasis_areas": ["Desktop WPF", "service architecture", "…"],
      "risk_notes": ["no cloud-native experience on record"]
    }
  ],
  "generated_at": "2026-04-17T…"
}
```

**Edge cases**:
- User says "generalist" → downstream steps use a synthetic "senior .NET / Desktop & Services, open to scope" placeholder. Motivation letter reframes as "curious to discuss how I could contribute across …" rather than targeting one role.
- None of the candidates fit → user can supply a free-form title which gets wrapped into `selected_role.json` with `source="user_override"`.

**Effort**: ~2 h.

## Step 5 — Tailor CV (adapted)

**Reuses**: `scripts/generate_outputs.py`, `schemas/tailored_cv.schema.json`, fact base.

**New prompt**: `prompts/tailor_cv_cold.md` — diverges from `tailor_cv.md` in two ways:
- Anchor = `selected_role.json` + `company_profile.json` instead of `job_offer_analysis.json`.
- Keyword matching is replaced by **values/domain alignment**: emphasise experience that resonates with the company's stated mission and inferred pain points. No keyword-stuffing since there is no ATS to pass.

All structural hard rules from the tailor skill (chronological integrity, no invention, earlier-experience compression, structural consistency) apply unchanged.

**Effort**: ~1.5 h (mostly prompt crafting + testing).

## Step 6 — Speculative motivation letter + short letter

**New prompts**: `prompts/generate_motivation_letter_cold.md`, `prompts/generate_short_letter_cold.md`.

**Tone spec** (reconciled with `feedback_motivation_letter_tone.md`): natural, conversational, not formal. Opens with **why this company specifically** — grounded in 1–2 concrete facts from the company profile (recent news, product, stated mission), not boilerplate. Never implies solo work at Oodrive.

**Structure**:
1. Opening hook — a specific observation about the company (from `recent_news` or `mission_statement`).
2. Why Eddie — 2–3 lines tying his experience to the company's apparent needs (without claiming knowledge of internal priorities).
3. What he's proposing — conversation, not application: "I'd like to explore whether there's a role where I could contribute to …"
4. Close — offer to discuss, signature.

Short letter = 4-line email-ready version with the same hook and ask.

**Schema**: reuses `schemas/letter.schema.json` with a new optional field `letter_type: "speculative"`.

**Effort**: ~1.5 h.

## Step 7 — Cold LinkedIn outreach

**New prompt**: `prompts/generate_linkedin_cold.md`.

**Differences from the offer-based flow**:
- Target contacts are **hiring managers / CTO / head of engineering**, not HR. The research step tries to surface names from `leadership[]` in the company profile.
- Messages are shorter (<300 chars for initial outreach), lead with a specific observation about the company, and **do not reference a posting**.
- Generates two variants: a connection request (no posting reference) and a direct message for after acceptance.

**Schema**: extend `schemas/linkedin.schema.json` with `outreach_type: "cold"` and `target_role` (distinct from HR path).

**Effort**: ~1 h.

## Step 8 — Company dossier + interview prep (merged)

**Goal**: one deliverable the user reads before any conversation with the company. Replaces the fit-score document.

**New prompt**: `prompts/generate_dossier_cold.md`. Output: `company_dossier.md` in the output folder.

**Sections**:
1. **Company at a glance** — distilled from `company_profile.json` (5-bullet version).
2. **Why you, why them** — narrative angle of approach (replaces fit score).
3. **Who to contact** — ordered list of named contacts with rationale, source URL, suggested first-message template.
4. **Likely objections** — "Why are you reaching out without a posting?" etc., with prepared answers grounded in the profile.
5. **Conversation openers** — 3–5 specific questions tied to recent news / products.
6. **Interview prep** — standard prep questions adapted to the inferred role, with STAR-style answer scaffolds drawn from the fact base.
7. **Research gaps** — honest list of what we couldn't verify, so the user knows where to tread carefully.

**Effort**: ~2 h.

## Step 9 — Generate outputs

**Reuses** `scripts/generate_outputs.py` unchanged except for two additions:
- Accept `--letter-type speculative` flag to trigger the cold filename convention.
- Accept `--dossier-source _prep/company_dossier.md` to include the dossier in the output pack.

Final pack contents:
- `CV-[lastname]-[company-slug]-[YYYY-MM-DD].docx` + `.pdf`
- `motivation-letter-[company-slug]-[YYYY-MM-DD].docx` + `.pdf`
- `short-letter.md`
- `linkedin.md` (or `.json` + rendered messages)
- `company_dossier.md`
- `_prep/` with all intermediate JSONs + `raw_research.md`

**Effort**: ~1 h (mostly CLI wiring + tests).

## Step 10 — History DB

**Migration**: add `source TEXT NOT NULL DEFAULT 'offer'` to `applications` table. Backfill existing rows to `'offer'`.

**Cold insert**:
- `company_name`, `output_folder`, `generated_at`, `source='cold'`
- `job_title` = selected role title
- `company_profile_snapshot` (new JSON column) = subset of `company_profile.json` for later dashboards
- `status='generated'` per existing lifecycle

**`job-stats` implications**: update queries to segment by `source`. Minor — one new grouping column in existing reports. Not a blocker for launch; can follow in a second pass.

**Effort**: ~1.5 h including migration testing against an existing populated DB.

## Rollout phases

Each phase is one commit, independently revertible. Status checkboxes track progress across sessions.

- [ ] **Phase A — Scaffold** (~1 h): skill dir, `SKILL.md` skeleton with reused Steps 0–2.5 delegating to tailor skill, `plugin.json`, `README.md` stub. No prompts yet. Confirms the shared-infrastructure pattern works.
- [ ] **Phase B — Research pipeline** (~3 h): Step 3 prompt + schema + MCP wiring + blacklist re-check. Ends with a working `/job-cold-prospect <name>` that writes `_prep/company_profile.json` and stops.
- [ ] **Phase C — Role inference loop** (~2 h): Step 4 prompt + schema + interactive selection. Ends with `_prep/selected_role.json` written after user picks.
- [ ] **Phase D — Tailor CV + letters** (~3 h): Phases 5 + 6 prompts + DOCX output for CV and motivation letter. First end-to-end dry run possible.
- [ ] **Phase E — LinkedIn + dossier** (~3 h): Steps 7 + 8. Full output pack complete.
- [ ] **Phase F — History DB + cold source** (~1.5 h): migration + insert path + `job-stats` segmentation.
- [ ] **Phase G — Tests + docs** (~1.5 h): unit tests for new schemas + prompts, README, CHANGELOG, sample run against a real company. Ready-to-ship check.

**Total budget ~15 hours.** Suggested cadence:
- **Session 1**: A + B (scaffold + research)
- **Session 2**: C + D (role inference + first outputs)
- **Session 3**: E (LinkedIn + dossier)
- **Session 4**: F + G (DB, tests, docs)

## Out of scope (for now)

- **Auto-monitoring for openings** — watching a target company and re-triggering the tailor skill when they post a matching JD. Nice, but a separate feature.
- **Email drafting via Gmail MCP** — the dossier includes copy-paste-ready text; automated send stays manual until the cold flow proves itself.
- **Multi-company batch mode** — "run cold prospect for these 20 companies." Wait for the single-company flow to stabilise first.
- **Company-profile caching** — reuse `company_profile.json` across multiple cold runs on the same company. Revisit once a real workflow pattern emerges.
- **Fit scoring re-introduction** — if dropping the score turns out to hurt decision-making, revisit with a reworked metric (e.g. "role-fit" tied to `selected_role.json` rather than JD keywords).
