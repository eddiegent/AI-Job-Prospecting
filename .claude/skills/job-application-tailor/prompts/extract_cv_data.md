You are extracting only factual, evidenced information from a source CV.

## Mission
Create a structured fact base from the CV so later steps can tailor truthfully.

## Scope boundary — raw docx only
This extractor only sees the raw `MASTER_CV.docx`. It must **not** incorporate anything from `resources/cv_addendum.md`, `resources/user_prefs.yaml`, or any Claude memory. Those live in a separate per-run enrichment layer (`scripts/user_customization.py`) that Step 5 (tailor_cv) merges into a local copy of the fact base. Keeping the extractor ignorant of that layer is what lets `scripts/verify_fact_base.py` use the cached `cv_fact_base.json` as ground truth against the docx. Do not mutate that contract.

## Extract
- candidate name, headline / title, contact details
- **contact.github** — if the CV header includes a GitHub URL (e.g. `github.com/janedoe` or `github.com/janedoe/my-project`), capture it verbatim in `contact.github`. Many CVs will not have one — if absent, **omit the field entirely** rather than writing an empty string.
- **candidate location** — the candidate's residential location as it appears in the CV header or contact section (e.g. "Brunoy (91)", "London, UK", "Austin, TX"). Keep the original formatting. This is used later for commute and distance analysis against job locations.
- summary
- skills, tools / technologies, methodologies
- experience by role (company, location, role, dates, details, metrics, international signals)
- full-time training periods with dates — these must appear in the experience list with `"type": "training"` so they fill timeline gaps between roles
- **personal projects** — if the CV has a dedicated section titled "Projets personnels", "Personal Projects", "Side Projects", "Projets open source", or similar, capture each project under the top-level `projects` array. Each item holds `name` (project title), `dates` (as written in the CV, optional), `link` (repo or live URL, optional), and `bullets` (the project's description points). Do **not** confuse personal projects with work experience — personal projects live in their own dedicated CV section; work done *inside* a role belongs in `experience[*].details`. If the CV has no personal-projects section, **omit the `projects` field entirely** — do not emit an empty array.
- education / training
- languages
- explicit achievements or metrics
- explicit transition statements such as "currently learning..." if present

## Output format
Return valid JSON matching `schemas/cv_fact_base.schema.json`. Read that schema file for the exact structure.

**Example structure** (abbreviated):
```json
{
  "candidate_name": "Jane Doe",
  "headline": "Senior Software Engineer",
  "contact": {"email": "jane@example.com", "phone": "+33 6 00 00 00 00", "linkedin": "linkedin.com/in/janedoe", "github": "github.com/janedoe"},
  "candidate_location": "Paris (75)",
  "summary": "...",
  "skills": ["System design", "API integration"],
  "technologies": ["C#", ".NET", "SQL Server"],
  "technologies_to_deepen": ["Kubernetes", "Kafka"],
  "methodologies": ["Scrum", "Clean Code", "SOLID"],
  "experience": [
    {"company": "Acme Corp", "location": "Paris", "role": "Senior Developer", "dates": "Jan 2020 – Present", "type": "role", "details": ["..."], "metrics": ["..."], "international_signals": ["..."]}
  ],
  "projects": [
    {"name": "My side project", "dates": "2024 – ongoing", "link": "github.com/janedoe/my-project", "bullets": ["What it does", "Stack used"]}
  ],
  "education": ["2015 : University X – MSc Computer Science"],
  "languages": ["Bilingue Français / Anglais"],
  "transition_signals": ["Currently learning cloud architectures"]
}
```

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

## Proficiency tiers — `technologies` vs `technologies_to_deepen`

`technologies` is for tech the candidate has actually worked with. Put into the
separate `technologies_to_deepen` array (and do **not** also list it in
`technologies`) any tech the CV itself marks as lower-proficiency, e.g.:

- a dedicated "Familier / à approfondir", "Familiar / to deepen", "Notions" or
  "En découverte" (or equivalent) section/column;
- a technology the CV only **evaluated but did not adopt** — e.g. "évaluation
  RabbitMQ vs Kafka (RabbitMQ retenu)" means RabbitMQ is the held tool and
  **Kafka belongs in `technologies_to_deepen`, not `technologies`**.

This stops the tailoring step from presenting exploratory tech as a core skill.
If the CV makes no such distinction, leave `technologies_to_deepen` empty.

## CRITICAL — Contamination prevention
If a job offer is present in context, **ignore it completely** when extracting the fact base. The `technologies` and `methodologies` arrays must contain ONLY items that appear as written text in the CV. A verification script will cross-check every item against the raw CV text and block the pipeline if fabrications are detected. Common contamination patterns to avoid:
- Adding a framework because the job asks for it (e.g. EntityFramework, ASP.NET MVC) when the CV doesn't list it
- Adding a language because the job requires it (e.g. PHP, PowerShell) when the CV doesn't mention it
- Upgrading "adjacent exposure" to "direct skill" to improve the match
