# Evidence discipline — shared by every prompt that writes about the candidate

Added after an over-claiming incident. Read by the letter, short-letter, LinkedIn and interview / dossier prompts of both flows; the gates' claims check enforces most of it.

- Read `cv_fact_base_merged.json`. Cite only things the CV or addendum say, in the scope they say it (employer, team vs solo, design vs tuning).
- Never write "j'ai pratiqué X pendant N ans", "au quotidien", "tous les jours", "pratique quotidienne" about the candidate. Name the concrete thing done instead (e.g. "remplacé une API SOAP par une API REST").
- Copy every figure as the source states it ("17 000+" stays 17 000+). Never round up, scale, or add a number the master CV and addendum don't state; the claims check reads every number.
- Never mention skills listed in `familiar_only_skills` as strengths. Naming one as a gap is fine ("n8n reste à apprendre") — keep the negation in the same clause as the skill, or the claims check reads it as a claim. Do not describe the employer's product or team with claims taken from nowhere (e.g. "utilisé tous les jours par les métiers").
- Gaps (domain knowledge, tools never used) are stated plainly and briefly, not dressed up.
