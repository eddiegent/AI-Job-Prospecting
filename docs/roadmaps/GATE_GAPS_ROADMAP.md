# Gate Gaps Roadmap

> **Status: shipped — historical document.** Fixes 1–4 committed 2026-11-02 (`fa5383d`). Fix 5 (a missing
> technology needs its own gap row) became blocking on 2026-11-17, when match rows were fixed to the offer's
> items (`docs/roadmaps/SKILL_REVIEW_2026-11.md` item 3). The language decision below is still open; since
> 2026-11-17 `gate offer` warns on it at Step 3. Later work is tracked in the repo-root `CHANGELOG.md`.
>
> Written 2026-10-21 from a comparison run: the five
> latest offer packs (#144–#148) were regenerated with the v1.1.0 pipeline plus
> both speedups, then compared with the originals. The plan is to fix the gaps
> below, regenerate the same five packs again, and re-run the comparison.

## The comparison set

Originals and regenerated packs, all in `output/`. The regenerated ones are
**not** recorded in the DB; keep them until the rerun is done.

| App | Original folder | Regenerated (2026-10-21) |
|---|---|---|
| #148 Opus | `good-19102026-AI-Product-Builder-Junior-Opus-Recruitment-Solutions` | `good-21102026-…-Opus-Recruitment-Solutions` |
| #147 CANAL+ | `medium-13102026-AI-Builder-(CDI)-CANAL+-Group-(CANAL+-TECH)` | `good-21102026-AI-Builder-(CDI)-CANAL+-…` |
| #146 Brevo | `medium-11102026-AI-Native-Product-Engineer-Brevo` | `medium-21102026-AI-Native-Product-Engineer-Brevo` |
| #145 OTOQI | `medium-09102026-Low-Code-Product-Builder-H-F-OTOQI` | `medium-21102026-Low-Code-Product-Builder-H-F-OTOQI` |
| #144 APB | `medium-09102026-AI-Product-Builder-…-Groupe-APB` | `good-21102026-AI-Product-Builder-…-Groupe-APB` |

`tools/compare_packs.py` prints a field-by-field diff of each pair (fit,
gaps, CV structure, letters, LinkedIn, interview prep, research). Update its
`PAIRS` list when the rerun produces new folders.

**How the rerun was done** (repeat it the same way): preflight → feed the
original `_prep/raw_offer.md` to `cache-raw-offer` (same input, no refetch) →
Steps 3–5 in the main context → Steps 6/7/8 as three parallel subagents →
re-run the three gates → `regenerate-outputs`. Skip Step 10 (no DB record).
The duplicate check flags each one; that is expected.

## Fixes

- [x] **1. Gate that every recent role appears in full.** Nothing checks that
  a role ending on or after `experience_compression_cutoff_year` is a full
  experience entry. The original APB CV folded JFC Kantar (2002–2005) into
  « Expériences antérieures » and passed every gate. `scripts/tailor_invariants.py`
  has related validators (`find_missing_load_bearing_roles`,
  `find_non_consolidated_non_load_bearing_roles`, training-in-experience) but
  they are only used by tests and none checks this direction. Add the check and
  wire the invariants into `gate cv` (`scripts/commands/gate.py`). Check the
  cold flow's CV gate too.
  **Done:** `find_missing_recent_roles` + a `cv timeline` check in `gate cv`
  (both flows). Roles are matched on company core name (no parenthetical, no
  legal form) **and** end year, so nested names (Peaktime SAS / Telmar
  Peaktime SAS, the two JFC roles) are told apart. Blocking: recent role
  missing, training in experience, consolidated line dated / wrong-language
  heading. Warnings only: the criterion-A load-bearing checks — they fire on
  passing mentions ("fluent English: 5 years at ROCC"), 38 of 133 historical
  packs. Sweep: 3 of 133 packs fail, all real (APB original, matchpoint, DP-IA
  Justice — each folded JFC Kantar).
- [x] **2. Short-letter length in `gate letters`.** The body must be 500–750
  characters (prompt + SKILL.md) but nothing checks it. The Opus (486) and
  OTOQI (496) originals shipped under the minimum; two subagents caught short
  drafts only by themselves.
  **Done:** `short letter length` check (paragraphs summed). Of 123 packs only
  the two above fail.
- [x] **3. Match grounding is too strict on alternatives.** "Make, Zapier, n8n
  ou équivalents" and "Cursor, Claude Code, Codex ou équivalents" are rejected
  as `direct` although Make / Claude Code are grounded: the compound
  all-or-nothing rule ignores "ou / or / équivalents". "Bac+3 à Bac+5" is also
  treated as a tech token. In `scripts/check_match_grounding.py`, treat an
  alternatives list as satisfied by any grounded member (the familiar-only cap
  still applies to the member that is used). APB's regenerated 70% is slightly
  understated because of this.
  **Done:** an alternatives clause (split on et/and/;) is met by one grounded,
  non-familiar member; with an explicit "ou équivalents / alternatives" marker
  and no grounded member it warns instead of blocking (OTOQI's "Supabase ou
  alternatives"). `Bac+N` is no longer tech-shaped. Requirements now split on
  "ou"/"or", which surfaced one new literal miss in the history (Alcimed
  "assistants ou agents de développement" marked direct) — kept as an error.
- [x] **4. Claims check blocks naming a familiar-only skill as a gap.** "n8n
  reste à apprendre" fails the claims check, so a letter cannot state that gap
  honestly. Allow a familiar-only skill in an explicit not-yet / gap phrasing
  (see `_negation.py`, which already handles negated addendum lines) while
  still blocking it as a claimed skill.
  **Done:** rule 2 reads only affirmative clauses (`affirmative_clauses`, as
  rule 6 does). `_negation.py` no longer treats restrictive/additive forms as
  negations ("je n'utilise que Docker", "non seulement", "not only"), so those
  still block. The three letter/LinkedIn prompts say a gap is fine if the
  negation sits in the skill's clause.

## Rerun after the fixes (run 2, 2026-10-21)

Run-1 folders were renamed `run1_*` so run 2 could reuse the date; `tools/compare_packs.py --gates`
prints ORIG / RUN1 / RUN2 side by side and runs today's gates on all 15 packs. Run 2 reused run 1's
`company_research.md` (no new web searches), so differences come from generation and gates only.
`prompts/match_analysis.md` gained an "Alternatives are not compounds" rule before the run — without
it the model kept downgrading "X, Y ou équivalents" whatever the gate allowed.

- **Gates now:** the three originals fail exactly where predicted (APB `cv timeline`, Opus and OTOQI
  `short letter length`); all 10 regenerated packs pass every gate.
- **Fix 1:** APB keeps JFC Kantar full. CANAL+ keeps JFC Asnières full (match evidence names it).
  The run surfaced one more false warning (Telmar Peaktime read as Peaktime, a Kantar year read as
  Peaktime's); fixed: longer names are blanked and the year must sit right after the mention.
- **Fix 2:** short letters 503–592; one subagent wrote 503, just over the floor.
- **Fix 3:** Opus "N8N, Make ou Zapier", APB "Make, Zapier, n8n ou équivalents" and "Cursor, Claude
  Code, Codex ou équivalents" are now `direct`; OTOQI "Supabase ou alternatives" is `direct` on
  PostgreSQL with the non-blocking warning.
- **Fix 4:** letters name gaps openly and pass: "n8n reste à apprendre" (OTOQI, APB), "TypeScript,
  Kubernetes et les frameworks agentiques restent à apprendre" (Brevo — after one jd-contagion fail
  that moved the tech into the negated clause), "Les agents Gemini ou GPT restent à apprendre" (CANAL+).
- **Fit (ORIG → RUN1 → RUN2, corrected):** Opus 71→71→66, CANAL+ 63→76→63, Brevo 62→66→66,
  OTOQI 59→66→56, APB 62→70→75. The first RUN2 figures (76/77/75/83) were inflated: missing offer
  technologies (OTOQI Edge Functions / Node.js / JWT / webhooks / Figma / JavaScript, APB JavaScript /
  PHP, Opus ChatGPT / Gemini / JavaScript, CANAL+ Gemini Agents / GPT Agents / SAP / Braze / CRM) sat
  inside broader `transferable` rows instead of their own `gap` rows. Corrected by adding the gap rows
  (folders re-ranked: CANAL+, Opus, OTOQI → medium) and regenerating those four interview preps.
  RUN1's 76 % for CANAL+ had the same flaw. Only APB rises for a real reason: its two "ou équivalents"
  rows (fix 3) and JFC Kantar kept in full.
- **Fix 5 (added from this run):** `check_match_grounding.py` now warns when an offer technology the
  candidate lacks has no `gap` row of its own (familiar-only skills and satisfied alternatives
  excepted); `prompts/match_analysis.md` requires the separate gap row. On the history it fires on
  120 of 135 packs — the folding habit is systematic, so past fit scores are mostly inflated by it.
  Warning only for now; consider blocking once new runs come out clean.
- **Smaller:** APB LinkedIn `contact_name` is now "[Prénom]" (was null). Interview prep stays
  15.8–18.2k chars (originals 6.9–10.4k) — still the open decision below.

## Open decisions (the user's)

- **Interview prep length — decided 2026-10-21: keep it for now.** Subagent-written preps run
  15.8–19.7k chars vs 6.9–10.4k for the originals. Same 12 sections and 8 questions; each item is
  just denser (3-bullet answers instead of one-line hints, full evidence citations in table cells),
  because the prompt sets no length and a fresh subagent uses the room. If it needs trimming later:
  a length budget in `prompts/generate_interview_prep.md` (≤ 2 bullets per answer, one-line
  evidence cells, ~8–10k target) plus a `gate interview` warning above ~12k.
- **Language rule.** `prompts/analyze_job_offer.md` flips `detected_language` to
  `fr` on French-market perks. Brevo's posting is for an English-speaking
  international team ("French not required") and still got a French pack.
  Decide whether an explicit "French not required" / English-team signal
  should override the flip.

## Smaller observations from the run

- Fit-score changes between original and rerun (+4 to +13 in 4 of 5) come
  mostly from how requirements are split into rows, not from the pipeline
  change. Compare row by row, not just the percentage.
- APB's regenerated `linkedin.json` has `contact_name: null` where the other
  packs use "[Prénom]" — harmless, but inconsistent.
- The Opus recruiter message says "disponible", inferred from the Ezel role
  ending, not stated in the fact base.
