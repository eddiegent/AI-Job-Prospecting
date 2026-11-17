# Skill Review — November 2026

> **Status: items 1–7 and 9 shipped 2026-11-17 on branch `gate-gaps-and-bootcamp-rule`; 8 and 10–14 open.**
> Written 2026-11-17 from a review of the five job skills, after the humanizer pass was added and three
> packs were rerun with it. Each item records what was found, what shipped and what is left. Details of
> each change are in `.claude/skills/job-application-tailor/CHANGELOG.md`.

## Shipped

- [x] **1. Figures checked against the CV.** A copy of pack #159 saying "45 000+ sauvegardes" (CV: 17 000+)
  plus an invented "équipe de 12 personnes" passed `gate cv` and `gate letters`. Claims rule 8 now blocks
  any number the master CV or addendum doesn't state. No failure on the 39 packs since October.
  (`2737008`)
- [x] **2. Humanizer pass fenced.** The first reruns with the pass invented a sentence and edited subject
  lines while every gate passed. `gate letters|linkedin --draft` snapshots the draft; the gate after the
  pass blocks an added number or name or a changed field outside the prose. (`2737008`)
- [x] **3. Fit score reproducible.** Match rows are fixed to the offer's items (`match-rows`); a missing
  technology must be `gap`. Two independent runs on pack #166: same 35 rows, 64% / 67%. (`10d4fe0`)
  - **Weighting — decided: no.** Simulated on 144 packs, every scheme mostly inflated scores and moved
    5–8 packs across the 50% cut-off, with 3 interviews of outcome data. The required skills rated `gap`
    are shown next to the score instead (`required_gaps`, interview-prep banner). (`d165198`)
- [x] **4. Rerun a pack in place.** `preflight --reuse-dir`, `record-application --update <id>`,
  SKILL.md § Rerunning a whole pack in place. (`f84a319`)
- [x] **5. Stale folder paths in the DB.** Fallback to `output/<folder name>`; `repair-output-folders`.
  Applied 2026-11-17: 156 of 157 rows resolve (#73 Vectalis has no pack anywhere). (`f84a319`)
- [x] **6. Cold flow checks.** `gate dossier` (completeness + hook-alignment warning); evidence rules in
  the cold prompts. (`5948122`)
- [x] **7. Offer analysis checked against the cached offer.** `gate offer` blocks a technology the offer
  never names (14 of 102 packs since June had one) and warns on an English offer analysed as French.
  (`ef819a5`)
- [x] **9. Evidence rules in one file.** `prompts/evidence_discipline.md`. (`5948122`)

## Open

- [ ] **8. What to do with a match-gate warning.** Agents handle the soft-skill "direct" warning
  inconsistently (one downgrades, another keeps the row). Step 4 should say when a warning means
  "downgrade" and when "keep, the evidence is explicit".
- [ ] **10. Near-duplicate company names.** Collective.work / Collective Works, three Safran entities, two
  Euro-Information spellings: `check-duplicate` should warn on a similar company name.
- [ ] **11. Reuse company research.** A second pack for the same company repeats every web search.
- [ ] **12. Correct a status-history date.** 99% of `application_events` are backfilled dates and no
  command amends one (`amend-event` was proposed, never built).
- [ ] **13. Small bugs.** `doctor` reports the latest backup by name (a July snapshot) instead of by date;
  interview prep stamps "Applied on" with the generation date; leftover files (Word `.tmp`) survive a
  rebuild; the two test suites can't share one pytest process.
- [ ] **14. Merge and release.** The branch carries the 2026-11-02 gate-gap fixes and everything above;
  merge to `main`, bump the version (README, `docs/index.html`, plugin manifest) and tag.

## Open decisions (the user's)

- **Language of an English offer that says French is not required** (Brevo). The analysis flips to
  French on French-market signals; `gate offer` now warns, but the pack still comes out in French.
