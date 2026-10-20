You must tailor a candidate CV to a specific job offer.

**First, read `prompts/cv_rules.md` (in this skill: `$SKILL_BASE/prompts/cv_rules.md`). ALL of its rules apply to this prompt** — fact-base input, candidate location, summary sourcing, learning language, skill sections, training, personal projects, earlier-experience compression and wording, structural consistency, evidence ledger, forbidden list, shared self-checks, output format, language and style. Follow its **(offer flow)** notes. This file adds only the offer-flow inputs and rules.

You will receive:
1. the **merged CV fact base** `$PREP_DIR/cv_fact_base_merged.json` (produced by `scripts/claims_guard.py merge` — the cached fact base with the user's addendum already merged in: the extra bullets appear as normal `experience[*].details` entries, hidden skills / off-CV facts appear under the keys `addendum_hidden_skills` and `addendum_off_cv_facts` when present, plus `addendum_skill_calibration` and `familiar_only_skills`)
2. a structured analysis of the job offer (including `company_size` field)
3. the match analysis (direct/transferable/gap for each requirement)
4. company research (if available) — use this to confirm company size and understand what the company values
5. the **experience compression cutoff year** from layered settings (`config/settings.default.yaml` merged with `<user-data-dir>/settings.yaml`) → `behaviour.experience_compression_cutoff_year` (may be `null` to disable compression)
6. the **user prefs** dict from `user_prefs.yaml` in the user data dir (may be empty). Honour these keys:
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

## Allowed changes
- **Adjust** the title / headline / summary to highlight the most relevant aspects of the candidate's actual profile — but the core identity must come from the master CV and from `user_prefs.yaml` (`preferred_title_labels` / `forbidden_title_labels`), not from the job offer. If the master CV uses a specific self-description and the user's prefs reinforce it, do not replace that with a different specialisation label just because the job offer uses different words. You may reorder or emphasise existing terms, drop less relevant ones, or add a qualifier that is evidenced in the CV — but never inject a specialisation label that the candidate doesn't use to describe themselves, and never use any label listed in `forbidden_title_labels`.
- Reorder skills to lead with the most relevant
- Tighten wording, emphasize relevant responsibilities and technologies
- Compress less relevant older detail to fewer bullets (per `cv_rules.md` § Earlier-experience compression)

## Gap honesty — how to handle `match_analysis` gaps and qualified matches

The match analysis is the source of truth for what the candidate actually has vs. what the job wants. Respect it when writing the CV.

**When a requirement is `gap`:**
- The CV must not state or imply current competence, production use, recent exposure, or active learning in that area.
- Do not introduce tense/phase language for the gap technology (*"en apprentissage"*, *"learning X"*, …) unless that specific technology appears by name in `cv_fact_base.transition_signals` — see `cv_rules.md` § Active-learning / in-progress phrasing. Transition signals come from the candidate; they are not inferred from the job offer's requirement list.
- The safe move for a gap is silence. The motivation letter is the place to address gaps honestly; the CV is not.

**When a requirement is `direct` or `transferable` but its `notes` field narrows the scope:**
- Any CV claim on that topic must stay inside the narrowing. If `notes` says *"used for CI/CD builds, not for production orchestration"*, the CV cannot say *"used in production"*. If `notes` says *"conceptual knowledge only"*, the CV cannot imply hands-on use.
- Prefer the wording already in `match_analysis.notes` or `evidence` over reinvented phrasing. Those fields were written with the caveats intact.

**When the match analysis classifies a fact under one label but the job offer uses a different label:**
- Keep the fact's original framing from the fact base. Don't relabel an experience to match the job's vocabulary (e.g. *"migration d'une base de données vers PostgreSQL"* must not become *"intégration de systèmes tiers"* just because the job uses that exact phrase). Keyword coverage belongs in the skills section, not in reworded experience bullets.

## Forbidden — offer-flow additions
Everything in `cv_rules.md` § Forbidden, plus:
- **Contradicting `match_analysis.notes` qualifiers** — if a match's `notes` field narrows the scope of an experience ("not for production orchestration", "conceptual knowledge only", "not labelled as such internally"), the CV must stay inside that narrowing.

## Final self-check before returning

Before emitting the JSON, run these checks in order. If any fails, fix the draft and re-check.

1. **Gap check** — for every row in `match_analysis.matches` with `match_type: "gap"`, read the `requirement`. Confirm that requirement does **not** appear in `summary_paragraphs`, `tagline`, or any `experience[*].bullets` entry framed as a current, recent, or in-progress capability. If it appears only inside a neutral factual bullet already in the fact base, that's fine; if it appears as a bridging claim ("en apprentissage sur X", "familiarité avec X", "exposition à X"), remove it unless `cv_fact_base.transition_signals` supports it by name.
2. **Qualifier check** — for every row with `match_type: "direct"` or `"transferable"` whose `notes` field narrows scope, confirm that no CV claim on that topic exceeds the narrowing. Prefer the `notes` or `evidence` wording when in doubt.
3. **Summary traceability** — as defined in `cv_rules.md` § Final self-check.
4. **Learning-language check** — as defined in `cv_rules.md` § Final self-check.
5. **Adjective audit** — as defined in `cv_rules.md` § Final self-check.
6. **JD-stack contagion check** — `job_offer_analysis.{required_skills, technologies, ats_keywords}` describes what the company wants. Do not promote a tech named there into `summary_paragraphs`, `tagline`, `skills_sections`, or `experience[*].bullets` unless that exact tech (or a close synonym) also appears in `cv_fact_base.{technologies, skills, methodologies}` or in `experience[*].details`. The Step-4 grounding check should have already scrubbed `match_analysis`, but this is the last line of defence before the CV ships. Concrete failure to avoid: the JD lists Kubernetes; the candidate has Docker but not K8s; the CV's `skills_sections.Outils` must not list "Kubernetes" just because the JD wanted it.

Then write `tailored_cv.json` and run the CV gate (`python scripts/cli.py gate cv "$PREP_DIR"` — see `cv_rules.md` § Evidence ledger and SKILL.md).
