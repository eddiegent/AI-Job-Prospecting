"""Job application history database.

Stores processed job applications in SQLite for duplicate detection,
status tracking, reporting, and export.
"""
from __future__ import annotations

import csv
import io
import re
import sqlite3
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

_SCHEMA_VERSION = 1

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


class JobHistoryDB:
    """Thin wrapper around the SQLite job history database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    # -- lifecycle -----------------------------------------------------------

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(_CREATE_SQL)
        row = cur.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        if row["v"] is None:
            cur.execute("INSERT INTO schema_version(version) VALUES(?)", (_SCHEMA_VERSION,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

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
        created_at: str | None = None,
        required_skills: list[str] | None = None,
        preferred_skills: list[str] | None = None,
    ) -> int:
        now = created_at or datetime.now().isoformat()
        cur = self._conn.cursor()
        cur.execute(
            """INSERT INTO applications
               (company_name, company_norm, job_title, job_title_norm,
                location, source_url, domain, seniority,
                fit_level, fit_pct, direct_count, transferable_count, gap_count,
                output_folder, detected_language, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                company_name, normalise_company(company_name),
                job_title, _normalise(job_title),
                location, source_url, domain, seniority,
                fit_level, fit_pct, direct_count, transferable_count, gap_count,
                output_folder, detected_language, status, now, now,
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

        # 1. Exact URL match
        if source_url:
            rows = self._conn.execute(
                "SELECT * FROM applications WHERE source_url = ? AND source_url IS NOT NULL",
                (source_url,),
            ).fetchall()
            for row in rows:
                seen_ids.add(row["id"])
                results.append({**dict(row), "match_reason": "exact URL match"})

        # 2. Company + title match
        comp_norm = normalise_company(company_name)
        title_norm = _normalise(job_title)
        rows = self._conn.execute(
            "SELECT * FROM applications WHERE company_norm = ? AND job_title_norm = ?",
            (comp_norm, title_norm),
        ).fetchall()
        for row in rows:
            if row["id"] not in seen_ids:
                seen_ids.add(row["id"])
                results.append({**dict(row), "match_reason": "same company + job title"})

        # 3. Company match + skill overlap
        if required_skills:
            rows = self._conn.execute(
                "SELECT * FROM applications WHERE company_norm = ?",
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
        valid = ("generated", "applied", "rejected", "interview", "offer")
        if status not in valid:
            raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(valid)}")
        cur = self._conn.execute(
            "UPDATE applications SET status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), app_id),
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
