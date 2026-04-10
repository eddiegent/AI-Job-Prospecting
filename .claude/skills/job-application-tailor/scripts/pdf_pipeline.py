"""Cross-platform DOCX → PDF conversion pipeline.

Tries three converters in order, stopping at the first that succeeds:

1. ``docx2pdf`` — Windows / Mac with Microsoft Word installed.
2. ``soffice`` — LibreOffice headless mode, works anywhere ``soffice`` is on PATH.
3. ``pandoc`` — universal fallback; needs a LaTeX engine for PDF output.

If all three fail (or are unavailable), the pipeline raises
``PdfConversionError`` with a message naming every tool so the user
knows what to install. The input DOCX is never moved or modified, so a
failed conversion still leaves the DOCX file on disk for manual handling.

The three ``_try_*`` helpers are looked up as module attributes at call
time so tests can monkeypatch them without touching the conversion loop.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class PdfConversionError(RuntimeError):
    """Raised when every configured PDF converter failed or was unavailable."""


def _try_docx2pdf(docx: Path, pdf: Path) -> bool:
    try:
        from docx2pdf import convert as _convert
    except ImportError:
        return False
    try:
        _convert(str(docx), str(pdf))
    except Exception:
        # Word.Application.Quit often raises even when conversion succeeded;
        # trust the on-disk artefact rather than the exception.
        pass
    return pdf.exists()


def _try_libreoffice(docx: Path, pdf: Path) -> bool:
    soffice = shutil.which("soffice")
    if soffice is None:
        return False
    try:
        subprocess.run(
            [
                soffice,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf.parent),
                str(docx),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    # soffice names the output <docx-stem>.pdf in --outdir; rename if the
    # caller asked for a different name.
    produced = pdf.parent / (docx.stem + ".pdf")
    if produced != pdf and produced.exists():
        produced.replace(pdf)
    return pdf.exists()


def _try_pandoc(docx: Path, pdf: Path) -> bool:
    pandoc = shutil.which("pandoc")
    if pandoc is None:
        return False
    try:
        subprocess.run(
            [pandoc, str(docx), "-o", str(pdf)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False
    return pdf.exists()


def convert_docx_to_pdf(docx: Path) -> Path:
    """Convert ``docx`` to a PDF sitting next to it.

    Returns the PDF path on success. Raises :class:`PdfConversionError`
    with an actionable message if every converter fails.
    """
    docx = Path(docx)
    pdf = docx.with_suffix(".pdf")

    # Resolve helpers at call time so tests can monkeypatch module attrs.
    for converter in (_try_docx2pdf, _try_libreoffice, _try_pandoc):
        if converter(docx, pdf):
            return pdf

    raise PdfConversionError(
        "Could not convert DOCX to PDF. Tried three converters in order:\n"
        "  1. docx2pdf — needs Microsoft Word (Windows or Mac).\n"
        "  2. LibreOffice (soffice) — install LibreOffice and ensure `soffice` is on PATH.\n"
        "  3. pandoc — install pandoc and a LaTeX engine (e.g. MiKTeX, TeX Live).\n"
        f"The DOCX is still available at: {docx}"
    )
