# CV Addendum

This file is an **optional** per-run enrichment layer on top of your
`MASTER_CV.docx`. Anything you put here is merged into the in-memory fact
base the skill uses to tailor each application — it never mutates the
cached `cv_fact_base.json`, and it never leaks into the extractor's
ground truth.

Use it for:

- experience bullets that belong on an existing role but that you left
  out of the master CV for length reasons,
- hidden skills the CV doesn't showcase but you want the tailor to know
  about (e.g. a language you once shipped production code in),
- off-CV facts you want the skill to remember across every application.

Delete any section you don't need. All three are optional.

---

## Additional experience entries

Each `###` subsection targets one existing role in your master CV. The
heading must match the role's **company name** followed by a dash and
the **dates** as they appear in the CV. The skill matches these
case-insensitively, and normalises em-dash / en-dash / ASCII hyphen, so
`Helios Analytics — Mar 2022 – Present` and `Helios Analytics - Mar 2022 - Present`
are equivalent.

Bullets under the heading are appended to that role's `details` array
when the tailor step builds its in-memory fact base.

### Helios Analytics — Mar 2022 – Present

- Example: led a 6-month effort to migrate the billing service from a
  monolith to three FastAPI services.
- Example: introduced contract testing across all public APIs.

### Northbridge Software — Aug 2019 – Feb 2022

- Example: owned the on-call runbook for the order-management service.

---

## Hidden skills

Flat bullet list. Each item is something you can talk about in an
interview but that isn't visible in the master CV (yet). The tailor step
is allowed to surface these **only** when the job offer explicitly asks
for the skill and you have real evidence to back it up.

- Example: Rust — shipped a production CLI for internal release tooling.
- Example: gRPC — built the internal service-to-service layer at a
  previous role, not listed on the CV because the product was
  never publicly announced.

---

## Off-CV facts to remember

Flat bullet list. Durable facts about your career or preferences that
you want the skill to know across every run, without cluttering the
master CV. These are passed to the letter and LinkedIn steps as
supporting context.

- Example: I am open to hybrid roles within 1 h 30 of Lyon, but not to
  full remote unless the team is explicitly remote-first.
- Example: I speak English fluently in a professional context even
  though the CV says "C1".
