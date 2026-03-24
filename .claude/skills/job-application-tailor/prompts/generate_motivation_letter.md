Write a short, concise motivation letter based on:
1. a structured CV fact base
2. a structured job offer analysis
3. company research (if available) — use company context to make the letter feel targeted, not generic

## Goal
Create a credible application letter that matches the role without exaggeration. The reader should feel the letter was written specifically for their company and role.

## Rules
- No invented experience — every claim must be grounded in the CV
- No empty flattery or generic buzzwords
- No exaggerated passion story
- Keep it short (3-4 paragraphs max)
- Align to the language of the job offer unless a target language is specified

## Suggested structure
1. Opening: role targeted, what caught your attention
2. Middle: 2-3 relevant strengths grounded in the CV, with concrete examples
3. Closing: interest in discussing the role

## Output format
Return valid JSON matching `schemas/letter.schema.json`. Read that schema file for the exact structure.

Key fields: `sender_name`, `sender_address` (array), `recipient_name`, `recipient_address` (array), `date_line`, `subject_line`, `greeting`, `paragraphs` (array), `signoff`, `name`.
