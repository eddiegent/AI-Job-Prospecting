"""Job application history database.

Stores processed job applications in SQLite for duplicate detection,
status tracking, reporting, and export.
"""
from __future__ import annotations

import atexit
import csv
import hashlib
import io
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import time

try:                       # POSIX advisory locks (auto-released if a process dies)
    import fcntl as _fcntl
except ImportError:        # Windows
    _fcntl = None
    try:
        import msvcrt as _msvcrt
    except ImportError:    # pragma: no cover - neither primitive available
        _msvcrt = None
else:
    _msvcrt = None
from datetime import datetime
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

_COMPANY_STRIP = re.compile(r"\b(sas|sarl|sa|sasu|inc|ltd|gmbh|ag|corp|group|plc)\b", re.I)
_WHITESPACE = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation edges."""
    return _WHITESPACE.sub(" ", text.strip().lower()).strip(" .-_,")


def normalise_company(name: str) -> str:
    """Normalise a company name for comparison."""
    n = _normalise(name)
    n = _COMPANY_STRIP.sub("", n)
    return _WHITESPACE.sub(" ", n).strip()


def normalise_skill(skill: str) -> str:
    """Normalise a skill string for comparison.

    Unifies common aliases so that e.g. 'C#' and 'CSharp' match.
    """
    s = _normalise(skill)
    aliases = {
        "c#": "csharp", "c sharp": "csharp",
        ".net": "dotnet", "dot net": "dotnet",
        "javascript": "js", "typescript": "ts",
    }
    for old, new in aliases.items():
        s = s.replace(old, new)
    return s


def skill_overlap(skills_a: list[str], skills_b: list[str]) -> float:
    """Return the Jaccard-style overlap ratio between two skill sets (0.0–1.0)."""
    set_a = {normalise_skill(s) for s in skills_a}
    set_b = {normalise_skill(s) for s in skills_b}
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Database class
# ---------------------------------------------------------------------------

_SCHEMA_VERSION = 2

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS applications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name    TEXT NOT NULL,
    company_norm    TEXT NOT NULL,
    job_title       TEXT NOT NULL,
    job_title_norm  TEXT NOT NULL,
    location        TEXT,
    source_url      TEXT,
    domain          TEXT,
    seniority       TEXT,
    fit_level       TEXT,
    fit_pct         REAL,
    direct_count    INTEGER,
    transferable_count INTEGER,
    gap_count       INTEGER,
    output_folder   TEXT,
    detected_language TEXT,
    status          TEXT NOT NULL DEFAULT 'generated',
    source          TEXT NOT NULL DEFAULT 'offer',
    company_profile_snapshot TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_skills (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id  INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    skill           TEXT NOT NULL,
    skill_norm      TEXT NOT NULL,
    skill_type      TEXT NOT NULL CHECK(skill_type IN ('required', 'preferred'))
);

CREATE INDEX IF NOT EXISTS idx_app_company_norm ON applications(company_norm);
CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_skills_app ON job_skills(application_id);
CREATE INDEX IF NOT EXISTS idx_skills_norm ON job_skills(skill_norm);

CREATE TABLE IF NOT EXISTS company_lists (
    company_norm    TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    list_type       TEXT NOT NULL CHECK(list_type IN ('blacklist', 'whitelist')),
    reason          TEXT,
    created_at      TEXT NOT NULL
);
"""



# ---------------------------------------------------------------------------
# Cross-process write lock
# ---------------------------------------------------------------------------
#
# The history DB is designed for sequential access. To make *parallel* access
# safe too (e.g. several `record-application` processes at once), every
# JobHistoryDB holds an exclusive advisory lock on a local lockfile for its
# whole lifetime. Because each process's critical section — mirror-in, operate,
# write-back — runs fully under the lock, the whole-file write-back can no
# longer interleave or lose updates: process B can't start until A has released
# (i.e. finished syncing its rows to the target), so B reads A's result first.
#
# The lockfile lives on local disk (keyed by the canonical target path), so the
# lock is reliable even when the DB itself sits on a network/mounted filesystem
# whose own locking is unreliable. The lock is RE-ENTRANT within a process (a
# refcount, so one process opening the same DB twice never deadlocks itself) and
# EXCLUSIVE across processes. Acquisition is best-effort: if the lock primitive
# errors or the wait times out, the DB still opens (degraded to the old
# behaviour) rather than blocking the caller.

