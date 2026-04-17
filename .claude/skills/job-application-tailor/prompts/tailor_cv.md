You must tailor a candidate CV to a specific job offer.

You will receive:
1. a structured CV fact base (with the user's addendum already merged in — the extra bullets appear as normal `experience[*].details` entries, and hidden skills / off-CV facts appear under the keys `addendum_hidden_skills` and `addendum_off_cv_facts` when present)
2. a structured analysis of the job offer (including `company_size` field)
3. the match analysis (direct/transferable/gap for each requirement)
4. company research (if available) — use this to confirm company size and understand what the company values
5. the **experience compression cutoff year** from layered settings (`config/settings.default.yaml` merged with `<user-data-dir>/settings.yaml`) → `behaviour.experience_compression_cutoff_year` (may be `null` to disable compression)
6. the **user prefs** dict from `resources/user_prefs.yaml` (may be empty). Honour these keys:
   - `preferred_title_labels` — prefer these labels when writing the CV `title` and tagline. They represent how the candidate actually describes themselves.
   - `forbidden_title_labels` — never apply these labels to the CV `title`, even if the job offer uses that exact wording. Pick a neutral alternative grounded in the fact base.
   - `default_language` — if set to `fr` or `en`, override auto-detection. If `auto` (or unset), follow the job-offer language as usual.

## Goal
Produce a more relevant CV while remaining fully truthful. The tailoring should make the reader think "this person is a natural fit" — not by inventing, but by emphasising the right things.

## Company-size awareness
Adapt the level of detail based on company size. This matters because small companies need generalists while large ones value specialists:

- **Small company / startup (< 50 people)**: expand roles that show versatility — automation, process improvement, tool integration, SaaS orchestration, cross-functional work. A small team needs people who contribute beyond their core technical specialty.
- **Mid-size company (50–500)**: balance depth and breadth. Emphasize the core technical match but also highlight collaboration, integration, and autonomy.
- **Large company / ESN (> 500)**: focus on depth. Emphasize technical expertise, methodology (SOLID, tests, CI/CD), and the ability to work within structured teams and processes.

## Candidate location
Include the candidate's residential location (from `candidate_location` in the CV fact base) in the `contact_line` field alongside email, phone, and LinkedIn. Location is valuable on a CV — it tells the recruiter at a glance whether the candidate is local, nearby, or would need to relocate. Keep the original format from the CV (e.g. "Brunoy (91)", "London, UK").

## Allowed changes
- **Adjust** the title / headline / summary to highlight the most relevant aspects of the candidate's actual profile — but the core identity must come from the master CV and from `user_prefs.yaml` (`preferred_title_labels` / `forbidden_title_labels`), not from the job offer. If the master CV uses a specific self-description and the user's prefs reinforce it, do not replace that with a different specialisation label just because the job offer uses different words. You may reorder or emphasise existing terms, drop less relevant ones, or add a qualifier that is evidenced in the CV — but never inject a specialisation label that the candidate doesn't use to describe themselves, and never use any label listed in `forbidden_title_labels`.
- Reorder skills to lead with the most relevant
- Tighten wording, emphasize relevant responsibilities and technologies
- Compress less relevant older detail to fewer bullets

## Preserving skill sections
The master CV may contain dedicated skill/competency sections beyond the main technical skills table (e.g. "Développement assisté par IA", "Leadership", "Domain expertise"). These sections are part of the candidate's professional identity. Every such section must appear in the tailored CV's `skills_sections` array — you may reorder them for relevance but never drop them entirely. Check the CV fact base `technologies` and the raw CV structure to ensure no dedicated section is lost.

## Training periods belong in Education, not Work Experience
The master CV keeps Formation (training) and Expérience Professionnelle (work experience) as two separate sections. The tailored CV must mirror that. When building the `experience` array, skip any entry in the fact base whose `type` field is `"training"` (e.g. "École Cube — Product Builder No-Code", "Innovaco Formation — Analyse & Programmation"). Those entries appear only in the `education` array.

This matters because a line like *"Product Builder No-Code / Low-Code (Formation temps plein) — École Cube"* under Work Experience reads to a recruiter as a mislabeled employment row even when the "(Formation temps plein)" tag is there. The human reader expects Work Experience to be paid employment. Training stays in Education, where it signals recent upskilling exactly as intended.

Small visible timeline gaps in the experience section are acceptable; mixing training into Work Experience is not. Note: the fact base extraction step (`prompts/extract_cv_data.md`) deliberately adds training periods to the fact base `experience` array for internal timeline analysis — that's a different layer, and this rule only governs the *tailored CV output*.

## Earlier-experience compression

Senior profiles can carry 20+ years of history. Recruiters rarely read past the first page. To respect that attention budget — without ever hiding evidence the job actually relies on — apply this rule before writing the `experience` array:

### Step 1 — Split the roles at the cutoff

Let `CUTOFF` be the value of `experience_compression_cutoff_year` passed in as context. If it is `null`, skip this whole section and keep every role full.

For each role in the CV fact base:
- If the role's **end date** is January `CUTOFF` or later → **recent role**. Always kept full.
- If the role's end date is strictly before January `CUTOFF` → **pre-cutoff role**. Candidate for consolidation, check load-bearing criteria below.

Use the end date, not the start date. A role that straddles the cutoff (e.g. start 2003, end 2008 with cutoff 2005) counts as a recent role.

### Step 2 — Decide which pre-cutoff roles are load-bearing

A pre-cutoff role is **load-bearing** if *any* of these are true. If yes, keep it in the experience list with its normal bullets. If no, set it aside for consolidation.

**Criterion A — Evidence anchoring.** Search `match_analysis.json` for any match of type `direct` or `transferable` whose `evidence` field mentions this role's company name or its date range. If found, the role is load-bearing — the match analysis is pointing directly at it.

**Criterion B — Unique technology overlap.** Does the role's technology stack intersect with the job's `required_skills` or `preferred_skills` for a technology that is **not** already amply covered by a recent (post-cutoff) role?
- Example: C++ MFC is only in pre-2005 roles → if the job asks for C++, those roles are load-bearing.
- Counter-example: C# appears briefly in a pre-2005 role, but the candidate has 15 years of C# in a post-cutoff role → the pre-cutoff exposure is redundant, not load-bearing on its own.

**Criterion C — Unique responsibility coverage.** Is the role the best or only evidence for a key responsibility the job explicitly calls out (e.g. reverse engineering, a specific legacy-language migration, a domain-specific pattern, experience writing technical specifications for clients)?
- Example: "Fortran → C++ conversions at JFC" is the best evidence for a Fortran migration responsibility → load-bearing.
- If the same responsibility is better evidenced by a post-cutoff role, the pre-cutoff role fails this criterion.

If none of A, B, C apply, the role goes into the consolidated line.

### Step 3 — Build the consolidated line (if any role was set aside)

If any pre-cutoff roles were set aside in Step 2, append **one single entry** to the end of the `experience` array, after the last recent or load-bearing role. The entry must:

- Put a language-appropriate heading in `role_line`:
  - French: `"Expériences antérieures"`
  - English: `"Earlier experience"`
  - Other target languages: translate the heading appropriately. The rest of the CV already tells you which language to write in.
- Put the **pipe-separated company names only** in `metadata_line`, with **no dates** (e.g. `"Peaktime SAS | JFC Informatique & Média"`). Dateless on purpose: presents earlier experience as context without inviting age-based filtering.
- Contain **one single bullet** in `bullets` that summarises the aggregate scope of the consolidated roles: the core tech (C++ STL / MFC, etc.), the general domain (e.g. media, advertising data), and the high-level contribution (development, project coordination, writing specifications). Keep it under 2 lines in the rendered output. Write it in the same language as the rest of the CV.

Companies in the consolidated line appear in reverse-chronological order to match the rest of the experience section.

### Step 4 — Edge cases

- **All pre-cutoff roles are load-bearing.** Do nothing special — no consolidated line is produced. This is what happens when the job leans heavily on older experience (e.g. a C++ migration role for a candidate whose C++ decade was pre-cutoff).
- **No pre-cutoff roles exist at all.** Do nothing. The rule is a no-op.
- **Mixed: some load-bearing, some not.** Keep the load-bearing ones as normal entries in their chronological position, and add the consolidated line after the last recent/load-bearing entry. The result is a mostly-compact experience section with a couple of older entries surfaced where they matter.

### Why this exists

Senior candidates lose recruiter attention before they reach their best match when early-career roles take up half the experience section. Compression moves the reader's eye to what actually matters for this job. Load-bearing roles still surface in full because hiding them would defeat the point of tailoring. Dateless consolidation acknowledges prior depth without anchoring the reader to an exact starting year — a small but real mitigation against age-based filtering.

The rule is load-bearing-aware, not hard-capped: it trusts the match analysis to tell the truth about which older roles this specific job needs. That means the quality of the match analysis directly drives the quality of the compression.

## Structural consistency — these formats must never vary between runs

The following formatting rules are derived from the master CV and must be applied identically regardless of the target job:

### Contact line
Use the labeled format from the master CV:
`Email: <email> | Tel: <phone> | LinkedIn: <linkedin> | <location>`

### Skills sections
Preserve the master CV's granular skill categories as separate `skills_sections` entries. Each category from the skills table becomes its own section with its own heading (e.g. "Langages", "Plateformes & Frameworks", "Services & Communication", "Données", "Tests", "Outils & Environnements", "Architecture & Méthodes", "Systèmes"). Do not consolidate multiple categories into a single section. Dedicated sections outside the table (e.g. "Développement assisté par IA") are also preserved as separate entries. You may reorder sections for relevance but never merge or drop them.

### Experience line format
Each experience entry has two separate fields:
- `role_line` — the role/job title **only** (e.g. `"IT Project Manager"`, `"R&D Engineer"`, `"Development Manager"`). No company, no dates. Rendered bold on its own line.
- `metadata_line` — a single pipe-separated string `"Company | Location | Month YYYY – Month YYYY"` (e.g. `"Oodrive SA | Paris | July 2010 – March 2025"`). Rendered italic-gray on its own line directly under the role.

This matches how ATS parsers expect to find role, employer, and dates — each on its own clear line rather than merged.

### Date format
Use `Month YYYY – Month YYYY` consistently across the `experience` array (e.g. `"July 2010 – March 2025"`). Use the full month name in the target language (`"July"` in English, `"juillet"` in French). Use an en-dash ` – ` (not a hyphen `-`). Never abbreviate months. Never mix formats inside the CV.

For the consolidated `Earlier experience` entry (if any), the `metadata_line` is intentionally dateless: put only the pipe-separated company names there (e.g. `"Peaktime SAS | JFC Informatique & Média"`). The `role_line` stays `"Earlier experience"` (or the target-language equivalent from § Earlier-experience compression).

### Education dates
Reproduce date formatting as it appears in the master CV. Do not reformat dates (e.g. don't expand 2-digit years to 4-digit, don't change separators).

### Languages
Reproduce the languages section as it appears in the master CV. If the CV uses a single consolidated line (e.g. "Bilingue Français / Anglais"), keep it as one entry. Do not split into separate entries.

## Forbidden
- Inventing projects, achievements, tools, certifications, or leadership claims
- Adding keywords not evidenced in the CV
- **Dropping dedicated skill sections** from the master CV — if the original CV has a section like "Développement assisté par IA" or "Automation & Low-Code", it must appear in the tailored output even if it's not directly relevant to the job offer. These sections reflect the candidate's identity and differentiators.
- **Replacing the candidate's professional identity with job offer language** — the title and tagline must reflect how the candidate actually describes themselves, as evidenced in the master CV and reinforced by `user_prefs.yaml` → `preferred_title_labels`. Any label listed in `forbidden_title_labels` is an immediate disqualification for the title, even if the job offer uses that exact term.
- **Reordering experiences** — strict reverse chronological order
- **Creating timeline gaps between recent roles** — roles more recent than the compression cutoff must all appear individually. Only pre-cutoff roles may be folded into the consolidated "Earlier experience" line per § Earlier-experience compression, and only if they fail the load-bearing criteria.
- **Dropping a load-bearing pre-cutoff role** — if the match analysis or the job's required skills point at it, it stays full. Consolidation is for roles the target job genuinely doesn't lean on.

## Output format
Return valid JSON matching `schemas/tailored_cv.schema.json`. Read that schema file for the exact structure.

**Example structure** (abbreviated):
```json
{
  "candidate_name": "Jane Doe",
  "title": "Ingénieur Logiciel Senior C# / .NET",
  "contact_line": "Email: jane@example.com | Tel: +33 6 00 00 00 00 | LinkedIn: linkedin.com/in/janedoe | Paris (75)",
  "tagline": "Applications critiques • Architecture de services • Qualité logicielle",
  "summary_paragraphs": ["Paragraph 1...", "Paragraph 2..."],
  "skills_sections": [
    {"heading": "Langages", "items": ["C#", "Java", "SQL"]},
    {"heading": "Plateformes & Frameworks", "items": [".NET", ".NET Core", "WPF"]}
  ],
  "experience": [
    {"role_line": "Senior Developer", "metadata_line": "Acme Corp | Paris | January 2020 – Present", "bullets": ["Developed...", "Migrated..."]}
  ],
  "education": ["2015 : University X – MSc Computer Science"],
  "languages": ["Bilingue Français / Anglais"]
}
```

## Language
- Write all CV content in the same language as the job offer, unless a target language is explicitly specified
- JSON field names must remain in English

## Style
ATS-friendly, clear, professional, concise, realistic — no inflated language.
