Produce the **company dossier** — a single markdown deliverable the candidate reads before any conversation with the target company. This is the Phase-E replacement for the fit-score document in the offer-based flow: no JD means no scoreable requirements, so the dossier centres a **narrative angle of approach** plus interview preparation.

You will receive:
1. the structured CV fact base (positioning, strengths, career timeline)
2. `company_profile.json` — mission, products, values, recent news, leadership, hiring signals, inferred pain points, research gaps, sources
3. `selected_role.json` — the angle the candidate is leading with, including `rationale` and `risk_notes`
4. the tailored CV JSON (for evidence-backed talking points)
5. the speculative motivation letter JSON (so openers, hooks, and objection answers stay aligned)
6. the LinkedIn outreach JSON (so contact recommendations align with actual messages)
7. the **user prefs** dict — honour `tone_directives`, `team_context_companies`, `default_language`

## Goal

One document that makes the candidate walk into a cold-opened conversation confident, informed, and honest about what they do and do not know. Every factual claim about the company cites a source URL. Every talking point about the candidate maps to the fact base or the tailored CV.

## Structure — sections, in this order

Use the section headings below verbatim (in the target language) — the layout matters because the candidate will skim, not read.

### 1. Quick reference

Opening block, before the first prose section. Same spirit as the offer-based flow's quick reference, adapted for cold:

```
## Quick Reference
- **Entreprise** : [company_name] — [canonical_url]
- **Secteur** : [industry]
- **Taille** : [size_band] ([headcount_estimate or "estimation indisponible"])
- **Localisation principale** : [locations[0]]
- **Angle ciblé** : [selected_role.title] — [selected_role.source]
- **Prospection envoyée le** : [today's date]
- **Dossier généré** : [output folder path]
```

Localise labels for the target language (`fr` default / `en`). Omit lines where the data is missing rather than writing "N/A".

### 2. Company at a glance

Exactly 5 bullets distilled from `company_profile.json`. Each bullet cites its source URL inline. Cover: mission in one line (quoted or tight paraphrase), products/services, size and locations, one standout culture or values signal, the most relevant recent-news item. If `research_gaps` is non-empty, add a sixth bullet flagging the biggest gap so the candidate knows where the summary is thin.

### 3. Why you, why them — angle of approach

This replaces the fit score. 3–5 short paragraphs (not bullets — this is the narrative the candidate rehearses mentally).

- **Why this company, specifically.** Anchor on 1–2 concrete company facts (recent news first, then mission or product). Match the motivation-letter hook exactly — the candidate should feel a coherent story across all artefacts.
- **Why this angle.** Quote or paraphrase `selected_role.rationale`. Call out `selected_role.emphasis_areas` explicitly — these are the topics the candidate should volunteer early in any conversation.
- **Why this candidate.** 2–3 strengths from the fact base that map to both `emphasis_areas` and the company profile. Give one concrete example per strength (real tech, real project, real number) drawn from the tailored CV where possible.
- **Honest caveats.** Fold in `selected_role.risk_notes` and any `company_profile.pain_points_inferred` you're leveraging — flag them as inferred and note how the candidate would adapt if the hypothesis turns out wrong.

No fit percentage. No "overall alignment score". The angle is the asset.

### 4. Who to contact

Ordered list, ranked by seniority and proximity to the selected role. Drawn from `company_profile.leadership[]` and aligned with the LinkedIn outreach JSON — if LinkedIn produced a variant for a contact, reflect that here.

For each contact:
- **Name and role** (with `source_url`)
- **Why reach out to them** — one sentence tying their role to `selected_role.title`
- **LinkedIn URL** if present
- **Suggested first message** — reuse the relevant LinkedIn connection-request verbatim from the outreach JSON (do not rewrite — coherence matters)
- **Fallback when declined** — one line on the next contact to try

If `leadership[]` is empty, this section becomes one paragraph explaining that no named contacts surfaced during research, pointing to the LinkedIn output's placeholder messages, and recommending the candidate use LinkedIn company-page search with filter "hiring" or Welcome to the Jungle team pages to find names manually. Add that gap to § Research gaps too.

### 5. Likely objections and prepared answers

The cold flow's distinctive interview prep. The recipient will ask — explicitly or mentally — "why are you reaching out to us without a posting?" The candidate needs quick, honest answers. Cover at least:

