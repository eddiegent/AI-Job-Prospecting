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
import tempfile
from pathlib import Path


class PdfConversionError(RuntimeError):
    """Raised when every configured PDF converter failed or was unavailable."""


def _try_docx2pdf(docx: Path, pdf: Path) -> bool:
    try:
        from docx2pdf import convert as _convert
    except ImportError:
        return False
    # Convert a copy in a local temp dir, like LibreOffice below: Word writes the
    # PDF through an ``lu*.tmp`` scratch file next to its output and, when the
    # final rename races with something holding the folder, leaves it there.
    # 24 packs held one (a stray copy of the PDF) on 2026-11-17.
    workdir = Path(tempfile.mkdtemp(prefix="docx2pdf_"))
    try:
        src = workdir / docx.name
        shutil.copy2(docx, src)
        produced = workdir / (docx.stem + ".pdf")
        try:
            _convert(str(src), str(produced))
        except Exception:
            # Word.Application.Quit often raises even when conversion succeeded;
            # trust the on-disk artefact rather than the exception.
            pass
        if not produced.exists():
            return False
        shutil.move(str(produced), str(pdf))
        return pdf.exists()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def remove_office_scratch(folder: Path) -> list[Path]:
    """Delete Office scratch files left in ``folder`` by earlier builds: Word
    ``~$`` lock files, LibreOffice ``.~lock.<file>#`` lock files (29 packs held
    one from conversions run in a remote session) and ``lu*.tmp`` files that
    are PDFs (Word's conversion scratch, 24 packs). Any other ``.tmp`` is left
    alone. A file still open is skipped. Returns the files removed."""
    removed: list[Path] = []
    for f in Path(folder).iterdir():
        if not f.is_file():
            continue
        scratch = f.name.startswith("~$") or (f.name.startswith(".~lock.") and f.name.endswith("#"))
        if not scratch and f.name.lower().startswith("lu") and f.suffix.lower() == ".tmp":
            try:
                with f.open("rb") as fh:
                    scratch = fh.read(5) == b"%PDF-"
            except OSError:
                continue
        if scratch:
            try:
                f.unlink()
                removed.append(f)
            except OSError:
                pass
    return removed


def _try_libreoffice(docx: Path, pdf: Path) -> bool:
    soffice = shutil.which("soffice")
    if soffice is None:
        return False
    # Convert inside an isolated temp dir with a dedicated LibreOffice profile.
    #
    # Why not point soffice straight at the output folder? LibreOffice creates
    # a ``.~lock.<file>#`` lock and ``lu*.tmp`` scratch files next to whatever
    # it opens. When the output folder lives on a network/restricted mount it
    # often refuses deletes, so those markers linger forever. Converting a copy
    # in a local temp dir keeps every lock/scratch file OFF the output folder,
    # and ``shutil.rmtree`` removes them with the temp dir.
    #
    # The unique ``-env:UserInstallation`` profile means each call gets its own
    # LibreOffice instance that starts and shuts down cleanly, instead of
    # attaching to a shared background ``soffice`` process that can hold locks
    # open — which also makes parallel conversions safe.
    workdir = Path(tempfile.mkdtemp(prefix="soffice_pdf_"))
    try:
        src = workdir / docx.name
        shutil.copy2(docx, src)
        profile = (workdir / "profile").as_uri()
        try:
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={profile}",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(workdir),
                    str(src),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False
        # soffice names the output <docx-stem>.pdf inside --outdir (the temp
        # dir). Move just the finished PDF back to the requested destination;
        # shutil.move handles the cross-filesystem case (temp → mount).
        produced = workdir / (docx.stem + ".pdf")
        if not produced.exists():
            return False
        shutil.move(str(produced), str(pdf))
        return pdf.exists()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


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
