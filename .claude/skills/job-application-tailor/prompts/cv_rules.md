# Shared CV-tailoring rules — offer flow and cold flow

These rules apply to **both** CV-tailoring prompts:

- `job-application-tailor/prompts/tailor_cv.md` — **offer flow** (a job offer exists, with a match analysis)
- `job-cold-prospect/prompts/tailor_cv_cold.md` — **cold flow** (no job offer; anchored on `selected_role.json` + `company_profile.json`)

The flow prompt lists its inputs, its goal and its flow-specific rules. Every rule in this file applies in addition. Where a rule differs by flow, it carries a short **(offer flow)** / **(cold flow)** note.

Vocabulary used below:

- **the target role** — the job offer (offer flow) or the selected role angle at the researched company (cold flow).
- **role-side inputs** — what describes the target, not the candidate: `job_offer_analysis` + `match_analysis` (offer flow); `selected_role` + `company_profile` (cold flow). Role-side inputs never confer competence on the candidate.

## Fact-base input — the merged fact base

Read `$PREP_DIR/cv_fact_base_merged.json` (produced by `scripts/claims_guard.py merge`), NOT the plain fact base. It is the cached fact base plus the user's addendum: the extra bullets appear as normal `experience[*].details` entries, hidden skills / off-CV facts appear under `addendum_hidden_skills` and `addendum_off_cv_facts` when present, and it also carries `addendum_skill_calibration` and `familiar_only_skills`. Every `cv_fact_base.<field>` below means this merged file.

## Candidate location

Include the candidate's residential location (from `candidate_location` in the CV fact base) in the `contact_line` field alongside email, phone, and LinkedIn. Location is valuable on a CV — it tells the recruiter at a glance whether the candidate is local, nearby, or would need to relocate. Keep the original format from the CV (e.g. "Lyon (69)", "London, UK").

**(cold flow)** Geographic proximity to `company_profile.locations[0]` (when close) is useful context for the motivation letter — not for the CV.

## Summary sourcing — every clause must be traceable

`summary_paragraphs` and `tagline` are the freest-form prose in the CV and are where embellishment most easily creeps in. Every clause you write in them must be traceable to one of:

- `cv_fact_base.summary`
- a concrete fact already present in `cv_fact_base.experience[*].details`
- `cv_fact_base.transition_signals` (for forward-looking / in-progress language)
- `cv_fact_base.addendum_hidden_skills` or `cv_fact_base.addendum_off_cv_facts`

If a clause cannot be traced to one of those sources, drop it. Do not infer it from the role-side inputs, or from what would make the candidate "sound better for this role". The summary is prose, not a wishlist.

- **(offer flow)** Not from the job offer, and not from the match analysis's `requirement` field.
- **(cold flow)** Not from `selected_role.emphasis_areas`, and not from `company_profile.tech_stack_hints` (which are **inferred** about the company, not claims about the candidate).

Applies equally to the `tagline`: each bullet-point in the tagline must point back to a fact-base source, not to role-side vocabulary (job-offer wording, emphasis areas, stack hints).

## Active-learning / in-progress phrasing

