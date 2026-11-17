# Humanizer pass — shared by every prose-drafting prompt

The letters, the short letter and the LinkedIn messages (offer and cold flows) all go through this pass after drafting and **before** their final gate. It removes AI tells: not-X-but-Y contrasts, one-line closers, forced triads, dashes everywhere, inflated claims and stock words. A recruiter who spots them stops reading.

## How

`<stage>` is `letters` (covers `letter.json` and `short_letter.json` together, so draft both first) or `linkedin`.

1. Draft the JSON as the calling prompt says.
2. **Gate the draft and take the snapshot:**
   ```bash
   cd "$SKILL_BASE" && python scripts/cli.py gate <stage> "$OUTPUT_DIR" --draft
   ```
   Same checks as the plain gate, short-letter length included. Fix the draft until it passes; a passing run ends with `draft snapshot saved (…)` and has copied the draft to `_prep/pre_humanize/`. Step 4 compares against it.
3. **Load the `humanizer:humanizer` skill with the Skill tool** (`skill: "humanizer:humanizer"`), then apply it to the prose fields only:
   - letters: each entry of `paragraphs` (the greeting, signoff and metadata stay as they are);
   - LinkedIn: each variant's `message`.
   Load it every time; don't work from what you remember of its rules, which change between versions. It loads as instructions, not as a tool that returns text: apply them yourself to those fields, in the draft's language, with `user_prefs.tone_directives` as the voice to match (its "embedded mode": only the final text, no commentary). Write that text back into the same fields. Subject lines, subject hints, greetings and signoffs are out of scope.
   The rewrite usually shortens the text. A short letter drafted near 500 characters can drop under the limit: prefer a draft with some margin, and see step 5 if the gate then asks for more.
4. **Run the gate again, without `--draft`.** Its `humanizer guard` check compares each file with the snapshot:
   - `[FAIL]` — a field outside the prose changed, or the text gained a number or a name the draft did not have. Put the draft's value back, or reword.
   - `[WARN]` — a sentence shares few words with the draft, or a number from the draft is gone. Resolve every warning: cut the sentence, or point to the line of `cv_fact_base_merged.json` it restates. A warning is not permission.
5. If a later fix needs a fact the draft lacked (for example to bring the short letter back over 500 characters), take it from `cv_fact_base_merged.json`, then re-run step 2 on the corrected text to take a new snapshot. Don't re-run step 2 to silence a failure you haven't traced.

If the `humanizer:humanizer` skill isn't installed, skip steps 2–3, say so in your report, and run the plain gate. The pass is a polish step, not a requirement; the gate then notes "no draft snapshot".

## What the rewrite must keep

The humanizer edits style. The rules of the calling prompt still win on content:

- **Every fact, number, name, employer and tech stays exactly as drafted**, and nothing new comes in. A "specific detail" the humanizer would add must come from `cv_fact_base_merged.json` or the company research, never from guesswork — and a detail the draft didn't have goes through step 5.
- Team scope stays team scope: no solo-work phrasing for `team_context_companies`.
- Gaps stay stated as gaps; a negation stays in the same clause as the skill it negates (the claims check reads it that way).
- Length limits still hold: short-letter body 500–750 characters, LinkedIn connection request ≤ 300, direct message ≤ 700.
- Cold flow: the opening hook must still match across the letter, short letter and LinkedIn. Rephrase it the same way everywhere or leave it.
- Same language as the draft. In French, treat the equivalent constructions the same way ("ce n'est pas X, c'est Y", "non seulement… mais aussi").
- `tone_directives` override the humanizer's defaults on conflict.
