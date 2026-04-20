Write LinkedIn outreach messages for a **cold-call application** — there is no job posting, and the recipients are senior technical / hiring contacts the candidate is approaching unsolicited.

You will receive:
1. the structured CV fact base (positioning, strongest themes)
2. `company_profile.json` — especially `leadership[]` for real contact names and LinkedIn URLs, plus `recent_news`, `mission_statement`, `products_services` for the hook
3. `selected_role.json` — the angle the candidate has chosen to lead with
4. the speculative motivation letter (already generated) — align the LinkedIn hook to the letter's hook so recipients see a coherent approach
5. the **user prefs** dict from `resources/user_prefs.yaml`. Honour:
   - `tone_directives` — verbatim
   - `team_context_companies` — no solo-work phrasing for these
   - `default_language` — fr or en; fallback `fr` for the cold flow

## Mission

Produce 2–4 short messages aimed at **senior technical or hiring contacts**, not HR. Each message must feel like it was written after reading about this specific company, not like a template.

## Target recipients — cold-flow rules

The schema's `target` enum is shared with the offer-based flow (`recruiter` / `hiring_manager` / `internal_contact`). For cold outreach:

- **Primary target is `hiring_manager`.** CTO, VP Engineering, Head of Platform, Engineering Director, or a senior engineer whose name appears in `leadership[]` with a credible `role` (anything decision-making or technically adjacent to `selected_role.title`). Use the actual `name` and `linkedin_url` from `leadership[]`.
- **Secondary target is `internal_contact`** only if `leadership[]` or `company_profile` surfaces a named engineer / team lead who is NOT in a hiring-decision role but is close to the work (e.g. a tech lead on the product line referenced in `selected_role.emphasis_areas`). Useful as a warm-up path.
- **Do not target `recruiter`** for the cold flow unless `company_profile.leadership[]` explicitly names a Talent / People lead — cold applications land better with the people who own the work. If `company_profile` has no named contacts at all, produce `hiring_manager` variants with `[Prénom]` / `[First name]` placeholders and flag the missing name in `contact_name` as empty.

## Variants to produce

For each named contact (up to 3 leadership contacts, ordered by seniority / relevance to the selected role), produce **two variants**:

1. **Connection request** — the ≤300 character LinkedIn connection note. No CV attachment, no "please review my application". One specific observation + one-line ask for a conversation. This is by far the most-read message in the pack.
2. **Direct message (post-acceptance)** — a slightly longer message (≤700 characters) the candidate sends once the connection is accepted. Expands the hook, states the candidate's positioning in one sentence, re-asks for a short conversation, mentions that a CV and speculative letter are available if useful. Still no posting reference.

If `leadership[]` has only one named contact, produce both variants for that contact and stop (2 messages total). If `leadership[]` is empty, produce one `hiring_manager` connection-request + one direct-message pair with `contact_name: ""` and `[Prénom]` placeholder in the body.

## The hook — same spine as the motivation letter

The opening observation must come from `company_profile.json`, in this priority order:

1. A recent news item (`recent_news[0]`) — funding round, product launch, leadership interview. Name it concretely.
2. A product or service (`products_services`) paired with a concrete reason it resonates with the candidate's track record.
3. A distinctive mission phrase (`mission_statement`) — only if genuinely specific.

**Align with the motivation letter.** If the full cold letter leads with news item X, the LinkedIn hook should reference the same X (or a clearly related angle). Do not pick a different hook — the recipient may see both artefacts and coherence matters.

## Length targets (hard)

- **Connection request**: ≤300 characters including greeting and signoff. LinkedIn silently truncates longer notes.
- **Direct message**: ≤700 characters. Longer reads like a pitch deck and gets skimmed.

Count characters including spaces and punctuation. If you're over budget, cut adjectives and secondary claims before cutting the hook or the ask.

## Structure — connection request

