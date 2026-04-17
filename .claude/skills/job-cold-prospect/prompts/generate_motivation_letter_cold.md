Write a short, speculative motivation letter for a **cold-call application** — there is no job posting. The reader is a named contact (hiring manager, CTO, or recruiter) at the target company.

You will receive:
1. the structured CV fact base (includes `candidate_location`; may include `addendum_off_cv_facts`)
2. `company_profile.json` — mission, products, values, recent news, hiring signals, leadership, locations
3. `selected_role.json` — the angle the user has chosen to lead with
4. the **user prefs** dict from `resources/user_prefs.yaml`. Honour:
   - `tone_directives` — short free-form style notes, applied verbatim
   - `team_context_companies` — never use solo-work phrasing for any of these
   - `default_language` — fr or en, else fallback to fr for the cold flow

## Goal

Open a door. The letter is not responding to a vacancy — it is proposing a conversation. The reader should feel that the candidate specifically chose *this* company for *this* reason, not that they are mass-mailing.

## The opening hook is the whole letter

Recruiters and hiring managers ignore letters that start with "Fort de X années d'expérience". In the cold flow, the opening line decides whether anyone reads paragraph two. It must be:

- **Specific to this company** — pull one concrete detail from `company_profile.json`. Prefer, in this priority order:
  1. A recent news item (`recent_news[0].headline` + `relevance`) — funding, product launch, leadership change, CEO interview. Reference it by fact, not by flattery.
  2. A quote from `mission_statement` if genuinely distinctive (not "deliver value to customers").
  3. A specific product or service from `products_services` paired with a concrete reason it resonates with the candidate's experience.
  4. A values signal from `values_culture_signals` — only if it's distinctive (e.g. "transparent salary bands", not "great culture").

- **Grounded**: do not invent a personal story of encountering the company. If the fact base provides a real connection (conference, shared client, prior collaboration), use it. Otherwise write as an informed outsider who did their homework.

- **Honest about being speculative**: the second or third sentence should make clear this is an unsolicited approach — "je me permets de vous écrire" / "I'm reaching out without responding to a specific posting" — and pivot to why.

## Structure (3–4 paragraphs)

1. **Opening hook (2–3 sentences)** — specific observation from the profile + concise pivot to why you're writing. Name `selected_role.title` or its softer variant (e.g. "un rôle autour du …" / "a role along the lines of …") once here. Do not pretend a posting exists.

2. **Why you** (2–4 sentences) — 2–3 strengths from the fact base that map to `selected_role.emphasis_areas` **and** resonate with something concrete in the company profile. One strength per sentence. Concrete — a real tech, a real number, a real project.

3. **What you're proposing** (1–2 sentences) — conversation, not application. "J'aimerais explorer avec vous …" / "I'd like to explore whether …" Leave room for the company to shape the role. This is especially important when `selected_role.source` is `generalist` or `user_override` — the framing should welcome a scope conversation.

4. **Close (1 sentence)** — offer to discuss, signoff. Signoff: `Cordialement,` or `Bien cordialement,` (fr) / `Best regards,` (en).

## Tone — direct, warm, professional

Write like you're addressing a respected colleague. Short sentences. Clear language. A bit of personality.

**Do this:**
- Use simple, direct language
- Be specific and concrete — real project, real number, real tech
- Keep sentences short; vary the rhythm; one idea per sentence
- Let the candidate's personality come through

**Avoid these anti-patterns** (they scream "form letter"):
- "Fort de X ans d'expérience…" — never lead with this in the cold flow
- "…résonne avec mes valeurs professionnelles" / vague "aligns with my values"
- "Mon parcours m'a permis de développer une expertise approfondie en…" — just say what you did
- Ultra-formal signoffs
- Stacking multiple nested clauses in one sentence

Apply `user_prefs.tone_directives` verbatim. They override these defaults on conflict.

## Rules

- **No invented experience.** Every claim maps to the fact base.
- **No fabricated company facts.** Every company claim maps to `company_profile.json` and its cited sources. `tech_stack_hints` and `pain_points_inferred` are **inferred** — treat them as plausible angles ("it looks like your product might benefit from …"), not confirmed needs.
- **No solo-work phrasing** for any company in `user_prefs.team_context_companies` — no "j'ai piloté seul", "single-handedly", "as the only developer", "j'ai développé seul", "by myself", "en autonomie complète". These companies were team environments regardless of what an individual bullet says.
- **No pretending there's a posting.** Avoid "votre annonce", "in response to your offer", "pour ce poste". The letter is speculative.
- **Geographic proximity** — if the candidate is near `company_profile.locations[0]`, mention it naturally once (e.g. "basé à Brunoy, à proximité de vos locaux"). Skip if remote-first or if the distance is large.
- **Respect `forbidden_title_labels`** — if `selected_role.title` contains a forbidden label (only possible if it's a `user_override`), paraphrase around it in the letter using a neutral alternative.
- Keep it short (3–4 paragraphs, 2–4 sentences each).
- Write in `default_language` (fallback `fr` for cold flow).

## Letter metadata

- `sender_name` and `sender_address` — from the CV fact base.
- `recipient_name` — from `company_profile.leadership[0].name` if present and senior (CTO / VP Eng / hiring lead). Otherwise omit (empty string) — do not invent a name.
- `recipient_address` — company address if derivable from `company_profile.locations[0]`. Otherwise empty array.
- `date_line` — current date in local format.
- `subject_line` — short, specific, cold-flow-appropriate. Example (fr): `"Candidature spontanée — [selected_role.title]"`. Example (en): `"Reaching out — [selected_role.title]"`. Do not use "Candidature au poste de X" — that implies a posting.

## Output format

Return valid JSON matching `schemas/letter.schema.json` (reused from the tailor skill). Key fields: `sender_name`, `sender_address` (array), `recipient_name`, `recipient_address` (array), `date_line`, `subject_line`, `greeting`, `paragraphs` (array), `signoff`, `name`.

Set the optional `letter_type` field to `"speculative"` if the schema supports it — it's an audit trail for downstream steps that a cold letter was generated. If the field isn't in the schema, skip it silently.
