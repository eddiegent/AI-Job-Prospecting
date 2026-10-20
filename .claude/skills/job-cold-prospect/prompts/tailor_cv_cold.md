You must tailor a candidate CV for a **speculative (cold-call) application**. There is no job offer. The anchor is a researched company profile plus the user-selected target role.

**First, read `$SKILL_BASE_TAILOR/prompts/cv_rules.md` (the job-application-tailor skill's shared CV rules). ALL of its rules apply to this prompt** — fact-base input, candidate location, summary sourcing, learning language, skill sections, training, personal projects, earlier-experience compression and wording, structural consistency, evidence ledger, forbidden list, shared self-checks, output format, language and style. Follow its **(cold flow)** notes. This file adds only the cold-flow inputs and rules.

You will receive:
1. the **merged CV fact base** `$PREP_DIR/cv_fact_base_merged.json` (produced by `scripts/claims_guard.py merge` — the cached fact base with the user's addendum already merged in: extra bullets appear as `experience[*].details` entries, hidden skills / off-CV facts appear under `addendum_hidden_skills` and `addendum_off_cv_facts` when present, plus `addendum_skill_calibration` and `familiar_only_skills`)
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
- **`company_profile.size_band`** — small companies need generalists, large ones value specialists:
  - `startup` (<50) → emphasise versatility, automation, cross-functional work
  - `scaleup` (50–250) → balance depth and breadth, add autonomy/delivery signals
  - `midmarket` (250–2000) → depth and methodology
  - `enterprise` (2000+) → technical depth, methodology, structured collaboration
  - `unknown` → neutral; lean on `selected_role.emphasis_areas`

## Allowed changes

- **Adjust** the title / headline / summary to highlight the selected-role angle. The core identity must come from the master CV and `user_prefs.yaml` (`preferred_title_labels` / `forbidden_title_labels`), not from `selected_role.title` alone. You may reuse the selected-role title where it aligns with the candidate's self-description; do **not** paste a user_override title verbatim if it contains a forbidden label.
- Reorder skills to lead with those that map to `emphasis_areas` or intersect with the company's stack hints.
- Tighten wording. Emphasise bullets that resonate with the company's mission and values. De-emphasise detail that doesn't land for this angle.
- Compress older detail per `cv_rules.md` § Earlier-experience compression (using its **(cold flow)** Criterion A).

## Honesty on technology claims

There is no job offer and no match analysis in the cold flow, so the CV is judged purely against the candidate's fact base. Two traps to avoid:

- **Inferred stack mirroring.** `company_profile.tech_stack_hints` is a best-guess about what the company uses — it does **not** confer competence on the candidate. Do not reword a CV bullet to echo a company stack hint the candidate hasn't actually worked with.
- **Active-learning / in-progress phrasing.** No *"en apprentissage"* / *"learning X"* / *"ramping up on X"* unless that specific technology appears by name in `cv_fact_base.transition_signals` — see `cv_rules.md` § Active-learning / in-progress phrasing. Transition signals come from the candidate; they are not inferred from the selected role or the company profile.

## Forbidden — cold-flow additions

Everything in `cv_rules.md` § Forbidden, plus:
- **Claiming company facts you cannot cite.** If something isn't in `company_profile.json`, do not assume the company uses it. Stack hints are **inferred** — never reword a CV bullet as if the company confirmed they use that tech.
- **Replacing the candidate's professional identity with `selected_role.title` wording** when that title conflicts with `preferred_title_labels` / `forbidden_title_labels`.

## Final self-check before returning

Before emitting the JSON, run these checks in order. If any fails, fix the draft and re-check.

1. **Summary traceability** — as defined in `cv_rules.md` § Final self-check.
2. **Stack-hint check** — scan `experience[*].bullets` for any wording that mirrors `company_profile.tech_stack_hints` but doesn't come from the fact base. Revert to the fact base's original wording. Stack hints are about the company, not the candidate.
3. **Learning-language check** — as defined in `cv_rules.md` § Final self-check.
4. **Adjective audit** — as defined in `cv_rules.md` § Final self-check.
5. **Selected-role contagion check** — `selected_role.emphasis_areas` and `selected_role.rationale` are *intent signals*, not fact-base entries. Do not promote a tech named there into `summary_paragraphs`, `tagline`, `skills_sections`, or `experience[*].bullets` unless that tech also appears in `cv_fact_base.{technologies,skills,methodologies}` or in `experience[*].details`. The Step-4 grounding check should have already scrubbed `selected_role`, but this is the last line of defence before the CV ships.

Then write `$PREP_DIR/tailored_cv.json` and run the CV gate (`cd "$SKILL_BASE_TAILOR" && python scripts/cli.py gate cv "$PREP_DIR"` — see `cv_rules.md` § Evidence ledger and SKILL.md).