Do not introduce tense/phase language for a technology — phrases like *"en apprentissage"*, *"en cours de formation"*, *"en montée en compétences sur X"*, *"learning X"*, *"ramping up on X"* — unless that specific technology appears by name in `cv_fact_base.transition_signals`. Transition signals come from the candidate; they are not inferred from the role-side inputs (the job offer's requirement list, the selected role, or the company profile).

## Preserving skill sections

The master CV may contain dedicated skill/competency sections beyond the main technical skills table (e.g. "Leadership", "Domain expertise", "Data & Analytics"). These sections are part of the candidate's professional identity. Every such section must appear in the tailored CV's `skills_sections` array — you may reorder them for relevance but never drop them entirely. Check the CV fact base `technologies` and the raw CV structure to ensure no dedicated section is lost.

## Training periods belong in Education, not Work Experience

The master CV keeps Formation (training) and Expérience Professionnelle (work experience) as two separate sections. The tailored CV must mirror that. When building the `experience` array, skip any entry in the fact base whose `type` field is `"training"` (e.g. "Acme Academy — Data Analyst Bootcamp", "Globex Institute — Programming Course"). Those entries appear only in the `education` array.

This matters because a line like *"Data Analyst (Formation temps plein) — Acme Academy"* under Work Experience reads to a recruiter as a mislabeled employment row even when the "(Formation temps plein)" tag is there. The human reader expects Work Experience to be paid employment. Training stays in Education, where it signals recent upskilling exactly as intended.

Small visible timeline gaps in the experience section are acceptable; mixing training into Work Experience is not. Note: the fact base extraction step (`prompts/extract_cv_data.md`) deliberately adds training periods to the fact base `experience` array for internal timeline analysis — that's a different layer, and this rule only governs the *tailored CV output*.

## Personal projects — passthrough with light filtering

If `cv_fact_base.projects` is present and non-empty, build a `projects` array in the tailored CV from it. Each item has:
- `name` — project name, verbatim from the fact base.
- `metadata_line` — a single line combining dates and link. Build it from the fact base fields: if both `dates` and `link` are present, use `"<dates> | <link>"`; if only one is present, use that one alone; if neither, omit the field entirely.
- `bullets` — the project's description points.

**Allowed:**
- Reorder bullets within a project to lead with the most relevant for the target role.
- Drop individual bullets that are tangential to the target role.
- Drop an entire project if it is **clearly unrelated** to the target role's domain (e.g. a cooking blog for a back-end infra role). The default is to keep every project — personal projects are a strong authenticity signal for mid-to-senior candidates, and dropping one is the exception, not the rule.

**Forbidden:**
- Inventing a project, a bullet, a date, or a link that isn't in the fact base.
- Rewording a bullet to inject role-side vocabulary (job-offer wording, emphasis areas, stack hints) — same rule as work experience: keyword coverage belongs in the skills section.
- Promoting work done inside a paid role into a "personal project" entry.

If `cv_fact_base.projects` is absent or empty, **omit the `projects` field entirely** from the tailored CV. Many candidates don't have a side-projects section; the renderer collapses the whole Projects section cleanly when the field is absent.

## Earlier-experience compression

Senior profiles can carry 20+ years of history. Recruiters rarely read past the first page. To respect that attention budget — without ever hiding evidence the target role actually relies on — apply this rule before writing the `experience` array.

### Step 1 — Split the roles at the cutoff

Let `CUTOFF` be the value of `experience_compression_cutoff_year` passed in as context. If it is `null`, skip this whole section and keep every role full.

For each role in the CV fact base:
- If the role's **end date** is January `CUTOFF` or later → **recent role**. Always kept full.
- If the role's end date is strictly before January `CUTOFF` → **pre-cutoff role**. Candidate for consolidation, check load-bearing criteria below.

Use the end date, not the start date. A role that straddles the cutoff (e.g. start 2003, end 2008 with cutoff 2005) counts as a recent role.

### Step 2 — Decide which pre-cutoff roles are load-bearing

A pre-cutoff role is **load-bearing** if *any* of these are true. If yes, keep it in the experience list with its normal bullets. If no, set it aside for consolidation.

**Criterion A — evidence anchoring.**
- **(offer flow)** Search `match_analysis.json` for any match of type `direct` or `transferable` whose `evidence` field mentions this role's company name or its date range. If found, the role is load-bearing — the match analysis is pointing directly at it.
- **(cold flow — anchor alignment)** There is no `match_analysis.json`, so Criterion A is replaced: does this role provide concrete evidence for one of `selected_role.emphasis_areas`, or for a technology in `company_profile.tech_stack_hints` that a recent role does not already amply cover? If yes, load-bearing.

**Criterion B — Unique technology overlap.** Does the role's technology stack intersect with what the target role asks for, for a technology that is **not** already amply covered by a recent (post-cutoff) role?
- **(offer flow)** "What the target role asks for" = the job's `required_skills` or `preferred_skills`.
- **(cold flow)** "What the target role asks for" = `company_profile.tech_stack_hints` (inferred) or the candidate's headline specialisations.
- Example: COBOL appears only in pre-cutoff roles → if the target role asks for (or the company hints at) COBOL, those roles are load-bearing.
- Counter-example: Java appears briefly in a pre-cutoff role, but the candidate has a decade of Java in a post-cutoff role → the pre-cutoff exposure is redundant, not load-bearing on its own.

**Criterion C — Unique responsibility coverage.** Is the role the best or only evidence for a key responsibility the target role explicitly calls out — the job offer (offer flow) or the selected-role angle (cold flow) — e.g. reverse engineering, a specific legacy-language migration, a domain-specific pattern, experience writing technical specifications for clients?
- Example: "a COBOL → Java migration at an earlier employer" is the best evidence for a legacy-migration responsibility → load-bearing.
- If the same responsibility is better evidenced by a post-cutoff role, the pre-cutoff role fails this criterion.

If none of A, B, C apply, the role goes into the consolidated line.

### Step 3 — Build the consolidated line (if any role was set aside)

If any pre-cutoff roles were set aside in Step 2, append **one single entry** to the end of the `experience` array, after the last recent or load-bearing role. The entry must:

- Put a language-appropriate heading in `role_line`:
  - French: `"Expériences antérieures"`
  - English: `"Earlier experience"`
  - Other target languages: translate the heading appropriately. The rest of the CV already tells you which language to write in.
- Put the **pipe-separated company names only** in `metadata_line`, with **no dates** (e.g. `"Globex SA | Initech"`). Dateless on purpose: presents earlier experience as context without inviting age-based filtering.
- Contain **one single bullet** in `bullets` that summarises the aggregate scope of the consolidated roles: the core tech, the general domain, and the high-level contribution (development, project coordination, writing specifications), written as described in § Earlier-experience line — wording rules (one opening sentence, then one clause per employer). Keep it to about three lines in the rendered output. Write it in the same language as the rest of the CV.

Companies in the consolidated line appear in reverse-chronological order to match the rest of the experience section.

### Step 4 — Edge cases

- **All pre-cutoff roles are load-bearing.** Do nothing special — no consolidated line is produced. This is what happens when the target role leans heavily on older experience (e.g. a COBOL modernisation role for a candidate whose COBOL years were all pre-cutoff).
- **No pre-cutoff roles exist at all.** Do nothing. The rule is a no-op.
- **Mixed: some load-bearing, some not.** Keep the load-bearing ones as normal entries in their chronological position, and add the consolidated line after the last recent/load-bearing entry. The result is a mostly-compact experience section with a couple of older entries surfaced where they matter.

### Why this exists

Senior candidates lose recruiter attention before they reach their best match when early-career roles take up half the experience section. Compression moves the reader's eye to what actually matters for the target role. Load-bearing roles still surface in full because hiding them would defeat the point of tailoring. Dateless consolidation acknowledges prior depth without anchoring the reader to an exact starting year — a small but real mitigation against age-based filtering.

The rule is load-bearing-aware, not hard-capped: it trusts the role-side evidence — the match analysis (offer flow), or `selected_role` + `company_profile` (cold flow) — to tell the truth about which older roles this specific target needs. That means the quality of that evidence directly drives the quality of the compression.

## Earlier-experience line — wording rules (added after a blended-line incident)

The single bullet of the consolidated "Expériences antérieures" / "Earlier experience" entry must read as a short, natural sentence, never as a keyword list.

- **One clause per employer, in the same order as the company names in `metadata_line`** (reverse-chronological), each introduced by the employer's short name and a colon.
- **Attach each language, tool and system only to the employer(s) where the fact base / addendum says it was used.** Read the per-employer notes in the merged fact base (`experience[*].details`) and `addendum_skill_calibration` first. Never write a combined phrase like "Java et C++ sous Linux" that spreads technologies used at different employers across all of them. An opening phrase may name only technologies that the listed employers genuinely share.
- **Disambiguate same-name employers.** If the same company name also appears as a full entry elsewhere in the CV (e.g. a recent "Acme Corp" role in Paris and an older Acme Corp role in Lyon), add the location in the heading line: "Acme Corp (Lyon)".
- Keep it dateless (company names only in `metadata_line`) and keep it to one bullet of about three lines.
- Template: `<Parcours général, une phrase>. <Employeur 1> : <ce qui y a été fait>. <Employeur 2> : <…>. <Employeur 3> : <…>.`

## Structural consistency — these formats must never vary between runs

The following formatting rules are derived from the master CV and must be applied identically regardless of the target role (contact line, skills-section granularity, experience `role_line` / `metadata_line` split, date format, education date format, languages line — all inherited unchanged from the master CV):

### Contact line
Use the labeled format from the master CV:
`Email: <email> | Tel: <phone> | LinkedIn: <linkedin> | <location>`

If `cv_fact_base.contact.github` is present, insert `| GitHub: <github>` between the LinkedIn segment and the location:
`Email: <email> | Tel: <phone> | LinkedIn: <linkedin> | GitHub: <github> | <location>`

If `contact.github` is absent from the fact base, omit the GitHub segment entirely — do not leave a dangling label and do not invent a URL. The renderer auto-splits long contact lines across two centered lines at the midpoint, so adding GitHub is safe.

### Skills sections
Preserve the master CV's granular skill categories as separate `skills_sections` entries. Each category from the skills table becomes its own section with its own heading (e.g. "Langages", "Frameworks", "Bases de données", "Cloud & DevOps", "Outils", "Méthodes"). Do not consolidate multiple categories into a single section. Dedicated sections outside the table (e.g. "Leadership") are also preserved as separate entries. You may reorder sections for relevance but never merge or drop them.

**Proficiency honesty — `technologies_to_deepen`.** Items in `cv_fact_base.technologies_to_deepen` are familiar-but-not-mastered (or only evaluated, not adopted). They must NEVER be mixed into a core skills group. If some are relevant to the target role, surface them only in a single clearly-labelled trailing section — heading `"Familier / à approfondir"` (FR) or `"Familiar / exploring"` (EN) — after the core skill sections; otherwise omit them. Never present an evaluated-not-adopted technology (e.g. a database the CV says was evaluated and rejected in favour of another) as a held skill anywhere in the CV.

### Experience line format
Each experience entry has two separate fields:
- `role_line` — the role/job title **only** (e.g. `"IT Project Manager"`, `"R&D Engineer"`, `"Development Manager"`). No company, no dates. Rendered bold on its own line.
- `metadata_line` — a single pipe-separated string `"Company | Location | Month YYYY – Month YYYY"` (e.g. `"Acme Corp | Paris | July 2010 – March 2025"`). Rendered italic-gray on its own line directly under the role.

This matches how ATS parsers expect to find role, employer, and dates — each on its own clear line rather than merged.

### Date format
Use `Month YYYY – Month YYYY` consistently across the `experience` array (e.g. `"July 2010 – March 2025"`). Use the full month name in the target language (`"July"` in English, `"juillet"` in French). Use an en-dash ` – ` (not a hyphen `-`). Never abbreviate months. Never mix formats inside the CV.

For the consolidated `Earlier experience` entry (if any), the `metadata_line` is intentionally dateless: put only the pipe-separated company names there (e.g. `"Globex SA | Initech"`). The `role_line` stays `"Earlier experience"` (or the target-language equivalent from § Earlier-experience compression).

### Education dates
Reproduce date formatting as it appears in the master CV. Do not reformat dates (e.g. don't expand 2-digit years to 4-digit, don't change separators).

### Languages
Reproduce the languages section as it appears in the master CV. If the CV uses a single consolidated line (e.g. "Français natif / Anglais courant"), keep it as one entry. Do not split into separate entries.

## Evidence ledger — no claim without a source (added after an over-claiming incident)

The merged fact base (§ Fact-base input) is the ledger: it contains the user's addendum bullets, `addendum_skill_calibration` and `familiar_only_skills`.

- **Every skill, tool, claim and bullet must trace to the master CV or the addendum.** Never add a technology to `skills_sections` because the job posting (or a role-side input) lists it or because it "feels adjacent". Do not add skills that are absent from the master CV's skills table (e.g. a tool named only once in passing in an old bullet, or a broader umbrella term than the table actually lists) unless the addendum states them.
- **Copy the master skills table as written, then only reorder.** Keep qualifiers verbatim: a skill the master CV qualifies, such as `Terraform (reading existing modules)` or `TDD (on new code only)`, keeps that qualifier exactly as written.
- **`familiar_only_skills` (the master's "Familier / à approfondir" row) may appear ONLY in a trailing section headed "Familier / à approfondir"** — never in a core skills section, tagline, title or summary.
- **No intensity / frequency / duration wording unless a source states it.** Forbidden unless sourced: "pratique quotidienne", "au quotidien", "tous les jours", "depuis N ans" attached to a specific technology, "expert", "maîtrise". The only durations allowed are those in the master CV (e.g. a "10+ ans en Java" that the master CV itself states).
- **Describe what was done, not how often.** "Remplacement d'une API SOAP par une API REST" is a fact; "pratique de SOAP" is an invention. A technology that only appears in a skills table without a described use is listed as a skill — it is not described as practised.
- **Respect `addendum_skill_calibration`**: it records the real scope of each skill (employer, team vs solo, tuning vs design). Wording must stay inside it.
- **Use the addendum.** Pick the bullets that support the target role's real requirements (support, production follow-up, documentation, migrations, team context) and phrase them as written there.
- **Tagline/summary come from the master CV's own profile text**, lightly reordered. Do not copy job-posting (or other role-side) vocabulary into them.

After writing `tailored_cv.json`, the flow runs the deterministic CV gate — `python scripts/cli.py gate cv "$PREP_DIR"` from the job-application-tailor skill directory (schema + forbidden title labels + claims check; see the flow's SKILL.md). Exit 1 = fix the wording and re-run. Never "fix" a failure by editing the master CV or the addendum.

## Forbidden

- Inventing projects, achievements, tools, certifications, or leadership claims
- Adding keywords not evidenced in the CV
- **Injecting adjectives not in the fact base** — do not attach modifiers like *"cloud-native"*, *"event-driven"*, *"distributed"*, *"mission-critical"*, etc. to an existing fact unless that exact adjective (or a clear equivalent) is already in the fact base. Promoting *"une plateforme de paiement"* to *"une plateforme de paiement cloud-native"* is invention, not emphasis.
- **Relabeling experience to match role-side vocabulary** — if the fact base describes a piece of work one way (e.g. *"migration d'une base de données vers PostgreSQL"*) and the target role calls it something else (e.g. *"intégration de systèmes tiers"*), keep the fact base's framing. Keyword coverage belongs in the skills section, not in reworded bullets.
  - **(offer flow)** Applies to job-offer vocabulary. The match analysis already records the correspondence; the CV does not need to force-align the vocabulary.
  - **(cold flow)** Applies to `selected_role.emphasis_areas` and `company_profile.tech_stack_hints`; keyword-style alignment belongs in the skills section.
- **Claiming active learning or in-progress competence for a technology** — see § Active-learning / in-progress phrasing. Phrases like *"en apprentissage"*, *"en cours de formation"*, *"en montée en compétences sur X"*, *"learning X"*, *"ramping up on X"* are only permitted when the specific technology appears in `cv_fact_base.transition_signals`. The role-side inputs (gap requirements, the selected role, company stack hints) do not justify such claims.
- **Dropping dedicated skill sections** from the master CV — if the original CV has a section like "Leadership" or "Data & Analytics", it must appear in the tailored output even if it's not directly relevant to the target role. These sections reflect the candidate's identity and differentiators.
- **Replacing the candidate's professional identity with role-side language** — the title and tagline must reflect how the candidate actually describes themselves, as evidenced in the master CV and reinforced by `user_prefs.yaml` → `preferred_title_labels`. Any label listed in `forbidden_title_labels` is an immediate disqualification for the title, even if the job offer (offer flow) or `selected_role.title` (cold flow) uses that exact term.
- **Reordering experiences** — strict reverse chronological order
- **Creating timeline gaps between recent roles** — roles more recent than the compression cutoff must all appear individually. Only pre-cutoff roles may be folded into the consolidated "Earlier experience" line per § Earlier-experience compression, and only if they fail the load-bearing criteria.
- **Dropping a load-bearing pre-cutoff role** — if the role-side evidence points at it (match analysis or the job's required skills in the offer flow; emphasis areas or stack hints in the cold flow), it stays full. Consolidation is for roles the target role genuinely doesn't lean on.

## Final self-check — shared checks

Before emitting the JSON, run the checks listed in the flow prompt's § Final self-check, in the order listed there. It includes these shared checks. If any fails, fix the draft and re-check.

- **Summary traceability** — read each clause of `summary_paragraphs` and the `tagline`. For each clause, silently point to the fact-base location (`summary` / a specific `experience[*].details` entry / `transition_signals` / addendum). If you can't, drop the clause.
- **Learning-language check** — scan for any *"en apprentissage / learning / ramping up"* phrasing. For every occurrence, confirm the technology is named in `cv_fact_base.transition_signals`. If not, remove the claim.
- **Adjective audit** — scan `summary_paragraphs` and `experience[*].bullets` for qualifiers that don't appear in the fact base (e.g. *"cloud-native"*, *"mission-critical"*, *"distributed"*). Strip any that aren't grounded.

## Output format

Return valid JSON matching `schemas/tailored_cv.schema.json` in the job-application-tailor skill (`$SKILL_BASE_TAILOR/schemas/tailored_cv.schema.json` from the cold flow). Read that schema file for the exact structure.

**Example structure** (abbreviated):
```json
{
  "candidate_name": "Jane Doe",
  "title": "Ingénieure Logiciel Senior Java",
  "contact_line": "Email: jane@example.com | Tel: +33 6 00 00 00 00 | LinkedIn: linkedin.com/in/janedoe | GitHub: github.com/janedoe | Paris (75)",
  "tagline": "Applications web • APIs REST • Qualité logicielle",
  "summary_paragraphs": ["Paragraph 1...", "Paragraph 2..."],
  "skills_sections": [
    {"heading": "Langages", "items": ["Java", "Kotlin", "SQL"]},
    {"heading": "Frameworks", "items": ["Spring Boot", "Hibernate"]}
  ],
  "experience": [
    {"role_line": "Senior Developer", "metadata_line": "Acme Corp | Paris | January 2020 – Present", "bullets": ["Developed...", "Migrated..."]}
  ],
  "projects": [
    {"name": "My side project", "metadata_line": "2024 – ongoing | github.com/janedoe/my-project", "bullets": ["What it does", "Stack used"]}
  ],
  "education": ["2015 : University X – MSc Computer Science"],
  "languages": ["Français natif / Anglais courant"]
}
```

## Language

- **(offer flow)** Write all CV content in the same language as the job offer, unless a target language is explicitly specified (or `user_prefs.default_language` overrides it — see the flow prompt's inputs).
- **(cold flow)** Write CV content in `selected_role.language` (chosen in Step 4 from the user's request or `user_prefs.default_language`; `fr` by default).
- JSON field names must remain in English.

## Style

ATS-friendly, clear, professional, concise, realistic — no inflated language.

**(cold flow)** The reader is more likely to be a named hiring manager than an ATS filter, but structural conventions still matter (recruiters forward the CV onward).
