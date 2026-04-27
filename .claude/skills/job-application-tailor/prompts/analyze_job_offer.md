You are analysing a job offer for the purpose of creating a truthful, tailored application pack.

## Mission
Extract the role requirements and likely ATS signals without inventing or over-interpreting.

## Extract
- job title, company name, location (city/area as stated in the offer), seniority level
- **work mode** — `onsite`, `hybrid`, `remote`, or `unknown`. Look for signals like "télétravail", "remote", "présentiel", "sur site", "X jours par semaine", "full remote", "hybride", "work from home", etc.
- required skills, preferred skills
- responsibilities
- technologies / tools / methods
- domain / industry
- language requirements
- keywords likely to matter for ATS
- company size signals (explicit headcount, "petite équipe", "startup", "ESN", "grand groupe", or inferred from context)
- hiring signals about culture, autonomy, communication, architecture, testing, delivery

## Output format
Return valid JSON matching `schemas/job_offer_analysis.schema.json`. Read that schema file for the exact structure.

Key points:
- `company_size` should be one of: `"small"`, `"medium"`, `"large"`, `"unknown"`
- Include a `detected_language` field (ISO 639-1 code, e.g. `"fr"`, `"en"`) — this drives the language of all subsequent outputs
- **Platform vs real client** — some postings are republished by job boards (Free-Work, Indeed, Welcome to the Jungle, LinkedIn, reservoirjobs, jooble, APEC, Hellowork, Monster, Glassdoor, France Travail, etc.). If the posting identifies the employer only as one of these platforms and the body of the offer mentions a distinct real client, set `company_name` to the real client and `source_platform` to the platform. If no real client is discoverable, set `company_name` to the platform and `company_is_aggregator: true` so the skill can ask the user. Leave both fields unset when the posting is clearly from a direct employer.

## Language mis-detection cross-check

WebFetch summarises pages through an internal LLM and can silently **translate** a French (or other non-English) posting into English before returning it. If you set `detected_language` based only on the text WebFetch returned, you'll produce an English pack for a French role — a slow, wasted run.

Before committing `detected_language`, cross-check against market signals in the posting. Any **one** of these is enough to flip `detected_language` from `"en"` to `"fr"`:

- Job title contains French-only abbreviations: **"IA"** in a tech title (vs. English "AI"), "Ingénieur", "Chef de projet", "Développeur"
- Paris / Lyon / Toulouse / Bordeaux / Nantes / Lille / Marseille as the posting location
- French-market benefits: **RTT days**, **Swile** / Edenred / Ticket Restaurant, **Alan** / Malakoff Humanis, **50 % transport** (prise en charge transports), **mutuelle**, **tickets restaurant**, **convention collective Syntec**, **CSE**
- French-law artefacts: **CDI** / **CDD**, **35 heures**, **congés payés** with specific day counts
- French job-board provenance in the URL (apec.fr, francetravail.fr, hellowork.com, welcometothejungle.com/fr)
- Team member names that are distinctly French (François, Florine, Hawa, Olivier as first-name-only signatories)

When you spot the signals but the text is in English, that's WebFetch translating. Set `detected_language: "fr"` and write the rest of the analysis in French — the downstream pack will match the real posting language.

The same logic applies to other languages (German, Spanish, Italian, Dutch) if their market signals are present; the French case is the most common at this project's location.

**Example structure** (abbreviated):
```json
{
  "job_title": "Développeur C# / .NET",
  "company_name": "Acme Corp",
  "location": "Paris",
  "work_mode": "hybrid",
  "seniority": "Confirmé (5+ ans)",
  "company_size": "medium",
  "required_skills": ["C#", ".NET", "Scrum"],
  "preferred_skills": ["Docker", "CI/CD"],
  "responsibilities": ["Concevoir et développer des applications"],
  "technologies": ["C#", ".NET", "SQL Server"],
  "domain": "SaaS / Cloud",
  "languages": ["Français", "Anglais courant"],
  "ats_keywords": ["C#", ".NET", "agile", "Scrum"],
  "signals": ["Startup culture", "Remote-friendly"],
  "detected_language": "fr"
}
```

## Rules
- If something is not explicit, use an empty string or empty list
- Do not hallucinate the job title
- Use concise phrases
