Create an interview preparation pack from:
1. the tailored CV
2. the job offer analysis
3. the original CV fact base
4. the match analysis (including `overall_fit_pct`)
5. company research (if available)

## Goal
Help the candidate walk into the interview confident and prepared. Every talking point should be grounded in real experience, and every gap should have an honest, strategic framing.

## Include

1. **Quick reference block** — right at the top, before the fit score, add a reference block with key links and metadata so the candidate has everything in one place:
   ```
   ## Quick Reference
   - **Job offer**: [job title](URL) — or the URL as plain text if no markdown rendering
   - **Company**: company name — company career page URL if found during research
   - **Location**: location and work mode (remote/hybrid/onsite)
   - **Applied on**: today's date
   - **Output folder**: the path to the output folder for this run
   ```
   Include the original job URL exactly as provided by the user (from `$ARGUMENTS`). If company research found additional useful links (career page, team page, Glassdoor, Welcome to the Jungle), add them too. This block is a practical cheat-sheet the candidate can glance at before an interview.

2. **Fit score banner** — display the overall fit percentage and match summary clearly:
   ```
   ## Fit Score: XX% — [LOW / MEDIUM / GOOD / VERY GOOD]
   Direct matches: X | Transferable: X | Gaps: X
   ```
   Thresholds: < 50% = LOW, 50-69% = MEDIUM, 70-84% = GOOD, 85%+ = VERY GOOD. Use labels from `config/languages.yaml` if available.

3. **Company context** (if research provided) — key facts, recent news, culture signals, and how to reference them naturally in conversation
4. **Role summary**
5. **Fit narrative** — why this profile is relevant for this specific role
6. **Direct matches** — table of strongest matching points with CV evidence
7. **Transferable points** — adjacent experience that transfers, with explanation
8. **Gaps to handle honestly** — table with gap + recommended honest framing
9. **8 likely interview questions** with talking points for each
10. **Transition narrative** — a concise story connecting past roles to this target role
11. **5 smart questions to ask** — informed by company research when available

## Rules
- Ground everything in the source CV — do not fabricate stories
- Do not conceal gaps — frame them honestly and strategically
- If company research is provided, weave relevant facts into talking points and smart questions
- Write in the same language as the job offer
- Use section headings from `config/languages.yaml` if available

## Output format
Return markdown only. Use the language-appropriate template from `templates/`:
- French: `templates/interview_prep_template_fr.md`
- English: `templates/interview_prep_template_en.md`
- Fallback: `templates/interview_prep_template.md` (French)
