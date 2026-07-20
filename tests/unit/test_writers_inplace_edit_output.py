"""append_pdf_section end-to-end (Workspace Slice 4, Fase 12 — PDF half of
in-place edit) — same style as test_writers_markdown_output.py: call the
actual public tool function, not just the shared parser.
"""
from pathlib import Path

from agent.tools.writers import append_pdf_section, write_pdf


def test_append_pdf_section_adds_pages_without_touching_existing_ones(tmp_path):
    from pypdf import PdfReader

    out = tmp_path / "laporan.pdf"
    write_pdf(str(out), "Laporan Awal", "# Ringkasan\nIsi ringkasan lama.")
    original_bytes = out.read_bytes()
    pages_before = len(PdfReader(str(out)).pages)

    result = append_pdf_section(str(out), "Isi tambahan.\n\n| A | B |\n| --- | --- |\n| 1 | 2 |", title="Bagian Baru")

    assert result["success"] is True
    assert result["pages_before"] == pages_before
    assert result["pages_after"] > pages_before
    assert result["pages_added"] == result["pages_after"] - pages_before

    reader = PdfReader(str(out))
    assert len(reader.pages) == result["pages_after"]
    full_text = "\n".join(p.extract_text() for p in reader.pages)
    assert "Ringkasan" in full_text  # original content survived
    assert "Bagian Baru" in full_text
    assert "Isi tambahan." in full_text
    # The original file's own bytes were replaced (a real merge happened,
    # not a no-op) — but the ORIGINAL PAGE's extracted text is unchanged.
    assert out.read_bytes() != original_bytes


def test_append_pdf_section_without_title_has_no_extra_heading(tmp_path):
    from pypdf import PdfReader

    out = tmp_path / "laporan.pdf"
    write_pdf(str(out), "Laporan Awal", "Isi awal.")
    result = append_pdf_section(str(out), "Isi tambahan tanpa judul.")

    assert result["success"] is True
    text = "\n".join(p.extract_text() for p in PdfReader(str(out)).pages)
    assert "Isi tambahan tanpa judul." in text


def test_append_pdf_section_missing_file_returns_error(tmp_path):
    result = append_pdf_section(str(tmp_path / "does-not-exist.pdf"), "isi")
    assert result["success"] is False
    assert "error" in result


def test_no_agpl_pdf_dependency_was_introduced():
    """Owner's Gate 1 decision (DCF classified full PDF in-place text
    editing HUMAN-ONLY/HALT over PyMuPDF's AGPL-3.0 license): this repo's
    dependency list must never gain pymupdf/fitz as a side effect of PDF
    work — a regression here is a licensing exposure, not just a
    functional bug, so it's asserted explicitly rather than left implicit."""
    import importlib.util

    assert importlib.util.find_spec("fitz") is None
    assert importlib.util.find_spec("pymupdf") is None

    requirements = (Path(__file__).resolve().parents[2] / "requirements.txt").read_text().lower()
    assert "pymupdf" not in requirements
    assert "fitz" not in requirements
