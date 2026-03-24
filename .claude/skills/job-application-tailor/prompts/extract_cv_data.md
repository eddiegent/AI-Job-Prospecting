You are extracting only factual, evidenced information from a source CV.

## Mission
Create a structured fact base from the CV so later steps can tailor truthfully.

## Extract
- candidate name, headline / title, contact details
- summary
- skills, tools / technologies, methodologies
- experience by role (company, location, role, dates, details, metrics, international signals)
- full-time training periods with dates — these must appear in the experience list with `"type": "training"` so they fill timeline gaps between roles
- education / training
- languages
- explicit achievements or metrics
- explicit transition statements such as "currently learning..." if present

## Output format
Return valid JSON matching `schemas/cv_fact_base.schema.json`. Read that schema file for the exact structure.

Key points:
- Each experience item has a `type` field: `"role"` or `"training"`
- Training periods with specific dates belong in both `experience` (for timeline continuity) and `education`

## Language
- Extract facts preserving the original language of the CV
- Field names in the JSON must remain in English regardless of CV language

## Hard rules
- Only include what is explicitly supported by the CV
- Do not infer missing technologies
- Do not convert adjacent exposure into direct ownership
- Do not merge different roles
- Full-time training periods that have specific dates must appear in the experience array so the timeline has no gaps
- List all experiences in strict reverse chronological order

## CRITICAL — Contamination prevention
If a job offer is present in context, **ignore it completely** when extracting the fact base. The `technologies` and `methodologies` arrays must contain ONLY items that appear as written text in the CV. A verification script will cross-check every item against the raw CV text and block the pipeline if fabrications are detected. Common contamination patterns to avoid:
- Adding a framework because the job asks for it (e.g. EntityFramework, ASP.NET MVC) when the CV doesn't list it
- Adding a language because the job requires it (e.g. PHP, PowerShell) when the CV doesn't mention it
- Upgrading "adjacent exposure" to "direct skill" to improve the match
