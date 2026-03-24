Write short LinkedIn messages based on:
1. the tailored application positioning
2. the job offer analysis
3. company research (if available) — especially the **Contacts** section for real names and LinkedIn profiles

## Goal
Produce **3 message variants**, each targeting a different recipient:
1. **recruiter** — a recruiter or talent acquisition specialist
2. **hiring_manager** — the direct hiring manager or tech lead
3. **internal_contact** — a current employee or mutual connection inside the company

## Using contacts
If company research includes a **Contacts** section with real names:
- Use actual names in the messages instead of generic "[Prénom]" placeholders
- Add the contact's LinkedIn URL in `linkedin_url` so the user can reach out directly
- If multiple contacts are found for a category, produce a variant for each

If no contacts were found for a category, use "[Prénom]" as placeholder.

## Rules
- Short, natural, professional
- No invented experience — mention 1-2 highly relevant truthful points
- Don't sound desperate or overload with detail
- Invite a conversation naturally
- Adapt tone: slightly more formal for hiring managers, warmer for internal contacts, direct for recruiters
- Write in the same language as the job offer

## Output format
Return valid JSON matching `schemas/linkedin.schema.json`. Read that schema file for the exact structure.

## Length target
500 characters max per message preferred.
