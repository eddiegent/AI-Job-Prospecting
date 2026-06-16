"""Concurrency / locking regression tests for the job-history DB.

The cross-process write lock makes the whole-file mirror write-back safe under
parallel access by serialising each process's open->operate->write-back section.
We test the lock's *mechanism* (mutual exclusion + re-entrancy) rather than the
data-race *symptom* (a wrong row count), because the symptom is non-deterministic
— an unlocked run sometimes still lands the right number of rows by luck, so
asserting on it would be a flaky, toothless test. Mutual exclusion is
deterministic: with a hold far larger than scheduling jitter, locked critical
sections never overlap, unlocked ones always do.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

from scripts.job_history_db import (
    _LOCK_REGISTRY,
    _lock_path_for,
    acquire_db_lock,
    release_db_lock,
    JobHistoryDB,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent
HOLD = 0.25  # seconds each worker holds the DB — >> scheduling jitter


def test_lock_is_reentrant_within_process(tmp_path):
    target = tmp_path / "hist.db"
    key = str(_lock_path_for(target))
    assert acquire_db_lock(target) is True
    assert acquire_db_lock(target) is True          # re-entrant: must not block
    assert _LOCK_REGISTRY[key][1] == 2
    release_db_lock(target)
    assert _LOCK_REGISTRY[key][1] == 1
    release_db_lock(target)
    assert key not in _LOCK_REGISTRY                 # fully released, fd closed


# argv: db_path, n, skill_root, hold_seconds, interval_out, disable_lock("0"/"1")
_WORKER = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, sys.argv[3])
    import scripts.job_history_db as J
    if sys.argv[6] == "1":                  # control: disable the lock
        J.acquire_db_lock = lambda *a, **k: False
        J.release_db_lock = lambda *a, **k: None
    db = J.JobHistoryDB(sys.argv[1])        # lock acquired here
    start = time.time()
    time.sleep(float(sys.argv[4]))          # hold the critical section
    db.add_application(company_name="Co" + sys.argv[2], job_title="J",
                       fit_pct=1.0, fit_level="good", direct_count=0,
                       transferable_count=0, gap_count=0, required_skills=["s"],
                       output_folder="/tmp", detected_language="fr")
    end = time.time()
    db.close()                              # lock released here
    open(sys.argv[5], "w").write(f"{start} {end}")
    """
)


def _run_workers(tmp_path, *, disable_lock):
    db_path = tmp_path / "hist.db"
    JobHistoryDB(str(db_path)).close()              # create schema first
    worker = tmp_path / "worker.py"
    worker.write_text(_WORKER)
    n = 6
    procs = []
    for i in range(n):
        iv = tmp_path / f"iv_{i}.txt"
        procs.append(subprocess.Popen([
            sys.executable, str(worker), str(db_path), str(i),
            str(SKILL_ROOT), str(HOLD), str(iv), "1" if disable_lock else "0",
        ]))
    for p in procs:
        assert p.wait(timeout=90) == 0
    intervals = sorted(
        tuple(float(x) for x in (tmp_path / f"iv_{i}.txt").read_text().split())
        for i in range(n)
    )
    # count pairs of critical sections that overlap in time
    overlaps = sum(
        1
        for a in range(len(intervals))
        for b in range(a + 1, len(intervals))
        if intervals[a][1] > intervals[b][0] + 0.01
        and intervals[b][1] > intervals[a][0] + 0.01
    )
    return db_path, n, overlaps


def test_parallel_critical_sections_are_serialised(tmp_path):
    db_path, n, overlaps = _run_workers(tmp_path, disable_lock=False)
    assert overlaps == 0, f"lock failed: {overlaps} overlapping critical sections"
    con = sqlite3.connect(str(db_path))
    try:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM applications").fetchone()[0] == n
    finally:
        con.close()


def test_overlap_detector_has_teeth(tmp_path):
    # Sanity that the serialisation test above is not vacuous: with the lock
    # disabled the same workers DO overlap, so the assertion would fire.
    _db, _n, overlaps = _run_workers(tmp_path, disable_lock=True)
    assert overlaps > 0
