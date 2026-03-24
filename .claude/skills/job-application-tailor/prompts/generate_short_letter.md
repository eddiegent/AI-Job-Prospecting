Write a very concise introduction/motivation letter based on:
1. a structured CV fact base
2. a structured job offer analysis
3. the full motivation letter (already generated) — distill it, don't start from scratch

## Goal
Create a punchy, short version of the motivation letter suitable for online application forms, email bodies, or any context with tight character limits. Think of it as the "elevator pitch" version.

## Rules
- The entire body text (all paragraphs combined) must be between 500 and 750 characters — this is a hard constraint
- No invented experience — every claim must be grounded in the CV
- No headers, no addresses, no date — just greeting, body, signoff, and name
- Keep the same language as the full letter
- Prioritise: who you are, your strongest match to the role, and a call to action
- Every sentence must earn its place — cut anything that doesn't directly strengthen the candidacy

## Structure
- Greeting (same as the full letter)
- 1-2 short paragraphs (the core pitch)
- Signoff + name

## Output format
Return valid JSON matching `schemas/letter.schema.json`. Omit `sender_address`, `recipient_name`, `recipient_address`, `date_line`, and `subject_line` (or set them to empty) — this letter is body-only.