- **"Why us, without a posting?"** — 2–3 sentence answer grounded in `recent_news` / `mission_statement` / `products_services`. Same spine as the letter opening.
- **"We're not hiring right now for [selected_role.title] — what would you propose?"** — candidate should acknowledge, redirect to adjacent scope (referencing `emphasis_areas`), and be explicit about openness ("I'm happy to explore what you actually need").
- **"Your experience is mostly [X] — this company is mostly [Y]"** — map the candidate's closest adjacency honestly, using one of the `risk_notes` as the handle.
- **"What would you bring in the first 90 days?"** — 2–3 concrete deliverables the candidate could credibly ship, tied to stated company priorities (recent_news / hiring_signals / inferred pain points — flag inferred ones).
- **"Why leave your current / recent role?"** — a one-line honest framing consistent with the fact base's timeline. Do not invent grievance.

Produce each as a Q-then-A pair, with the A under 120 words.

### 6. Conversation openers — questions to ask

3–5 specific questions the candidate can use mid-conversation to demonstrate homework and surface the company's real priorities. Each question:

- Ties to a concrete fact from the profile (recent news, product, hiring signal, values) with the source URL cited
- Is open-ended (not yes/no)
- Is not fishable from the company's public site in 30 seconds — i.e. it asks about priorities, tradeoffs, or lived reality behind the public facts
- Avoids asking "what's your culture like" and similar empty prompts

### 7. Interview prep — role-specific

STAR-style prep tailored to `selected_role.title`. Produce 6 likely interview questions for this role band (`selected_role.seniority_band`) and for this company size/industry. For each question provide:

- The question (in the target language)
- A **talking-point scaffold**: 2–4 bullets anchored in the fact base or tailored CV. No fabricated stories. If the candidate cannot honestly answer a question from their real experience, replace the question with a different one — do not invent experience.

Weight the set toward the `emphasis_areas` of the selected role. For a lead / manager seniority band include at least one question on team scaling, hiring, or mentoring. For an IC band include at least one on technical depth. Avoid generic HR-style questions already covered by § 5.

### 8. Transition narrative

Two short paragraphs the candidate can use when the recruiter / contact asks "tell me about your career so far." Stitch the fact-base roles into a coherent arc that naturally lands on `selected_role.title`. No fabrication — the arc must follow the real chronology.

### 9. Research gaps

Honest, short, list-format. Copy every entry from `company_profile.research_gaps` verbatim, plus any gap the dossier itself surfaces (e.g. "no named engineering leadership found — who-to-contact section uses placeholders"). The user should know exactly where their own due diligence still needs to happen.

## Hard rules

- **Every company fact cites a source URL** — either inline (Markdown link) or as a trailing `[source](url)` reference. If a claim cannot be sourced, drop it.
- **Inferred stays inferred.** When referencing `tech_stack_hints` or `pain_points_inferred`, write "il semble que" / "it looks like" / "inferred from [source]". Never state as fact.
- **No fabrication.** No made-up company facts, no invented candidate stories, no imagined company priorities. If the profile does not support a talking point, cut it.
- **No fit percentage.** The cold flow has deliberately no score. The angle-of-approach narrative replaces it.
- **No posting reference.** No "in response to your opening", "for this role" — the dossier prepares the candidate for a conversation, not a vacancy.
- **No solo-work phrasing** for `user_prefs.team_context_companies` — applies to § Interview prep and § Transition narrative especially.
- **Respect `forbidden_title_labels`.** If `selected_role.title` contains a forbidden label (only possible via `user_override`), paraphrase around it throughout the dossier.
- **Alignment across artefacts.** The hook in the motivation letter, the opening sentence in the LinkedIn connection-request, and § 3 of this dossier must reference the same company fact. Inconsistency between artefacts is the single most preventable cold-flow mistake.
- **Language.** Write in `user_prefs.default_language` (default `fr` for the cold flow). All section headings localised.

## Output format

Return pure markdown. No JSON wrapper, no code-fence around the whole document. The SKILL.md step writes your output to `$OUTPUT_DIR/company_dossier.md` directly.

Filename constraint: the dossier lives at the output root (`company_dossier.md`), not in `_prep/`. It is a first-class deliverable the user opens before a call — the research JSON stays in `_prep/` as the audit trail.
