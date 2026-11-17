# Humanizer pass — shared by every prose-drafting prompt

The letters, the short letter and the LinkedIn messages (offer and cold flows) all go through this pass after drafting and **before** their gate. It removes AI tells: not-X-but-Y contrasts, one-line closers, forced triads, dashes everywhere, inflated claims and stock words. A recruiter who spots them stops reading.

## How

1. Draft the JSON as the calling prompt says.
2. Invoke the **`humanizer:humanizer`** skill (Skill tool) in **embedded mode** on the prose fields only:
   - letters: each entry of `paragraphs` (the greeting, signoff and metadata stay as they are);
   - LinkedIn: each variant's `message`.
   The skill loads as instructions, not as a tool that returns text: apply them yourself to those fields, in the draft's language, with `user_prefs.tone_directives` as the voice to match. Write only the final text back into the same fields. Subject lines, greetings and signoffs are out of scope.
3. Run the gate the calling prompt names. If the rewrite broke it (length, claims), fix the wording and re-gate; don't drop the pass.

If the `humanizer:humanizer` skill isn't installed, skip the pass, say so in your report, and carry on. It is a polish step, not a requirement.

## What the rewrite must keep

The humanizer edits style. The rules of the calling prompt still win on content:

- **Every fact, number, name, employer and tech stays exactly as drafted**, and nothing new comes in. A "specific detail" the humanizer would add must come from `cv_fact_base_merged.json` or the company research, never from guesswork.
- Team scope stays team scope: no solo-work phrasing for `team_context_companies`.
- Gaps stay stated as gaps; a negation stays in the same clause as the skill it negates (the claims check reads it that way).
- Length limits still hold: short-letter body 500–750 characters, LinkedIn connection request ≤ 300, direct message ≤ 700.
- Cold flow: the opening hook must still match across the letter, short letter and LinkedIn. Rephrase it the same way everywhere or leave it.
- Same language as the draft. In French, treat the equivalent constructions the same way ("ce n'est pas X, c'est Y", "non seulement… mais aussi").
- `tone_directives` override the humanizer's defaults on conflict.
