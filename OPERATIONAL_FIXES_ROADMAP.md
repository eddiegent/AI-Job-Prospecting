# Operational Fixes Roadmap

Three-item plan to remove the failure modes that hit during the Speechify run on 2026-05-06. Read this before picking up any of the items below — context matters for scope decisions.

## Context

**What prompted the roadmap.** The Speechify *Senior Software Engineer, Windows/Desktop Applications* run on 2026-05-06 produced a clean pack (fit 61 % medium, application #51 in DB), but three friction points surfaced along the way:

1. **WebFetch returned 403 on `lesjeudis.com`.** That aggregator isn't in `config/settings.default.yaml § aggregators.known_platforms`, and there's no preflight probe before WebFetch — so the 403 cost a round-trip and forced a manual fallback (the user had to provide the offer text from a local file). Lesjeudis is a well-known French aggregator; the fact that it isn't on the platform list is a coverage gap.

2. **A false-direct match almost shipped.** `match_analysis.matches[10]` had `"OOP, design patterns, data structures, algorithms"` marked `match_type: "direct"` — none of those tokens are literal in the fact base. The deterministic grounding check (`scripts/check_match_grounding.py`, shipped in tailor 1.8.0) caught it because "OOP" is tech-shaped (3-letter all-caps acronym). The `match_analysis.md` prompt has a "No false directs" rule but doesn't explicitly call out **compound concept-list phrases** as a class — they read like soft-skill prose, but the embedded acronyms are tech-shaped enough to trip the check.

3. **`db.add_application()` was called with wrong kwargs.** I composed `add_application(job_url=..., job_skills=..., source='offer')` from intuition. The real signature uses `source_url=`, `required_skills=`, `preferred_skills=` (and `source` *is* a valid kwarg, defaulting to `'offer'`). The correct invocation was already documented at `references/commands.md § Record Application`. The skill memory was updated post-incident (`feedback_check_schema_first.md` broadened from "SQL columns" to "Python signatures, JSON/YAML keys, API payloads" with both incidents recorded), but the deeper fix is structural: Step 10 is the **last DB-touching step still doing inline Python** instead of going through a CLI wrapper. Every other DB-touching step (`check-duplicate`, `regenerate-outputs`, `rename-application`) was already a wrapper for exactly this reason.

## Rollout order

Status checkboxes track progress. Each item is one commit so any can be reverted independently.

- [x] **#1. `record-application` CLI wrapper** — ~1.5 h, high leverage
- [x] **#2. Aggregator URL probe + extend `known_platforms`** — ~30 min, medium leverage
- [x] **#3. Compound-phrase rule in match-analysis prompt** — ~15 min, belt-and-braces

Total budget ~2.25 h. Items are independent; any session order works. Suggested cadence:

- **Session A**: #1 alone (the highest-leverage item; benefits both offer + cold flows).
- **Session B**: #2 + #3 together (both touch only configuration / prompt files; ~45 min total).

---

## #1 — `record-application` CLI wrapper

**Goal.** Eliminate the entire class of "composed-from-memory" failures for the Step 10 history record by collapsing the inline Python block into a single CLI invocation, matching the existing `check-duplicate` / `regenerate-outputs` / `rename-application` pattern.

**Changes.**

- `scripts/cli.py` — new subcommand:
  ```
  record-application <output-dir-or-id> [--url URL] [--source {offer,cold}] [--dry-run]
  ```
- Pipeline:
  1. Resolve the argument: integer → DB lookup, path → use as-is.
  2. Read `_prep/job_offer_analysis.json` (offer flow) or `_prep/selected_role.json` + `_prep/company_profile.json` (cold flow). Detect flow from folder name prefix (`cold-` → cold, else offer) — `--source` overrides.
  3. Read `_prep/match_analysis.json` if present (offer flow only).
  4. Derive `fit_level` from folder-name prefix using the existing `('very_good', 'good', 'medium')` scan; fall back to `'low'`.
  5. Build the kwargs dict: `company_name`, `job_title`, `location`, `source_url` (from JSON, override with `--url`), `domain`, `seniority`, `fit_level`, `fit_pct`, `direct_count`, `transferable_count`, `gap_count`, `output_folder`, `detected_language`, `required_skills`, `preferred_skills`, `source`. Cold flow: `fit_*` stay `None`; `company_profile_snapshot` populated from the curated subset (mirror the existing cold-flow Step 10 block).
  6. Call `db.add_application(**kwargs)` — single point where the kwargs are constructed; no inline composition elsewhere.
  7. Print `Recorded application #<id>`.
- `references/commands.md § Record Application` — replace the ~25-line inline Python block with one line:
  ```bash
  cd "$SKILL_BASE" && python scripts/cli.py --db "$PROJECT_ROOT/resources/job_history.db" \
    record-application "$OUTPUT_DIR" --url "<url>"
  ```
- `SKILL.md § Step 10` — drop the inline block, point to the new command. Same change in `job-cold-prospect/SKILL.md § Step 10`.
- `tests/test_cli_record_application.py` — new file. Cover: offer-flow happy path; cold-flow happy path (verify `source='cold'`, `fit_*` NULL, `company_profile_snapshot` present); `--url` override; `--dry-run` (prints the kwargs JSON, no DB write); missing `_prep/` files surface a clean error and exit 2; integer-id resolution.

**Edge cases.**
- A folder created before this commit might lack `source_url` in its `job_offer_analysis.json` — `--url` is the escape hatch.
- Schema v2 `applications.source` validation is already at the DB layer (rejects unknown values) — the CLI just passes it through.
- The cold flow's `selected_role.json` doesn't carry `required_skills` / `preferred_skills` — for cold rows those stay empty arrays, matching today's behaviour.

**Effort.** 1.5 h including the cold-flow path, tests, and both SKILL.md updates.

---

## #2 — Aggregator URL probe + extend `known_platforms`

**Goal.** Fail fast on aggregators that 403 WebFetch instead of letting the WebFetch round-trip burn before falling back. Also broaden the platform-detection coverage so the "is this a real client or a posting platform?" prompt fires on more French boards.

**Changes.**

- `config/settings.default.yaml § aggregators.known_platforms` — add (alphabetical):
  ```yaml
  - lesjeudis
  - RegionsJob
  - Cadremploi
  - Choose your Boss
  - Talent.io
  ```
  Spot-check the spelling each platform actually uses on its own postings before committing — `matched_aggregator()` is normalised but the canonical form should match what users will see in the wild.

- `SKILL.md § Step 3` — before WebFetch, add a one-line probe:
  ```python
  import urllib.request
  req = urllib.request.Request(URL, method='HEAD', headers={'User-Agent': 'Mozilla/5.0'})
  try:
      urllib.request.urlopen(req, timeout=5)
  except urllib.error.HTTPError as e:
      blocked = e.code in (401, 403, 429, 451)
  ```
  If `blocked`, skip WebFetch and immediately surface: *"`<host>` blocks automated requests. Paste the offer text below, or share a path to a local file."*

- `references/commands.md` — add a `## URL Probe` section documenting the snippet for reuse.

**Edge cases.**
- HEAD probe rate limiting — 5 s timeout is conservative; the probe runs once per posting.
- Sites that allow WebFetch but block HEAD specifically — false-positive risk. If the user reports the probe blocked a fetchable site, the fix is `--skip-probe` (don't add this flag preemptively; wait for the first real false-positive).
- The probe must respect the user's network conditions; behind some corporate proxies any HTTP probe will fail. The skill's existing fallback (paste / local file) is a clean degradation either way, so a probe failure simply collapses to the same fallback as a 403.

**Effort.** 30 min.

---

## #3 — Compound-phrase rule in match-analysis prompt

**Goal.** Pre-empt the false-direct class that today's grounding check caught (compound concept-list phrases like `"OOP, design patterns, data structures, algorithms"` marked direct because the prose reads like soft-skill but contains a tech-shaped acronym).

**Changes.**

- `prompts/match_analysis.md` — extend the existing "No false directs" / "Direct ≠ partial" rules with one bullet:

  > **Compound concept-list phrases.** When a requirement is a comma-list of multiple distinct concept tokens (e.g. `"OOP, design patterns, data structures, algorithms"`, `"reliability, performance, scalability, maintainability"`), apply the same all-or-nothing rule as `"C# / Kubernetes"`: every token must have a literal counterpart (or close synonym) in `cv_fact_base.{technologies, skills, methodologies}` or in `experience[*].details`. Even one ungrounded token in the list demotes the whole row to `transferable` with a `notes` explanation. The check_match_grounding script will block the row if any token is tech-shaped (acronyms, CamelCase, dot/hash/slash/plus); soft-skill tokens become warnings. Don't rely on the warning-vs-error split — the prompt should produce honest classifications either way.

- No code change. The grounding check (`scripts/check_match_grounding.py`) is the runtime mechanism and already covers this case for tech-shaped tokens; this rule is the prompt-side belt-and-braces.

- `tests/` — no test change. The existing `test_match_grounding.py::test_compound_requirement_partial_grounding_flags_only_ungrounded` already pins the runtime behaviour.

**Effort.** 15 min.

---

## Out of scope (for now)

- **Auto-pasting from the clipboard when WebFetch is blocked.** Tempting, but introduces a new dependency surface (pyperclip, OS-specific quirks). The current "paste below or share a file path" UX is fine; users can paste in 2 seconds.
- **A `record-application` Python API surface separate from the CLI.** The DB layer (`db.add_application`) already *is* the Python API. Adding a second wrapper adds indirection without removing failure modes.
- **An end-of-run pipeline integrity check** (verify all expected `_prep/` artefacts exist, schema-validate every JSON, confirm DB row was inserted). Worth thinking about but bigger than this roadmap — the schema validations are inline at each step, and the missing piece would be a final post-Step-10 sanity sweep. Defer.
- **Automatic prompt for unknown aggregators**: when `matched_aggregator()` returns nothing AND the WebFetch URL host matches a `*.fr` job-board pattern (heuristic), prompt the user to add the platform. Speculative — wait until there's a second uncovered aggregator before generalising.
