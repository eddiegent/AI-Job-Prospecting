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

## Rules
- Only claim "direct" if the CV explicitly names the skill or a very close synonym
- "transferable" must include a concrete explanation of why the experience transfers
- Be honest about gaps — do not stretch transferability
- Write evidence and notes in the same language as the job offer
