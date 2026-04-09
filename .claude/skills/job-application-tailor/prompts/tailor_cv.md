You must tailor a candidate CV to a specific job offer.

You will receive:
1. a structured CV fact base
2. a structured analysis of the job offer (including `company_size` field)
3. the match analysis (direct/transferable/gap for each requirement)
4. company research (if available) — use this to confirm company size and understand what the company values

## Goal
Produce a more relevant CV while remaining fully truthful. The tailoring should make the reader think "this person is a natural fit" — not by inventing, but by emphasising the right things.

## Company-size awareness
Adapt the level of detail based on company size. This matters because small companies need generalists while large ones value specialists:

- **Small company / startup (< 50 people)**: expand roles that show versatility — automation, process improvement, tool integration, SaaS orchestration, cross-functional work. A small team needs people who contribute beyond their core technical specialty.
- **Mid-size company (50–500)**: balance depth and breadth. Emphasize the core technical match but also highlight collaboration, integration, and autonomy.
- **Large company / ESN (> 500)**: focus on depth. Emphasize technical expertise, methodology (SOLID, tests, CI/CD), and the ability to work within structured teams and processes.

## Candidate location
Include the candidate's residential location (from `candidate_location` in the CV fact base) in the `contact_line` field alongside email, phone, and LinkedIn. Location is valuable on a CV — it tells the recruiter at a glance whether the candidate is local, nearby, or would need to relocate. Keep the original format from the CV (e.g. "Brunoy (91)", "London, UK").

## Allowed changes
- **Adjust** the title / headline / summary to highlight the most relevant aspects of the candidate's actual profile — but the core identity must come from the master CV, not from the job offer. If the master CV says "Services, Intégration & Architectures Applicatives", do not replace that with "Backend" or "Full-Stack" just because the job offer uses those words. You may reorder or emphasise existing terms, drop less relevant ones, or add a qualifier that is evidenced in the CV — but never inject a specialisation label that the candidate doesn't use to describe themselves.
- Reorder skills to lead with the most relevant
- Tighten wording, emphasize relevant responsibilities and technologies
- Compress less relevant older detail to fewer bullets

## Preserving skill sections
The master CV may contain dedicated skill/competency sections beyond the main technical skills table (e.g. "Développement assisté par IA", "Leadership", "Domain expertise"). These sections are part of the candidate's professional identity. Every such section must appear in the tailored CV's `skills_sections` array — you may reorder them for relevance but never drop them entirely. Check the CV fact base `technologies` and the raw CV structure to ensure no dedicated section is lost.

## Forbidden
- Inventing projects, achievements, tools, certifications, or leadership claims
- Adding keywords not evidenced in the CV
- **Dropping dedicated skill sections** from the master CV — if the original CV has a section like "Développement assisté par IA" or "Automation & Low-Code", it must appear in the tailored output even if it's not directly relevant to the job offer. These sections reflect the candidate's identity and differentiators.
- **Replacing the candidate's professional identity with job offer language** — if the CV describes someone as a "Desktop & Services" developer, do not relabel them as "Backend", "Full-Stack", "DevOps", or any other specialisation just because the job offer uses that term. The title and tagline must reflect how the candidate actually describes themselves.
- **Removing any work experience or training period** — every role from the source CV must appear, even if compressed to a single bullet
- **Reordering experiences** — strict reverse chronological order
- **Creating timeline gaps** — training periods between roles must appear in the experience section

## Output format
Return valid JSON matching `schemas/tailored_cv.schema.json`. Read that schema file for the exact structure.

## Language
- Write all CV content in the same language as the job offer, unless a target language is explicitly specified
- JSON field names must remain in English

## Style
ATS-friendly, clear, professional, concise, realistic — no inflated language.
