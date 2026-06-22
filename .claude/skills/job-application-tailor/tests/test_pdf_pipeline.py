"""Phase 2 regression tests for scripts/pdf_pipeline.py.

Pin the invariants listed under PLUGIN_ROADMAP.md Phase 2 "Tests to write
first". Each test maps one-to-one to a bullet in that list.

Philosophy: no real Word/LibreOffice/pandoc calls. Every converter is
monkeypatched so the tests run offline and deterministically on any OS.
The production module must look up the three private helpers via module
globals (not via a frozen module-level list) so monkeypatching works.

LibreOffice conversion runs against a COPY of the DOCX inside an isolated
temp dir (with a dedicated ``-env:UserInstallation`` profile), then moves
only the finished PDF back to the requested destination. This keeps
LibreOffice's ``.~lock.*#`` / ``lu*.tmp`` artefacts off the (often
delete-restricted, network-mounted) output folder. The subprocess-level
fakes below therefore emit their PDF into the ``--outdir`` directory, the
same way real soffice does.
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


def _fake_soffice_run(cmd, **kwargs):
    """Stand-in for subprocess.run that mimics soffice's --outdir behaviour.

    Real soffice writes ``<src-stem>.pdf`` into the directory given by
    ``--outdir`` (never directly to the final destination), so the fake does
    the same. This is what lets _try_libreoffice find the produced file in the
    temp dir and move it onward.
    """
    cmd = list(cmd)
    outdir = Path(cmd[cmd.index("--outdir") + 1])
    src = Path(cmd[-1])
    (outdir / (src.stem + ".pdf")).write_bytes(b"%PDF-1.4 fake")

    class _Result:
        returncode = 0
        stdout = b""
        stderr = b""

    return _Result()


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

    # Case 2: soffice present — helper attempts subprocess and produces the PDF.
    fake_soffice = str(tmp_path / "soffice")
    monkeypatch.setattr(mod.shutil, "which", lambda name: fake_soffice if name == "soffice" else None)
    monkeypatch.setattr(mod.subprocess, "run", _fake_soffice_run)
    assert mod._try_libreoffice(docx, pdf) is True
    assert pdf.exists()


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
        return _fake_soffice_run(cmd, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod._try_libreoffice(docx, pdf)

    assert "cmd" in recorded, "_try_libreoffice must invoke subprocess.run"
    cmd = recorded["cmd"]
    assert "--headless" in cmd, f"Missing --headless flag: {cmd}"
    assert "--convert-to" in cmd, f"Missing --convert-to flag: {cmd}"
    # The format argument immediately follows --convert-to
    fmt_index = cmd.index("--convert-to") + 1
    assert cmd[fmt_index] == "pdf", f"Expected 'pdf' format arg, got {cmd[fmt_index]}"
    # The source handed to soffice is a COPY (same basename) inside the temp
    # outdir — NOT the original DOCX on the (mounted) output folder.
    src_arg = Path(cmd[-1])
    assert src_arg.name == docx.name, f"soffice source should share the DOCX name: {cmd}"
    assert src_arg != docx, "soffice must convert a temp copy, not the original DOCX on the mount"


def test_libreoffice_uses_isolated_user_profile(tmp_path, monkeypatch):
    """Each conversion must pass a dedicated -env:UserInstallation profile so
    soffice runs as its own instance and shuts down cleanly (no shared
    background process holding locks; safe under parallel runs)."""
    docx = _make_docx(tmp_path)
    pdf = docx.with_suffix(".pdf")
    import scripts.pdf_pipeline as mod

    fake_soffice = str(tmp_path / "soffice")
    monkeypatch.setattr(mod.shutil, "which", lambda name: fake_soffice if name == "soffice" else None)

    recorded: dict = {}

    def fake_run(cmd, **kwargs):
        recorded["cmd"] = list(cmd)
        return _fake_soffice_run(cmd, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    mod._try_libreoffice(docx, pdf)

    profile_args = [a for a in recorded["cmd"] if a.startswith("-env:UserInstallation=")]
    assert profile_args, f"Missing -env:UserInstallation profile flag: {recorded['cmd']}"
    assert profile_args[0].startswith("-env:UserInstallation=file:"), \
        f"Profile must be a file URI: {profile_args[0]}"


def test_libreoffice_converts_off_mount_and_cleans_up(tmp_path, monkeypatch):
    """The conversion must happen in a temp dir distinct from the output folder,
    leave NO lock/scratch files behind in the output folder, and remove the
    temp dir afterwards."""
    outdir_mount = tmp_path / "output_folder"
    outdir_mount.mkdir()
    docx = _make_docx(outdir_mount, "CV.docx")
    pdf = docx.with_suffix(".pdf")
    import scripts.pdf_pipeline as mod

    fake_soffice = str(tmp_path / "soffice")
    monkeypatch.setattr(mod.shutil, "which", lambda name: fake_soffice if name == "soffice" else None)

    seen = {}

    def fake_run(cmd, **kwargs):
        cmd = list(cmd)
        workdir = Path(cmd[cmd.index("--outdir") + 1])
        seen["workdir"] = workdir
        # Simulate the lock/scratch debris LibreOffice would create next to the
        # file it opens — it must all live in the temp workdir, never the mount.
        (workdir / ".~lock.CV.docx#").write_text("lock")
        (workdir / "lu12345.tmp").write_text("scratch")
        return _fake_soffice_run(cmd, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    ok = mod._try_libreoffice(docx, pdf)

    assert ok is True and pdf.exists(), "conversion should succeed and produce the PDF"
    # Work happened OFF the output folder.
    assert seen["workdir"] != outdir_mount
    # The temp workdir (with all its lock/scratch debris) is gone.
    assert not seen["workdir"].exists(), "temp workdir must be cleaned up"
    # The output folder contains ONLY the original DOCX and the new PDF — no
    # .~lock.*# and no lu*.tmp leaked onto the mount.
    leftovers = sorted(p.name for p in outdir_mount.iterdir())
    assert leftovers == ["CV.docx", "CV.pdf"], f"output folder must be clean, got {leftovers}"
