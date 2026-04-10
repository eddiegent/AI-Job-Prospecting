Write a short, concise motivation letter based on:
1. a structured CV fact base (includes `candidate_location`; may also include `addendum_off_cv_facts` if the user has off-CV facts worth surfacing)
2. a structured job offer analysis (includes `location` and `work_mode`)
3. the match analysis (includes `location_analysis` with commute assessment)
4. company research (if available) — use company context to make the letter feel targeted, not generic
5. the **user prefs** dict from `resources/user_prefs.yaml` (may be empty). Honour these keys:
   - `tone_directives` — a list of short free-form style notes. Read them verbatim and apply them. Examples of what a user might put here: "natural and conversational, not formal", "no corporate buzzwords", "first person, active voice". These override the generic defaults below when they conflict.
   - `team_context_companies` — a list of companies where the candidate was part of a team. When writing about any of these companies, the letter must never use solo-work phrasing (no "seul développeur", "single-handedly", "as the only developer", "j'ai développé seul", "by myself"). Frame contributions as part of a team even if the specific achievement was the candidate's own.
   - `default_language` — if `fr` or `en`, override auto-detection; if `auto` (or unset), follow the job-offer language.

## Goal
Create a credible, natural-sounding application letter. The reader should feel a real person wrote this for their specific role — not that a template was filled in.

## Tone — this matters a lot
Write like you're addressing a respected colleague, not a royal court. The tone should be **direct, warm, and human** — professional but not stiff.

Recruiters read dozens of letters a day. The ones that stand out feel genuine, not performative. Short sentences. Clear language. A bit of personality.

**Do this:**
- Use simple, direct language — say things the way you'd say them out loud
- Keep sentences short. Vary the rhythm. One idea per sentence.
- Be specific and concrete — a real project, a real number, a real tool
- Let the personality of the candidate come through

**Avoid these anti-patterns** (they make letters sound robotic and interchangeable):
- "Fort de X ans d'expérience, je souhaite mettre mes compétences au service de..." → Instead, lead with something specific about the role or company that caught your eye
- "...résonne avec mes valeurs professionnelles" / "...correspond pleinement à l'environnement dans lequel je souhaite évoluer" → Too vague. Say *what* specifically appeals and *why*
- "Mon parcours m'a permis de développer une expertise approfondie en..." → Just say what you did
- Stacking multiple nested clauses in a single sentence — if a sentence has more than one comma, consider splitting it
- Ultra-formal signoffs like "Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées" → Cap at "Cordialement," or "Bien cordialement,"

## Rules
- No invented experience — every claim must be grounded in the CV
- No empty flattery or generic buzzwords
- No exaggerated passion story
- **Don't imply solo work** — phrases like "en autonomie complète" or "j'ai piloté seul" suggest the candidate did everything alone. In reality, most work happened within a team. Only mention autonomy if the CV fact base explicitly marks a period as solo/autonomous, and even then scope it to that specific period, not the whole tenure. Companies listed in `user_prefs.yaml → team_context_companies` are a hard no for any solo-work phrasing, regardless of what the CV bullets say.
- If the candidate lives near the job location, it's worth mentioning naturally (e.g. "basé à Brunoy, à proximité de vos locaux" or "based locally in..."). Geographic proximity is a real advantage — recruiters prefer candidates who won't need relocation. But don't force it if the role is fully remote or if the candidate is far away.
- Keep it short (3-4 paragraphs max)
- Paragraphs should be 2-4 sentences, not dense blocks
- Signoff must be "Cordialement," or "Bien cordialement," — nothing more formal
- Align to the language of the job offer unless a target language is specified

## Suggested structure
1. Opening: name the role, and mention one specific thing about the company or role that caught your attention (not generic praise)
2. Middle: 2-3 relevant strengths grounded in the CV, with concrete examples. Keep it punchy — one strength per short paragraph if needed
3. Closing: brief, confident interest in discussing the role — one sentence is enough

## Output format
Return valid JSON matching `schemas/letter.schema.json`. Read that schema file for the exact structure.

Key fields: `sender_name`, `sender_address` (array), `recipient_name`, `recipient_address` (array), `date_line`, `subject_line`, `greeting`, `paragraphs` (array), `signoff`, `name`.
