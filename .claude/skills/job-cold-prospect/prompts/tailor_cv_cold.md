You must tailor a candidate CV for a **speculative (cold-call) application**. There is no job offer. The anchor is a researched company profile plus the user-selected target role.

You will receive:
1. the structured CV fact base (with the user's addendum already merged in — extra bullets appear as `experience[*].details` entries, and hidden skills / off-CV facts appear under `addendum_hidden_skills` and `addendum_off_cv_facts` when present)
2. `company_profile.json` from Step 3 — industry, size_band, mission, products_services, values_culture_signals, tech_stack_hints (inferred), hiring_signals, pain_points_inferred (inferred), locations, leadership
3. `selected_role.json` from Step 4 — `title`, `source`, `seniority_band`, `emphasis_areas`, `risk_notes`, `rationale`
4. the **experience compression cutoff year** from layered settings (`config/settings.default.yaml` merged with `<user-data-dir>/settings.yaml`) → `behaviour.experience_compression_cutoff_year` (may be `null` to disable compression)
5. the **user prefs** dict from `resources/user_prefs.yaml`. Honour these keys:
   - `preferred_title_labels`
   - `forbidden_title_labels`
   - `default_language` — for the cold flow, the default is `fr` unless user prefs set a different language

## Goal

Produce a truthful CV tailored to the **selected role angle** at this specific company. Since there is no JD, there are **no ATS keywords to match**. Instead, align emphasis to the role's `emphasis_areas` and the company's stated mission and values — so the CV reads as "this person is credible for this role at this company" rather than "this person has the right keywords."

## Anchoring — what drives emphasis

- **`selected_role.emphasis_areas`** — these are the parts of the CV the user has decided to foreground. Lead with experience, skills, and bullets that map to these areas.
- **`selected_role.seniority_band`** — calibrate the summary, tagline, and top-of-bullet phrasing to this level (e.g. "lead" → team leadership, mentoring, architecture calls).
- **`company_profile.mission_statement` + `values_culture_signals`** — where experience from the fact base resonates with the company's stated values, surface it. Concrete examples only: if the company values "shipping fast" and the CV has concrete delivery-speed evidence, elevate it; if the company values "rigorous engineering" and the CV has testing/CI evidence, elevate that.
- **`company_profile.products_services` + `tech_stack_hints`** — technology overlap is a real signal. When the candidate's fact base intersects with the company's stack or product domain, lead with it. Remember `tech_stack_hints` is **inferred**, so do not over-commit to stack matches that are speculative.
- **`company_profile.size_band`** — same rules as the tailor skill:
  - `startup` (<50) → emphasise versatility, automation, cross-functional work
  - `scaleup` (50–250) → balance depth and breadth, add autonomy/delivery signals
  - `midmarket` (250–2000) → depth and methodology
  - `enterprise` (2000+) → technical depth, methodology, structured collaboration
  - `unknown` → neutral; lean on `selected_role.emphasis_areas`

## Candidate location

Include the candidate's residential location (from `candidate_location` in the CV fact base) in the `contact_line` field alongside email, phone, and LinkedIn. Keep the original format from the CV (e.g. "Brunoy (91)"). Geographic proximity to `company_profile.locations[0]` (when close) is useful context for the motivation letter — not for the CV.

## Allowed changes

- **Adjust** the title / headline / summary to highlight the selected-role angle. The core identity must come from the master CV and `user_prefs.yaml` (`preferred_title_labels` / `forbidden_title_labels`), not from `selected_role.title` alone. You may reuse the selected-role title where it aligns with the candidate's self-description; do **not** paste a user_override title verbatim if it contains a forbidden label.
- Reorder skills to lead with those that map to `emphasis_areas` or intersect with the company's stack hints.
- Tighten wording. Emphasise bullets that resonate with the company's mission and values. De-emphasise detail that doesn't land for this angle.
- Compress older detail per the compression rule below.

## Preserving skill sections

The master CV may contain dedicated skill sections beyond the main technical skills table. Every such section must appear in the tailored CV's `skills_sections` array — you may reorder them for relevance but never drop them entirely.

## Training in Education, not Work Experience

When building the `experience` array, skip any fact-base entry whose `type` field is `"training"`. Those entries appear only in the `education` array. This rule is identical to the tailor skill's — training reads to a recruiter as mislabeled employment when it shows up under Work Experience.

## Earlier-experience compression

Apply the same rule as the tailor skill, with one adaptation for the cold flow:

### Step 1 — Split the roles at the cutoff

Let `CUTOFF` be `experience_compression_cutoff_year`. If `null`, skip this section.

- End date on or after January `CUTOFF` → **recent role**, kept full.
- End date strictly before January `CUTOFF` → **pre-cutoff role**, candidate for consolidation.

### Step 2 — Decide load-bearing

A pre-cutoff role is **load-bearing** if *any* apply. Since there is no match_analysis.json in the cold flow, Criterion A is replaced:

**Criterion A (cold) — Anchor alignment.** Does this role provide concrete evidence for one of `selected_role.emphasis_areas` or for a technology in `company_profile.tech_stack_hints` that a recent role does not already amply cover? If yes, load-bearing.

**Criterion B — Unique technology overlap.** Does the role's stack intersect with `company_profile.tech_stack_hints` (inferred) or the candidate's headline specialisations in a way that's **not** already covered by a post-cutoff role? Example: C++ MFC only in pre-2005 roles + company profile hints at C++ usage → load-bearing.

**Criterion C — Unique responsibility coverage.** Is the role the best or only evidence for a responsibility the selected-role angle calls out (e.g. reverse engineering, Fortran→C++ migration, domain-specific experience)?

If none of A, B, C apply, the role goes into the consolidated line.

### Step 3 — Build the consolidated line

Exactly as in the tailor skill: `role_line` = `"Expériences antérieures"` (fr) or `"Earlier experience"` (en), `metadata_line` = pipe-separated company names only, one summary bullet.

### Step 4 — Edge cases

Same as the tailor skill: all load-bearing → no consolidated line; none pre-cutoff → no-op; mixed → consolidated line after the last retained entry.

## Structural consistency — these formats must never vary between runs

Same as the tailor skill. Contact line, skills-section granularity, experience `role_line` / `metadata_line` split, date format (`Month YYYY – Month YYYY`), education date format, languages line — all inherited unchanged from the master CV.

## Forbidden

- Inventing projects, achievements, tools, certifications, or leadership claims
- **Claiming company facts you cannot cite.** If something isn't in `company_profile.json`, do not assume the company uses it. Stack hints are **inferred** — never reword a CV bullet as if the company confirmed they use that tech.
- Adding keywords not evidenced in the CV
- Dropping dedicated skill sections from the master CV
- Replacing the candidate's professional identity with `selected_role.title` wording when that title conflicts with `preferred_title_labels` / `forbidden_title_labels`
- Reordering experiences
- Creating timeline gaps between recent roles
- Dropping a load-bearing pre-cutoff role

## Output format

Return valid JSON matching `schemas/tailored_cv.schema.json` (reused from the tailor skill). Read that schema file for the exact structure.

**Example structure** (abbreviated, as in the tailor skill):
```json
{
  "candidate_name": "Jane Doe",
  "title": "Ingénieur Logiciel Senior C# / .NET",
  "contact_line": "Email: ... | Tel: ... | LinkedIn: ... | Paris (75)",
  "tagline": "Applications critiques • Architecture de services • Qualité logicielle",
  "summary_paragraphs": ["..."],
  "skills_sections": [{"heading": "Langages", "items": ["C#", "Java"]}],
  "experience": [
    {"role_line": "Senior Developer", "metadata_line": "Acme Corp | Paris | January 2020 – Present", "bullets": ["..."]}
  ],
  "education": ["..."],
  "languages": ["..."]
}
```

## Language

- Write CV content in `default_language` from user prefs (fallback `fr` for the cold flow).
- JSON field names stay in English.

## Style

ATS-friendly, clear, professional, concise, realistic — no inflated language. The cold-flow reader is more likely to be a named hiring manager than an ATS filter, but structural conventions still matter (recruiters forward the CV onward).
