"""Backfill the job history database from existing output folders.

Scans output/ for job_offer_analysis.json and run_summary.json files,
then populates the SQLite database with the historical data.

Usage:
    python backfill_history.py --output-dir <path-to-output> --db-path <path-to-db>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Allow importing siblings
sys.path.insert(0, str(Path(__file__).resolve().parent))

from job_history_db import JobHistoryDB


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_date_from_folder(folder_name: str) -> str | None:
    """Extract date from folder name like 'good-23032026-...' → '2026-03-23T00:00:00'."""
    m = re.search(r"(\d{8})", folder_name)
    if not m:
        return None
    raw = m.group(1)  # e.g. "23032026" (ddmmyyyy)
    try:
        day, month, year = raw[:2], raw[2:4], raw[4:]
        return f"{year}-{month}-{day}T00:00:00"
    except (ValueError, IndexError):
        return None


def backfill(output_dir: Path, db: JobHistoryDB) -> dict[str, list[str]]:
    """Scan output_dir for completed runs and insert into the database.

    Returns a dict with 'imported' and 'skipped' folder lists.
    """
    imported: list[str] = []
    skipped: list[str] = []

    if not output_dir.exists():
        return {"imported": imported, "skipped": skipped}

    for folder in sorted(output_dir.iterdir()):
        if not folder.is_dir():
            continue

        prep_dir = folder / "_prep"
        job_analysis = _load_json(prep_dir / "job_offer_analysis.json")
        run_summary = _load_json(folder / "run_summary.json")
        match_analysis = _load_json(prep_dir / "match_analysis.json")

        if not job_analysis:
            skipped.append(f"{folder.name} (no job_offer_analysis.json)")
            continue

        company = job_analysis.get("company_name", "")
        title = job_analysis.get("job_title", "")

        # Check if already imported (by company + title + output folder)
        existing = db.find_duplicates(
            company_name=company,
            job_title=title,
        )
        folder_already = any(
            e.get("output_folder") and Path(e["output_folder"]).name == folder.name
            for e in existing
        )
        if folder_already:
            skipped.append(f"{folder.name} (already in database)")
            continue

        # Extract fit data from match_analysis or run_summary
        fit_pct = None
        direct_count = None
        transferable_count = None
        gap_count = None

        if match_analysis and "match_summary" in match_analysis:
            ms = match_analysis["match_summary"]
            fit_pct = ms.get("overall_fit_pct")
            direct_count = ms.get("direct_count")
            transferable_count = ms.get("transferable_count")
            gap_count = ms.get("gap_count")
        elif run_summary and "match_summary" in run_summary:
            ms = run_summary["match_summary"]
            fit_pct = ms.get("overall_fit_pct")
            direct_count = ms.get("direct_count")
            transferable_count = ms.get("transferable_count")
            gap_count = ms.get("gap_count")

        # Derive fit_level from folder name prefix
        fit_level = None
        for prefix in ("very_good", "good", "medium", "low"):
            if folder.name.startswith(prefix + "-"):
                fit_level = prefix
                break

        created_at = _extract_date_from_folder(folder.name)

        db.add_application(
            company_name=company,
            job_title=title,
            location=job_analysis.get("location"),
            domain=job_analysis.get("domain"),
            seniority=job_analysis.get("seniority"),
            fit_level=fit_level,
            fit_pct=fit_pct,
            direct_count=direct_count,
            transferable_count=transferable_count,
            gap_count=gap_count,
            output_folder=str(folder),
            detected_language=job_analysis.get("detected_language"),
            status="generated",
            created_at=created_at,
            required_skills=job_analysis.get("required_skills", []),
            preferred_skills=job_analysis.get("preferred_skills", []),
        )
        imported.append(folder.name)

    return {"imported": imported, "skipped": skipped}


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill job history database from output folders.")
    parser.add_argument("--output-dir", required=True, help="Path to the output/ directory")
    parser.add_argument("--db-path", required=True, help="Path to job_history.db")
    args = parser.parse_args()

    db = JobHistoryDB(args.db_path)
    result = backfill(Path(args.output_dir), db)
    db.close()

    print(f"Imported: {len(result['imported'])} applications")
    for name in result["imported"]:
        print(f"  + {name}")
    if result["skipped"]:
        print(f"Skipped: {len(result['skipped'])}")
        for name in result["skipped"]:
            print(f"  - {name}")


if __name__ == "__main__":
    main()