_LOCK_REGISTRY: dict[str, list] = {}          # lock_path -> [fd, refcount]
_LOCK_REGISTRY_GUARD = threading.Lock()


def _lock_path_for(target: Path) -> Path:
    key = hashlib.sha1(str(target.resolve()).encode()).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"jobhist-{key}.lock"


def _try_lock_fd(fd: int) -> bool:
    """Attempt a non-blocking exclusive lock on `fd`. True on success."""
    try:
        if _fcntl is not None:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
            return True
        if _msvcrt is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)
            return True
    except OSError:
        return False
    # No lock primitive available — proceed unlocked (best effort).
    return True


def acquire_db_lock(target: Path, timeout: float = 60.0) -> bool:
    """Acquire the process-wide / cross-process lock for `target`.

    Returns True if the lock is now held (or re-entered, or unguarded because no
    primitive exists). Returns False only if the wait timed out — the caller
    still proceeds, just without serialisation, so a stuck peer can't deadlock
    the whole tool."""
    lock_path = _lock_path_for(target)
    key = str(lock_path)
    with _LOCK_REGISTRY_GUARD:
        ent = _LOCK_REGISTRY.get(key)
        if ent is not None:                  # re-entrant within this process
            ent[1] += 1
            return True
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
        os.write(fd, b"\0")                  # ensure >=1 byte for msvcrt locking
    except OSError:
        return True                          # can't create lockfile -> unlocked
    deadline = time.time() + timeout
    while True:
        if _try_lock_fd(fd):
            with _LOCK_REGISTRY_GUARD:
                _LOCK_REGISTRY[key] = [fd, 1]
            return True
        if time.time() >= deadline:
            try:
                os.close(fd)
            except OSError:
                pass
            return False                     # timed out -> proceed unlocked
        time.sleep(0.1)


