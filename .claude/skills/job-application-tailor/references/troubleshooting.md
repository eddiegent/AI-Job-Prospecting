# Troubleshooting

Read the section that matches the problem. None of this is needed on a normal run.

## History database errors (`disk I/O error`, `database disk image is malformed`)

`job_history.db` is SQLite. If it doesn't exist it is created automatically on
first run. If it is corrupted — common when the DB lives on a network/mounted
filesystem — **do NOT just delete and re-run**: `backfill_history.py` only
reimports applications that still have an output folder, so any history whose
folder was since cleaned would be lost silently.

**Salvage first:**

1. Copy the DB to local disk.
2. Recover surviving rows one at a time by rowid into a fresh DB (a bulk
   `SELECT *` aborts on the first bad page, but row-by-row reads skip only the
   damaged rows).
3. Re-record today's runs from their output folders
   (`cli.py record-application <folder>`).

Delete-and-backfill is a last resort, only when no rows are recoverable.

### Why corruption is rare now (network/mounted filesystems)

SQLite's file locking and rollback journals are unreliable on NFS, SMB/CIFS, 9p
and many container/VM mounts. `scripts/job_history_db.py` handles this so
callers don't have to:

- **Local mirror.** Every `JobHistoryDB` opens a local-disk copy (keyed by the
  canonical target path, under the system temp dir) and does all SQL there. The
  canonical file is touched only at open and close.
- **Verified, retrying write-back.** Each write-back is integrity-checked
  off-mount before and after the swap and retried; a copy that fails to verify
  is discarded, so a healthy target is never replaced by a corrupt one. If no
  attempt yields a clean file the prior target is left intact and the local
  mirror remains the durable copy.
- **Cross-process lock.** Each instance holds an exclusive advisory lock
  (`fcntl` on POSIX, `msvcrt` on Windows — auto-released if the process dies) on
  a local lockfile for its whole lifetime, so open → operate → write-back is
  serialised across processes. The lock is re-entrant within a process and
  fail-safe (if the primitive errors or a 60 s wait times out, the DB still
  opens, degraded, rather than blocking the tool).

**Scope.** This guarantees correctness for multiple processes on a single
machine. It does not coordinate writers on different machines against one
networked DB file — don't run the skill against a shared `job_history.db` from
several hosts at once. Covered by `tests/test_db_concurrency.py`.

## PDF not produced

PDF generation does NOT require Microsoft Word. `scripts/pdf_pipeline.py` tries
three converters in order and stops at the first that works: `docx2pdf` (needs
Word, Windows/Mac) → LibreOffice (`soffice` headless, anywhere it's on PATH) →
`pandoc` (needs a LaTeX engine). Don't pass `--skip-pdf` assuming "no Word = no
PDF". Only if none of the three is installed does the PDF step skip (with an
actionable message); the DOCX is always produced. In a bare environment install
LibreOffice (`apt install libreoffice`).

## DOCX generation fails

Run `cli.py regenerate-outputs "$OUTPUT_DIR" --check` — it lists which `_prep/`
inputs are missing. Re-run the step that produces the missing file, then build
again.

## Subagent reports "Write permission denied" for `output/**/_prep/*.json`

The project's tracked `.claude/settings.json` pre-approves `Edit(output/**)` so
subagents can write into `_prep/`. It must be an `Edit()` rule: Claude Code does
not match `Write()` permission rules, and `Edit()` rules cover the Write tool too.

1. Confirm the allow rule is still present in `.claude/settings.json`.
2. If a subagent returned the generated JSON in its final message instead of
   saving it, save it yourself from the main context and continue — don't
   re-run the subagent.

## Fact base verification fails

See `job-prep-cv/SKILL.md` Step 2.5. In short: remove a fabricated
technology/methodology; for a `[metric]` failure re-extract the figure from the
current CV. Never refresh `.cv_hash` by hand — `save-cv-cache` refuses while the
fact base disagrees with the CV.
