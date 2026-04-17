Write a very concise speculative cold-letter variant for online forms, email bodies, or any context with tight character limits.

You will receive:
1. the structured CV fact base
2. `company_profile.json`
3. `selected_role.json`
4. the full speculative motivation letter (already generated) — **distill it, don't start from scratch**
5. the **user prefs** dict (honour `tone_directives`, `team_context_companies`, `default_language` — same rules as the full cold letter)

## Goal

A 4-line, email-ready version of the full cold letter. Same hook, same ask, cut ruthlessly. Think of it as the opener the recipient actually reads before deciding whether to click through to the attached CV.

## Rules

- **Body length: 500–750 characters total.** Hard constraint.
- **Same hook as the full letter.** The specific company observation from the profile carries over — do not replace it with a generic "J'ai été impressionné par votre entreprise".
- **Same ask.** Still a conversation, not an application. Do not let brevity collapse the ask into "please consider my application" boilerplate.
- **No headers, no addresses, no date, no subject.** Just greeting, body, signoff, name.
- **Same language and tone** as the full letter — apply `tone_directives` and `team_context_companies` rules identically.
- **No solo-work phrasing** for any `team_context_companies` entry.
- **No invented experience.** Every claim grounded in the fact base.
- **No pretending there's a posting.** Still cold — no "votre annonce", no "pour ce poste".
- **Signoff**: `Cordialement,` or `Bien cordialement,` (fr) / `Best regards,` (en).

## Structure

- Greeting (same as the full letter)
- 1–2 short paragraphs: (1) the specific company hook + who you are, (2) why you + what you're proposing
- Signoff + name

## Output format

Return valid JSON matching `schemas/letter.schema.json`. Omit `sender_address`, `recipient_name`, `recipient_address`, `date_line`, and `subject_line` (or set them to empty) — body-only.

Set `letter_type` to `"speculative"` — this is the short cold letter, and the audit trail matters.
