"""Phase 0 regression tests for scripts/backup_user_data.py.

The backup script must be safe enough to run immediately before Phases 3
and 4.5, which will touch gitignored files that have no other recovery
path. These tests pin the safety invariants:

- every backed-up file ends up in the manifest with a matching SHA-256
- the copy preserves directory structure recursively
- SQLite tables export to CSVs whose row counts match the source
- two backup invocations produce two distinct timestamped folders
- an existing timestamped folder is never silently overwritten
- manifest verification catches post-backup corruption
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from scripts.backup_user_data import backup, verify_backup


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def fake_user_data(tmp_path: Path) -> Path:
    """Build a minimal user-data tree that mirrors the real layout."""
    root = tmp_path / "project"
    resources = root / "resources"
    output = root / "output" / "medium-10042026-acme-engineer"
    nested = root / "resources" / "cache" / "deep"
    for d in (resources, output, nested):
        d.mkdir(parents=True)

    (resources / "MASTER_CV.docx").write_bytes(b"fake-docx-bytes")
    (resources / "cv_fact_base.json").write_text('{"candidate_name": "Alex"}', encoding="utf-8")
    (resources / ".cv_hash").write_text("abc123", encoding="utf-8")
    (nested / "note.txt").write_text("nested content", encoding="utf-8")
    (output / "tailored_cv.json").write_text('{"candidate_name": "Alex"}', encoding="utf-8")

    db_path = resources / "job_history.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE applications (id INTEGER PRIMARY KEY, company TEXT, status TEXT)"
    )
    conn.executemany(
        "INSERT INTO applications (company, status) VALUES (?, ?)",
        [("Acme", "applied"), ("Globex", "generated"), ("Initech", "rejected")],
    )
    conn.commit()
    conn.close()

    return root


def test_backup_creates_manifest_with_sha256_per_file(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    created = backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")

    import json
    manifest = json.loads((created / "manifest.json").read_text(encoding="utf-8"))
    assert "files" in manifest
    # Every file recorded must match its actual SHA-256 in the backup.
    for rel, recorded_hash in manifest["files"].items():
        actual = _sha256(created / rel)
        assert actual == recorded_hash, f"Hash mismatch for {rel}"
    # The five source files we created must all be represented.
    names = set(manifest["files"].keys())
    assert any("MASTER_CV.docx" in n for n in names)
    assert any("job_history.db" in n for n in names)
    assert any("cv_fact_base.json" in n for n in names)
    assert any("note.txt" in n for n in names)
    assert any("tailored_cv.json" in n for n in names)


def test_backup_copies_all_files_recursively(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    created = backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")

    source_files = sorted(
        p.relative_to(fake_user_data).as_posix()
        for p in fake_user_data.rglob("*")
        if p.is_file()
    )
    backup_files = sorted(
        p.relative_to(created).as_posix()
        for p in (created / "resources").rglob("*")
        if p.is_file()
    ) + sorted(
        p.relative_to(created).as_posix()
        for p in (created / "output").rglob("*")
        if p.is_file()
    )
    for src_rel in source_files:
        assert any(src_rel.split("/", 1)[-1] in b for b in backup_files), (
            f"Source file {src_rel} not found in backup"
        )


def test_backup_db_export_csv_row_count_matches(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    created = backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")

    csv_path = created / "db_export" / "applications.csv"
    assert csv_path.exists()
    lines = csv_path.read_text(encoding="utf-8").strip().splitlines()
    # header + 3 rows
    assert len(lines) == 4


def test_running_backup_twice_creates_two_distinct_folders(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    a = backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")
    b = backup(fake_user_data, backup_root, timestamp="2026-04-10-1301")
    assert a != b
    assert a.exists() and b.exists()


def test_backup_refuses_to_overwrite_existing_timestamp(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")
    with pytest.raises(FileExistsError):
        backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")


def test_sha256_mismatch_fails_verification(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    created = backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")

    # Corrupt one backed-up file.
    target = created / "resources" / "MASTER_CV.docx"
    target.write_bytes(b"corrupted-bytes")

    violations = verify_backup(created)
    assert len(violations) >= 1
    assert any("MASTER_CV.docx" in v for v in violations)


def test_verify_backup_clean_install_returns_empty(fake_user_data: Path, tmp_path: Path):
    backup_root = tmp_path / "backups"
    created = backup(fake_user_data, backup_root, timestamp="2026-04-10-1200")
    assert verify_backup(created) == []
