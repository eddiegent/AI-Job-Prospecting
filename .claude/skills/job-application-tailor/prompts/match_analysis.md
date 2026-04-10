You are creating a structured match analysis between a candidate's CV and a job offer.

You will receive:
1. a structured CV fact base
2. a structured job offer analysis

## Goal
Produce a requirement-by-requirement match matrix that shows where the candidate is strong, where skills are transferable, and where there are gaps. This matrix feeds into CV tailoring and appears in the interview prep, so accuracy and honesty matter.

## Method
For each requirement (from `required_skills`, `preferred_skills`, `technologies`, and key `responsibilities`):
1. Search the CV fact base for direct evidence
2. If no direct match, look for adjacent or transferable experience
3. If neither, mark as a gap

## Classification
- **direct**: the CV explicitly names this skill, tool, or responsibility
- **transferable**: the CV shows adjacent experience that could reasonably transfer (explain the concrete link)
- **gap**: no evidence found in the CV

## Output format
Return valid JSON matching `schemas/match_analysis.schema.json`. Read that schema file for the exact structure.

Key points:
- `overall_fit_pct` formula: `(direct + transferable * 0.5) / total * 100`
- `match_type` must be one of: `"direct"`, `"transferable"`, `"gap"`
- `category` must be one of: `"required_skill"`, `"preferred_skill"`, `"technology"`, `"responsibility"`

## Geographic assessment
In addition to the skills matrix, produce a `location_analysis` object that compares the candidate's residential location (from the CV fact base `candidate_location` field) against the job's `location` and `work_mode`. Use your general knowledge of geography to assess commute feasibility — you don't need exact distances, just a sensible estimate (same city, same metro area, different region, different country, etc.). If the role is fully remote, note that distance is not a factor. This helps the candidate understand at a glance whether the job is geographically practical.

## Rules
- Only claim "direct" if the CV explicitly names the skill or a very close synonym
- "transferable" must include a concrete explanation of why the experience transfers
- Be honest about gaps — do not stretch transferability
- Write evidence and notes in the same language as the job offer
- **Name the role in the evidence** — when the evidence comes from a specific experience entry (especially an older one), include the company name and date range in the `evidence` field (e.g. "Conversions Fortran → C++ chez JFC Informatique & Média, Asnières (1994–2001)"). The CV tailoring step later uses these mentions to decide whether an older role should be kept in full or folded into a consolidated "Earlier experience" line. If the evidence is anchored to a specific pre-cutoff role and you don't name it, that role risks being hidden.

**Example structure** (abbreviated):
```json
{
  "match_summary": {"direct_count": 8, "transferable_count": 3, "gap_count": 2, "overall_fit_pct": 73},
  "location_analysis": {
    "candidate_location": "Brunoy (91)",
    "job_location": "Paris",
    "work_mode": "hybrid",
    "commute_assessment": "Trajet faisable",
    "notes": "40-50 min en RER D, gérable en hybride"
  },
  "matches": [
    {"requirement": "C#", "category": "required_skill", "match_type": "direct", "evidence": "15 ans en C#/.NET chez Oodrive", "notes": ""},
    {"requirement": "Docker", "category": "preferred_skill", "match_type": "transferable", "evidence": "Conteneurisation Docker chez Oodrive", "notes": "Utilisé pour CI/CD, pas en production"},
    {"requirement": "Kubernetes", "category": "technology", "match_type": "gap", "evidence": "", "notes": "Non mentionné dans le CV"}
  ]
}
```