def release_db_lock(target: Path) -> None:
    """Release one reference to `target`'s lock; unlock when the last ref drops."""
    key = str(_lock_path_for(target))
    with _LOCK_REGISTRY_GUARD:
        ent = _LOCK_REGISTRY.get(key)
        if ent is None:
            return
        ent[1] -= 1
        if ent[1] > 0:
            return
        fd = ent[0]
        del _LOCK_REGISTRY[key]
    try:
        if _fcntl is not None:
            _fcntl.flock(fd, _fcntl.LOCK_UN)
        elif _msvcrt is not None:
            os.lseek(fd, 0, os.SEEK_SET)
            _msvcrt.locking(fd, _msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def compute_content_fingerprint(conn: sqlite3.Connection) -> dict:
    """Content fingerprint of the applications table — read-only.

    Hashes the sorted ``(company_norm, job_title_norm, created_at, status)``
    tuples, so the fingerprint tracks *content* and is stable across VACUUM /
    rowid churn. Used by ``cli.py doctor`` to detect when the DB has been
    silently replaced or restored across sessions, and to compare the canonical
    target against the temp working mirror. Returns row_count, max_id,
    schema_version, and a short fingerprint.
    """
    rows = conn.execute(
        "SELECT company_norm, job_title_norm, created_at, status "
        "FROM applications ORDER BY company_norm, job_title_norm, created_at, id"
    ).fetchall()
    h = hashlib.sha256()
    for r in rows:
        h.update(("|".join((r[0] or "", r[1] or "", r[2] or "", r[3] or "")) + "\n").encode("utf-8"))
    max_id = conn.execute("SELECT MAX(id) FROM applications").fetchone()[0]
    try:
        ver_row = conn.execute("SELECT version FROM schema_version").fetchone()
        schema_version = ver_row[0] if ver_row else None
    except sqlite3.Error:
        schema_version = None
    return {
        "row_count": len(rows),
        "max_id": max_id,
        "schema_version": schema_version,
        "fingerprint": h.hexdigest()[:16],
    }


class JobHistoryDB:
    """Thin wrapper around the SQLite job history database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._mirror_path: Path | None = None
        self._closed = False
        self._lock_held = False

        # Serialise the whole open->operate->write-back critical section across
        # processes so parallel runs can't interleave / lose updates / corrupt.
        self._lock_held = acquire_db_lock(self.db_path)

        # Work on a local-disk mirror to dodge SQLite "disk I/O error" /
        # corruption on networked/mounted filesystems. The mirror is keyed by
        # the canonical target path so sequential opens see the latest data;
        # every commit (and close) copies the mirror atomically back to target.
        connect_path = self.db_path
        try:
            key = hashlib.sha1(str(self.db_path.resolve()).encode()).hexdigest()[:16]
            mirror = Path(tempfile.gettempdir()) / f"jobhist-mirror-{key}.db"
            if self.db_path.exists():
                if (not mirror.exists()
                        or self.db_path.stat().st_mtime >= mirror.stat().st_mtime):
                    shutil.copy2(self.db_path, mirror)
            self._mirror_path = mirror
            connect_path = mirror
        except Exception:
            # Mirroring is best-effort; fall back to operating on the target.
            self._mirror_path = None
            connect_path = self.db_path

        self._conn = sqlite3.connect(str(connect_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        try:
            self._conn.execute("PRAGMA busy_timeout = 8000")
        except sqlite3.DatabaseError:
            pass
        self._init_schema()
        # Flush schema creation / v1->v2 upgrade to the canonical target now, so
        # callers that inspect the target file without closing still see it.
        # Writes back only at init + close (not per-commit): minimises writes to
        # the canonical file, which matters on flaky network/mounted filesystems.
        self._sync_back()
        atexit.register(self._safe_close)

    @staticmethod
    def _verify_sqlite(path: Path) -> bool:
        """Return True iff `path` is a structurally sound SQLite DB.

        Reads are done on a local-disk copy because direct reads of a
        networked/mounted file can themselves raise spurious I/O errors;
        copying off first makes the integrity check trustworthy."""
        local = Path(tempfile.gettempdir()) / f"jobhist-verify-{os.getpid()}-{id(path)}.db"
        try:
            shutil.copy2(path, local)
            con = sqlite3.connect(str(local))
            try:
                row = con.execute("PRAGMA integrity_check").fetchone()
            finally:
                con.close()
            return bool(row) and row[0] == "ok"
        except Exception:
            return False
        finally:
            try:
                local.unlink(missing_ok=True)
            except Exception:
                pass

    def _sync_back(self) -> None:
        """Copy the local mirror back onto the canonical target, verifying the
        result and retrying on failure. Never replaces a healthy target with a
        corrupt copy: some mounts mangle SQLite files on write, so each attempt
        is integrity-checked off-mount before AND after the swap, and if no
        attempt yields a clean file the existing target is left untouched (the
        mirror remains the durable working copy)."""
        mirror = getattr(self, "_mirror_path", None)
        if not mirror:
            return
        for attempt in range(4):
            tmp = self.db_path.with_name(
                self.db_path.name + f".sync.{os.getpid()}.{attempt}.tmp"
            )
            try:
                shutil.copy2(mirror, tmp)
                try:
                    with open(tmp, "rb") as fh:
                        os.fsync(fh.fileno())
                except OSError:
                    pass
                if not self._verify_sqlite(tmp):
                    tmp.unlink(missing_ok=True)
                    time.sleep(0.2)
                    continue
                os.replace(tmp, self.db_path)
                if self._verify_sqlite(self.db_path):
                    return
            except Exception:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass
            time.sleep(0.2)
        # All attempts failed — leave the prior target in place (don't corrupt
        # good data). The mirror at self._mirror_path holds the latest state.

    def _safe_close(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # -- lifecycle -----------------------------------------------------------

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(_CREATE_SQL)
        row = cur.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        current = row["v"]
        if current is None:
            cur.execute("INSERT INTO schema_version(version) VALUES(?)", (_SCHEMA_VERSION,))
        elif current < _SCHEMA_VERSION:
            self._upgrade_schema(cur, from_version=current)
            cur.execute("UPDATE schema_version SET version = ?", (_SCHEMA_VERSION,))
        self._conn.commit()

    def _upgrade_schema(self, cur: sqlite3.Cursor, *, from_version: int) -> None:
        """Incremental schema migrations. Each clause takes the DB from vN to vN+1."""
        existing_cols = {r["name"] for r in cur.execute("PRAGMA table_info(applications)").fetchall()}
        if from_version < 2:
            # v1 -> v2: add source + company_profile_snapshot columns for the
            # cold-prospect flow. Existing rows get source='offer' via the
            # DEFAULT clause; snapshot stays NULL for offer-flow rows.
            if "source" not in existing_cols:
                cur.execute(
                    "ALTER TABLE applications ADD COLUMN source TEXT NOT NULL DEFAULT 'offer'"
                )
            if "company_profile_snapshot" not in existing_cols:
                cur.execute(
                    "ALTER TABLE applications ADD COLUMN company_profile_snapshot TEXT"
                )

    def close(self) -> None:
        if getattr(self, "_closed", False):
            return
        try:
            self._sync_back()
        finally:
            self._conn.close()
            self._closed = True
            if getattr(self, "_lock_held", False):
                release_db_lock(self.db_path)
                self._lock_held = False

    # -- insert --------------------------------------------------------------

    def add_application(
        self,
        *,
        company_name: str,
        job_title: str,
        location: str | None = None,
        source_url: str | None = None,
        domain: str | None = None,
        seniority: str | None = None,
        fit_level: str | None = None,
        fit_pct: float | None = None,
        direct_count: int | None = None,
        transferable_count: int | None = None,
        gap_count: int | None = None,
        output_folder: str | None = None,
        detected_language: str | None = None,
        status: str = "generated",
        source: str = "offer",
        company_profile_snapshot: str | None = None,
        created_at: str | None = None,
        required_skills: list[str] | None = None,
        preferred_skills: list[str] | None = None,
    ) -> int:
        if source not in ("offer", "cold"):
            raise ValueError(f"source must be 'offer' or 'cold', got {source!r}")
        now = created_at or datetime.now().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO applications
               (company_name, company_norm, job_title, job_title_norm,
                location, source_url, domain, seniority,
                fit_level, fit_pct, direct_count, transferable_count, gap_count,
                output_folder, detected_language, status,
                source, company_profile_snapshot,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                company_name, normalise_company(company_name),
                job_title, _normalise(job_title),
                location, source_url, domain, seniority,
                fit_level, fit_pct, direct_count, transferable_count, gap_count,
                output_folder, detected_language, status,
                source, company_profile_snapshot,
                now, now,
            ),
        )
        app_id = cur.lastrowid
        for skill in (required_skills or []):
            cur.execute(
                "INSERT INTO job_skills(application_id, skill, skill_norm, skill_type) VALUES(?,?,?,?)",
                (app_id, skill, normalise_skill(skill), "required"),
            )
        for skill in (preferred_skills or []):
            cur.execute(
                "INSERT INTO job_skills(application_id, skill, skill_norm, skill_type) VALUES(?,?,?,?)",
                (app_id, skill, normalise_skill(skill), "preferred"),
            )
        self._conn.commit()
        return app_id

    # -- duplicate detection -------------------------------------------------

    def find_duplicates(
        self,
        *,
        company_name: str,
        job_title: str,
        source_url: str | None = None,
        required_skills: list[str] | None = None,
        skill_threshold: float = 0.80,
    ) -> list[dict[str, Any]]:
        """Find potential duplicate applications.

        Returns a list of matches with a 'match_reason' field explaining why.
        Ordered by strongest match first.
        """
        results: list[dict[str, Any]] = []
        seen_ids: set[int] = set()

        # Dropped applications are excluded from all duplicate checks — once
        # the user has explicitly walked away from a role, it should not
        # block or warn on a new application to the same company/title/URL.

        # 1. Exact URL match
        if source_url:
            rows = self._conn.execute(
                "SELECT * FROM applications WHERE source_url = ? AND source_url IS NOT NULL AND status != 'dropped'",
                (source_url,),
            ).fetchall()
            for row in rows:
                seen_ids.add(row["id"])
                results.append({**dict(row), "match_reason": "exact URL match"})

        # 2. Company + title match
        comp_norm = normalise_company(company_name)
        title_norm = _normalise(job_title)
        rows = self._conn.execute(
            "SELECT * FROM applications WHERE company_norm = ? AND job_title_norm = ? AND status != 'dropped'",
            (comp_norm, title_norm),
        ).fetchall()
        for row in rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                results.append({**dict(row), "match_reason": "same company + job title"})

        # 3. Company match + skill overlap
        if required_skills:
            rows = self._conn.execute(
                "SELECT * FROM applications WHERE company_norm = ? AND status != 'dropped'",
                (comp_norm,),
            ).fetchall()
            for row in rows:
                if row["id"] in seen_ids:
                    continue
                existing_skills = [
                    r["skill"]
                    for r in self._conn.execute(
                        "SELECT skill FROM job_skills WHERE application_id = ? AND skill_type = 'required'",
                        (row["id"],),
                    ).fetchall()
                ]
                overlap = skill_overlap(required_skills, existing_skills)
                if overlap >= skill_threshold:
                    seen_ids.add(row["id"])
                    results.append({
                        **dict(row),
                        "match_reason": f"same company, {overlap:.0%} skill overlap",
                    })

        return results

    def find_same_company(self, company_name: str) -> list[dict[str, Any]]:
        """Find all previous applications to the same company (for context surfacing).

        Tries exact normalised match first, then falls back to partial LIKE match
        so that e.g. 'Attineos' finds 'Attineos Applications'.
        """
        comp_norm = normalise_company(company_name)
        rows = self._conn.execute(
            "SELECT * FROM applications WHERE company_norm = ? ORDER BY created_at DESC",
            (comp_norm,),
        ).fetchall()
        if not rows:
            rows = self._conn.execute(
                "SELECT * FROM applications WHERE company_norm LIKE ? ORDER BY created_at DESC",
                (f"%{comp_norm}%",),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- status updates ------------------------------------------------------

    def update_status(self, app_id: int, status: str) -> bool:
        valid = ("generated", "applied", "rejected", "interview", "offer", "dropped")
        if status not in valid:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid)}")
        cur = self._conn.execute(
            "UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), app_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_company(self, app_id: int, new_name: str) -> bool:
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Company name must be non-empty")
        cur = self._conn.execute(
            "UPDATE applications SET company_name = ?, company_norm = ?, updated_at = ? WHERE id = ?",
            (new_name, _normalise(new_name), datetime.now().isoformat(), app_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_output_folder(self, app_id: int, new_path: str) -> bool:
        new_path = new_path.strip()
        if not new_path:
            raise ValueError("Output folder must be non-empty")
        cur = self._conn.execute(
            "UPDATE applications SET output_folder = ?, updated_at = ? WHERE id = ?",
            (new_path, datetime.now().isoformat(), app_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # -- queries -------------------------------------------------------------

    def get_application(self, app_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
        return dict(row) if row else None

    def list_applications(
        self,
        *,
        status: str | None = None,
        company: str | None = None,
        limit: int = 50,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM applications WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if company:
            query += " AND company_norm = ?"
            params.append(normalise_company(company))
        if since:
            query += " AND created_at >= ?"
            params.append(since)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(query, params).fetchall()]

    def get_skills(self, app_id: int) -> list[dict[str, str]]:
        rows = self._conn.execute(
            "SELECT skill, skill_type FROM job_skills WHERE application_id = ?",
            (app_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- reporting -----------------------------------------------------------

    def stats_by_fit_level(self, since: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE created_at >= ?" if since else ""
        params = (since,) if since else ()
        rows = self._conn.execute(
            f"SELECT fit_level, COUNT(*) as count FROM applications {where} GROUP BY fit_level ORDER BY count DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def stats_by_status(self, since: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE created_at >= ?" if since else ""
        params = (since,) if since else ()
        rows = self._conn.execute(
            f"SELECT status, COUNT(*) as count FROM applications {where} GROUP BY status ORDER BY count DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def stats_by_domain(self, since: str | None = None) -> list[dict[str, Any]]:
        base_where = "WHERE domain IS NOT NULL"
        params: tuple = ()
        if since:
            base_where += " AND created_at >= ?"
            params = (since,)
        rows = self._conn.execute(
            f"SELECT domain, COUNT(*) as count FROM applications {base_where} GROUP BY domain ORDER BY count DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def stats_by_company(self, since: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE created_at >= ?" if since else ""
        params = (since,) if since else ()
        rows = self._conn.execute(
            f"SELECT company_name, COUNT(*) as count FROM applications {where} GROUP BY company_norm ORDER BY count DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def top_skill_gaps(self, limit: int = 15) -> list[dict[str, Any]]:
        """Find skills that most frequently appear as required but are gaps."""
        rows = self._conn.execute(
            """SELECT js.skill, COUNT(*) as gap_count
               FROM job_skills js
               JOIN applications a ON a.id = js.application_id
               WHERE js.skill_type = 'required'
               GROUP BY js.skill_norm
               HAVING gap_count > 0
               ORDER BY gap_count DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def skill_gap_trends(self, limit: int = 10, since: str | None = None) -> list[dict[str, Any]]:
        """Find required skills from gap matches across all applications.

        Looks at match_analysis data via the job_skills table combined with
        application fit data to identify recurring gaps.
        """
        since_clause = "AND a.created_at >= ?" if since else ""
        params: tuple = (limit,) if not since else (since, limit)
        rows = self._conn.execute(
            f"""SELECT js.skill, COUNT(DISTINCT js.application_id) as appearances,
                      ROUND(AVG(a.fit_pct), 1) as avg_fit_pct
               FROM job_skills js
               JOIN applications a ON a.id = js.application_id
               WHERE js.skill_type = 'required' {since_clause}
               GROUP BY js.skill_norm
               ORDER BY appearances DESC
               LIMIT ?""",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    # -- blacklist / whitelist -----------------------------------------------

    def add_company_to_list(
        self, company_name: str, list_type: str, reason: str | None = None
    ) -> None:
        if list_type not in ("blacklist", "whitelist"):
            raise ValueError("list_type must be 'blacklist' or 'whitelist'")
        self._conn.execute(
            """INSERT OR REPLACE INTO company_lists(company_norm, company_name, list_type, reason, created_at)
               VALUES(?, ?, ?, ?, ?)""",
            (normalise_company(company_name), company_name, list_type, reason, datetime.now().isoformat()),
        )
        self._conn.commit()

    def remove_company_from_list(self, company_name: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM company_lists WHERE company_norm = ?",
            (normalise_company(company_name),),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def check_company_list(self, company_name: str) -> dict[str, Any] | None:
        """Check if a company is on the blacklist or whitelist.

        Returns the entry dict if found, None otherwise.
        """
        row = self._conn.execute(
            "SELECT * FROM company_lists WHERE company_norm = ?",
            (normalise_company(company_name),),
        ).fetchone()
        return dict(row) if row else None

    def get_company_list(self, list_type: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM company_lists WHERE list_type = ? ORDER BY company_name",
            (list_type,),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- export --------------------------------------------------------------

    def export_csv(self, output_path: str | Path | None = None) -> str:
        """Export all applications to CSV. Returns CSV string, optionally writes to file."""
        rows = self._conn.execute(
            "SELECT * FROM applications ORDER BY created_at DESC"
        ).fetchall()
        if not rows:
            return ""
        columns = rows[0].keys()
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))
        content = buf.getvalue()
        if output_path:
            Path(output_path).write_text(content, encoding="utf-8")
        return content

    def total_count(self, since: str | None = None) -> int:
        if since:
            row = self._conn.execute("SELECT COUNT(*) as c FROM applications WHERE created_at >= ?", (since,)).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) as c FROM applications").fetchone()
        return row["c"]
