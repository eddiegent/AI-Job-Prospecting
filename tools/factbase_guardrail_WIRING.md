# Wiring the fact-base consistency guardrail into the skill

> **✅ APPLIED.** This wiring is now live in the skill — kept as a record of what was
> done and why. The canonical checker is
> `.claude/skills/job-application-tailor/scripts/factbase_consistency.py`; the
> repo-root `tools/factbase_consistency.py` is a thin re-export shim. The three edits
> below (verify_fact_base, common.save_cv_fact_base, preflight) plus a pre-commit hook
> are in place, and `tests/test_factbase_consistency.py` guards them.

To make the stale-cache shortcut *impossible* (not just discouraged), these three small
edits were applied to the skill code under
`.claude/skills/job-application-tailor/scripts/`.

First, move (or copy) the checker next to the other scripts so it's importable:

```bash
cp tools/factbase_consistency.py .claude/skills/job-application-tailor/scripts/factbase_consistency.py
```

---

## 1. `verify_fact_base.py` — make metric drift a blocking error

This is the highest-value edit: `preflight` already calls `verify_fact_base.py` on the
cache-hit path, so plugging the check here means a stale cached fact base is
automatically downgraded to `cache_stale` (forcing re-extraction) with **no preflight
change needed**.

In `verify()`, after the technologies/methodologies loop, add metric-drift detection:

```python
# at top of file
from factbase_consistency import find_metric_drift

# inside verify(), after the skills loop, before `return errors, warnings`:
import json as _json
fact_base = _json.loads(fact_base_path.read_text(encoding="utf-8"))
for token in find_metric_drift(cv_text, fact_base):
    errors.append(f"[metric] '{token}' in fact base but not in CV — stale/fabricated figure")
```

(`cv_text` and `fact_base_path` are already in scope.) Metric drift now joins
fabricated tech as an exit-1 error.

## 2. `common.py` — refuse to bless a stale fact base

`save_cv_fact_base()` writes `.cv_hash`. Guard it so refreshing the hash with a
fact base that doesn't match the CV raises instead of silently succeeding — this is
exactly the operation that caused the incident.

```python
def save_cv_fact_base(cv_path: Path, prep_dir: Path) -> None:
    """Save cv_fact_base.json and .cv_hash next to the CV, and copy to prep_dir."""
    import shutil
    from factbase_consistency import check  # local import; standalone module

    src = prep_dir / "cv_fact_base.json"
    if src.exists():
        errors, _ = check(cv_path, src)          # metric-drift gate
        if errors:
            raise RuntimeError(
                "Refusing to cache a fact base that is inconsistent with the CV:\n  "
                + "\n  ".join(errors)
                + "\nRe-extract the fact base instead of refreshing the hash."
            )
    resources_dir = cv_path.parent
    hash_file = resources_dir / ".cv_hash"
    ensure_dir(resources_dir)
    hash_file.write_text(file_hash(cv_path), encoding="utf-8")
    dst = resources_dir / "cv_fact_base.json"
    if src.exists() and src != dst:
        shutil.copy2(str(src), str(dst))
```

## 3. (Optional, defense-in-depth) `preflight.py` — metric check on the cache-hit path

If you do edit #1, `preflight` already benefits. If you prefer an explicit check, in
`main()` where `cv_cache_is_valid(master_cv)` is true, after `_verify_fact_base_cached`,
also run:

```python
from factbase_consistency import check as _fb_check
errs, _ = _fb_check(master_cv, fact_base_path)
if errs:
    ok = False
    state["fact_base_verify_message"] = (verify_msg + "\n" + "\n".join(errs)).strip()
if not ok:
    state["status"] = "cache_stale"
```

---

## Verify the wiring

```bash
# should FAIL (exit 1) on a drifted fact base, PASS on a fresh one
python tools/factbase_consistency.py resources/MASTER_CV.docx resources/cv_fact_base.json --check-hash
```

## Optional: pre-commit hook

Add to `.githooks/pre-commit` so a stale fact base can't be committed:

```bash
python tools/factbase_consistency.py resources/MASTER_CV.docx resources/cv_fact_base.json --check-hash || {
  echo "cv_fact_base.json is out of sync with MASTER_CV.docx — re-extract it."; exit 1; }
```