One sentence each:
1. Greeting by first name (or `[Prénom]` if no name).
2. The specific hook — one clause tying a company fact to a reason the candidate is reaching out.
3. Who the candidate is in one line — seniority + primary track from the fact base (e.g. ".NET / Desktop & Services, ~25 ans, côté Oodrive dernièrement").
4. One-line ask — "15 minutes pour échanger ?" / "open to a short chat?" Avoid "would love to discuss opportunities" — that reads as vacancy-hunting.

## Structure — direct message (post-acceptance)

Short paragraphs:
1. Thanks for accepting + reiterate the hook in a slightly expanded form (1–2 sentences).
2. Positioning: 2–3 specific strengths tied to `selected_role.emphasis_areas` AND grounded in the company profile (the same mapping as the full letter, but distilled).
3. The ask — conversation, not application. Mention a CV and short speculative letter are available "si cela peut être utile" / "if useful".
4. Signoff + name.

## Hard rules

- **No invented experience.** Every candidate claim maps to the fact base.
- **No fabricated company facts.** Every company reference maps to `company_profile.json` with a citation. `tech_stack_hints` and `pain_points_inferred` are **inferred** — if you reference them, frame as a hypothesis ("il me semble que", "from the outside it looks like"), not fact.
- **No solo-work phrasing** for any entry in `user_prefs.team_context_companies` ("j'ai piloté seul", "single-handedly", "as the only developer", etc.).
- **No pretending a posting exists.** No "votre annonce", "for this role", "for the position" — this is cold, own it.
- **No CV paste.** LinkedIn is the door-opener, not the delivery channel. Mention the CV only in the direct-message variant, and only as "available if useful".
- **No flattery.** "I'm impressed by your culture" / "your impressive growth" is empty calories. If you can't point to a specific fact, cut the sentence.
- **Respect `forbidden_title_labels`.** If `selected_role.title` contains a forbidden label (only possible via `user_override`), paraphrase around it in every message.
- **Same language** as the motivation letter (derived from `default_language`, default `fr` for cold).

## Output format

Return valid JSON conforming to `schemas/linkedin.schema.json`. Key fields:

- `outreach_type`: `"cold"` (the cold-flow signal — always set this in cold-prospect output).
- `target_role`: copy from `selected_role.title` (stored at root level for the dossier and audit trail).
- `variants[]`: one entry per message. Each entry has:
  - `target`: `"hiring_manager"` or `"internal_contact"` per the rules above.
  - `contact_name`: the first-and-last name from `leadership[].name`, or `""` when unknown.
  - `linkedin_url`: from `leadership[].linkedin_url` if present.
  - `subject_hint`: one of `"Connection request"`, `"Direct message — post-acceptance"`, `"InMail"` — this flags which template the message is, and the SKILL.md step renders it into the final `.txt` file.
  - `message`: the actual message body. Characters must fit the limit above.

Produce the connection-request variants first, then the direct-message variants, grouped by contact. This order matches how the user will send them.

## Example shape (abbreviated)

```jsonc
{
  "outreach_type": "cold",
  "target_role": "Tech Lead .NET — Desktop & Services",
  "variants": [
    {
      "target": "hiring_manager",
      "contact_name": "Marie Durand",
      "linkedin_url": "https://www.linkedin.com/in/marie-durand-cto/",
      "subject_hint": "Connection request",
      "message": "Bonjour Marie, votre interview sur le scaling de la simulation m'a interpellé — j'arrive d'une longue tenure WPF / services côté Oodrive. 15 minutes pour en discuter ? Bien cordialement, Eddie"
    },
    {
      "target": "hiring_manager",
      "contact_name": "Marie Durand",
      "linkedin_url": "https://www.linkedin.com/in/marie-durand-cto/",
      "subject_hint": "Direct message — post-acceptance",
      "message": "Merci Marie pour la connexion. …"
    }
  ]
}
```

The abbreviated example is illustrative — in the real output every message must respect the character budget and reference verifiable company facts.
