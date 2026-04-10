"""Phase 2 regression tests for scripts/pdf_pipeline.py.

Pin the invariants listed under PLUGIN_ROADMAP.md Phase 2 "Tests to write
first". Each test maps one-to-one to a bullet in that list.

Philosophy: no real Word/LibreOffice/pandoc calls. Every converter is
monkeypatched so the tests run offline and deterministically on any OS.
The production module must look up the three private helpers via module
globals (not via a frozen module-level list) so monkeypatching works.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import pdf_pipeline
from scripts.pdf_pipeline import PdfConversionError, convert_docx_to_pdf


def _make_docx(tmp_path: Path, name: str = "cv.docx") -> Path:
    docx = tmp_path / name
    docx.write_bytes(b"PK\x03\x04 fake docx bytes")  # not a real docx, but exists
    return docx


def _recording_fake(name: str, calls: list[str], *, succeed: bool):
    """Build a fake converter that records its name and optionally creates the PDF."""

    def fake(docx: Path, pdf: Path) -> bool:
        calls.append(name)
        if succeed:
            pdf.write_bytes(b"%PDF-1.4 fake")
            return True
        return False

    return fake


def test_pdf_pipeline_tries_docx2pdf_first(tmp_path, monkeypatch):
    docx = _make_docx(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(pdf_pipeline, "_try_docx2pdf", _recording_fake("docx2pdf", calls, succeed=True))
    monkeypatch.setattr(pdf_pipeline, "_try_libreoffice", _recording_fake("libreoffice", calls, succeed=True))
    monkeypatch.setattr(pdf_pipeline, "_try_pandoc", _recording_fake("pandoc", calls, succeed=True))

    result = convert_docx_to_pdf(docx)

    assert calls == ["docx2pdf"], f"Expected only docx2pdf to be called, got {calls}"
    assert result == docx.with_suffix(".pdf")
    assert result.exists()


def test_pdf_pipeline_falls_through_on_failure(tmp_path, monkeypatch):
    docx = _make_docx(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(pdf_pipeline, "_try_docx2pdf", _recording_fake("docx2pdf", calls, succeed=False))
    monkeypatch.setattr(pdf_pipeline, "_try_libreoffice", _recording_fake("libreoffice", calls, succeed=True))
    monkeypatch.setattr(pdf_pipeline, "_try_pandoc", _recording_fake("pandoc", calls, succeed=True))

    result = convert_docx_to_pdf(docx)

    assert calls == ["docx2pdf", "libreoffice"], f"Expected fall-through to libreoffice, got {calls}"
    assert result.exists()


def test_pdf_pipeline_all_fail_raises_actionable_error(tmp_path, monkeypatch):
    docx = _make_docx(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(pdf_pipeline, "_try_docx2pdf", _recording_fake("docx2pdf", calls, succeed=False))
    monkeypatch.setattr(pdf_pipeline, "_try_libreoffice", _recording_fake("libreoffice", calls, succeed=False))
    monkeypatch.setattr(pdf_pipeline, "_try_pandoc", _recording_fake("pandoc", calls, succeed=False))

    with pytest.raises(PdfConversionError) as excinfo:
        convert_docx_to_pdf(docx)

    assert calls == ["docx2pdf", "libreoffice", "pandoc"], f"All three must be attempted, got {calls}"
    message = str(excinfo.value)
    # The error must name all three tools so the user knows their options
    assert "docx2pdf" in message.lower()
    assert "libreoffice" in message.lower() or "soffice" in message.lower()
    assert "pandoc" in message.lower()


def test_pdf_pipeline_docx_always_produced_even_if_pdf_fails(tmp_path, monkeypatch):
    """The pipeline must never delete or corrupt the DOCX, even on total failure."""
    docx = _make_docx(tmp_path)
    original_bytes = docx.read_bytes()
    monkeypatch.setattr(pdf_pipeline, "_try_docx2pdf", lambda d, p: False)
    monkeypatch.setattr(pdf_pipeline, "_try_libreoffice", lambda d, p: False)
    monkeypatch.setattr(pdf_pipeline, "_try_pandoc", lambda d, p: False)

    with pytest.raises(PdfConversionError):
        convert_docx_to_pdf(docx)

    assert docx.exists(), "DOCX must survive a failed PDF conversion"
    assert docx.read_bytes() == original_bytes, "DOCX must be byte-identical after failed conversion"


def test_detect_libreoffice_on_path(tmp_path, monkeypatch):
    """_try_libreoffice must honour `shutil.which('soffice')`."""
    docx = _make_docx(tmp_path)
    pdf = docx.with_suffix(".pdf")

    # Case 1: soffice not on PATH — helper returns False without attempting subprocess.
    import scripts.pdf_pipeline as mod
    monkeypatch.setattr(mod.shutil, "which", lambda name: None)
    subprocess_called = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: subprocess_called.append(a) or None)
    assert mod._try_libreoffice(docx, pdf) is False
    assert subprocess_called == [], "subprocess.run must not be called when soffice is absent"

    # Case 2: soffice present — helper attempts subprocess.
    fake_soffice = str(tmp_path / "soffice")
    monkeypatch.setattr(mod.shutil, "which", lambda name: fake_soffice if name == "soffice" else None)

    def fake_run(cmd, **kwargs):
        # Simulate a successful conversion by writing the expected output file.
        pdf.write_bytes(b"%PDF-1.4 fake")

        class _Result:
            returncode = 0
            stdout = b""
            stderr = b""

        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    assert mod._try_libreoffice(docx, pdf) is True


def test_libreoffice_invocation_uses_headless_flag(tmp_path, monkeypatch):
    docx = _make_docx(tmp_path)
    pdf = docx.with_suffix(".pdf")
    import scripts.pdf_pipeline as mod

    fake_soffice = str(tmp_path / "soffice")
    monkeypatch.setattr(mod.shutil, "which", lambda name: fake_soffice if name == "soffice" else None)

    recorded: dict = {}

    def fake_run(cmd, **kwargs):
        recorded["cmd"] = list(cmd)
        recorded["kwargs"] = kwargs
        pdf.write_bytes(b"%PDF-1.4 fake")

        class _Result:
            returncode = 0
            stdout = b""
            stderr = b""

        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod._try_libreoffice(docx, pdf)

    assert "cmd" in recorded, "_try_libreoffice must invoke subprocess.run"
    cmd = recorded["cmd"]
    assert "--headless" in cmd, f"Missing --headless flag: {cmd}"
    assert "--convert-to" in cmd, f"Missing --convert-to flag: {cmd}"
    # The format argument immediately follows --convert-to
    fmt_index = cmd.index("--convert-to") + 1
    assert cmd[fmt_index] == "pdf", f"Expected 'pdf' format arg, got {cmd[fmt_index]}"
    assert str(docx) in cmd, f"DOCX path missing from command: {cmd}"
