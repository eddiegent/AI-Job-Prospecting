# Pipeline Speedups Roadmap

> **Status: not started.** Drafted 2026-07-28. Two independent changes to the
> `job-application-tailor` run order. Either can ship alone.

Both items came out of the schema-v4 session. Neither is a correctness fix —
the pipeline works today; these remove wasted work from it. The dependency
analysis below was verified against the prompts, not assumed, so a future
session can act on it without re-deriving it. Re-check if the prompts have
moved since.

## Rollout order

Item 1 is low-risk and self-contained. Item 2 removes more wall-clock but
needs a guard built first — do it second.

- [ ] **1. Move company research to after the fit gate**
- [ ] **2. Run interview prep alongside the letter and LinkedIn**

---

## 1. Move company research to after the fit gate

**Where:** `.claude/skills/job-application-tailor/SKILL.md` — Step 3.6 (~line
103) moves to sit between Step 4 (~line 113) and Step 5 (~line 129).

**Current behaviour.** Step 3.6 runs foreground `WebSearch` for company size,
recent news, culture signals, tech stack and key contact names. Step 4 then
scores the match and **stops the run entirely below 50%**. Research that has
already been paid for is discarded.

**Why the move is safe.** Verified by reading the prompts:

- `prompts/match_analysis.md` (Step 4) contains **no** reference to
  `company_research`, "company research" or `company_size`. The scoring does
  not consume it.
- Every real consumer sits *after* the gate: Step 5 (`company_size` steers CV
  emphasis — small firms value versatility, large ones depth), Step 6
  (letter), Step 7 (LinkedIn contacts), Step 8 (interview prep).

So Step 3.6 can slot in after the gate with nothing losing an input.

**Sizing — be honest about this.** Only **7 of 112 scored runs (6%)** fall
below the 50% gate, so the "wasted research on rejected offers" saving is
real but small.

The stronger case is **dry-run mode**, which also stops at Step 4. It exists
explicitly "for quickly scanning multiple job offers to assess fit before
committing to full generation" — and today every dry run still pays the full
WebSearch cost for a result it throws away. That is the mode built for
volume, and the one where this change would actually be felt.

**Watch out for.** Step 3.6 currently back-fills `company_size` into
`job_offer_analysis.json`. That write must still happen before Step 5 reads
it. Moving the step *after* Step 4 but *before* Step 5 preserves this;
moving it any later does not.

---

## 2. Run interview prep alongside the letter and LinkedIn

**Where:** `SKILL.md` — Steps 6/7 (~line 151) and Step 8 (~line 167).

**Current behaviour.** Steps 6 and 7 run as two parallel subagents; the
pipeline waits for both, then Step 8 generates interview prep serially in the
foreground. That is a third LLM generation sitting on the critical path.

**Why it is a candidate.** Per `prompts/generate_interview_prep.md`, Step 8's
inputs are: the tailored CV, the job offer analysis, the CV fact base, the
match analysis, and company research if available. It needs Step 5's output —
but so do Steps 6 and 7. It does **not** read `letter.json` or
`linkedin.json`. Nothing makes it depend on the two steps it currently waits
for, so it can be a third agent in the same batch.

**Why the existing blocker is stale.** SKILL.md says *"Do not use a background
agent for this step"* because subagents hit permission problems. That note
predates the `Write(output/**)` rule now shipping in the **tracked**
`.claude/settings.json` — which is precisely what the Step 6/7 subagents rely
on to write into `_prep/`.

**Why it is still not just "delete the note".** The note gives a second
reason that has *not* gone away: interview prep is markdown-only, with no
schema validation. Steps 6/7 write JSON that gets validated, so a failed
subagent is caught. A silently-failed Step 8 would leave no
`interview_prep.md` and nothing would notice until an incomplete pack
shipped.

**So before parallelising, add a cheap detection guard:** after the batch
completes, assert `$PREP_DIR/interview_prep.md` exists and is non-trivially
sized, and fail loudly if not. Then verify on a real end-to-end run rather
than by reasoning — the failure mode being designed against is precisely one
that produces no error.

---

## Out of scope

- **Parallelising Step 5 (CV tailoring)** — Steps 6/7/8 all consume the
  tailored CV, so it is a genuine barrier, not incidental serialisation.
- **Skipping the fit gate for known-good companies** — changes what gets
  generated, not how fast; a behaviour change, not a speedup.
