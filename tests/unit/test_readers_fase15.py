"""Fase 15 (DCF v5 mandate — bulk/large-file capability + failure recovery,
Gate 1 Owner decision 2026-08-02): pagination, batch reads, and narrow
retry/fallback for agent/tools/readers.py. No live services (Bab 12.3).
"""
import zipfile

import pytest

from agent.tools.readers import (
    MAX_BATCH_FILES,
    read_docx,
    read_many_files,
    read_pdf,
    read_txt,
)


# ── Pagination ───────────────────────────────────────────────────────────


def test_read_txt_default_matches_old_hard_truncation_behavior(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 15000)

    result = read_txt(str(p))

    assert len(result["text"]) == 10000
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["char_count"] == 15000
    assert result["offset"] == 0


def test_read_txt_small_file_needs_no_pagination(tmp_path):
    p = tmp_path / "small.txt"
    p.write_text("halo dunia")

    result = read_txt(str(p))

    assert result["text"] == "halo dunia"
    assert result["has_more"] is False
    assert result["truncated"] is False


def test_read_txt_second_page_continues_where_first_left_off(tmp_path):
    p = tmp_path / "big.txt"
    p.write_text("x" * 15000)

    first = read_txt(str(p))
    second = read_txt(str(p), offset=first["offset"] + first["returned_chars"], length=10000)

    assert second["offset"] == 10000
    assert second["returned_chars"] == 5000
    assert second["has_more"] is False
    assert second["char_count"] == 15000


# ── Batch reads ──────────────────────────────────────────────────────────


def test_read_many_files_caps_batch_size():
    result = read_many_files(["a.txt"] * (MAX_BATCH_FILES + 1))

    assert result["success"] is False
    assert str(MAX_BATCH_FILES) in result["error"]


def test_read_many_files_rejects_empty_list():
    result = read_many_files([])
    assert result["success"] is False


def test_read_many_files_clamps_length_per_file(tmp_path):
    """Gate 2 finding: length_per_file had no upper bound — a caller could
    defeat the whole point of a small per-file batch budget."""
    from agent.tools.readers import MAX_LENGTH_PER_FILE

    p = tmp_path / "big.txt"
    p.write_text("z" * (MAX_LENGTH_PER_FILE + 5000))

    result = read_many_files([str(p)], length_per_file=999999)

    assert len(result["results"][0]["text"]) == MAX_LENGTH_PER_FILE


def test_read_many_files_survives_one_bad_file(tmp_path):
    good = tmp_path / "a.txt"
    good.write_text("hello")

    result = read_many_files([str(good), str(tmp_path / "missing.txt")])

    assert result["success"] is True
    assert result["count"] == 2
    assert result["ok_count"] == 1
    assert result["results"][0]["text"] == "hello"
    assert "error" in result["results"][1]


def test_read_many_files_unsupported_extension_reports_error_not_crash():
    result = read_many_files(["file.xyz"])

    assert result["success"] is True
    assert "error" in result["results"][0]


def test_read_many_files_accepts_a_single_string_path(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("hai")

    result = read_many_files(str(p))

    assert result["count"] == 1
    assert result["results"][0]["text"] == "hai"


# ── Narrow retry (transient only) ───────────────────────────────────────


def test_read_docx_retries_transient_error_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("agent.tools.readers.time.sleep", lambda s: None)
    p = tmp_path / "test.docx"
    p.write_bytes(b"irrelevant, Document() is mocked")

    attempts = {"n": 0}

    class _Para:
        text = "berhasil setelah retry"

    class _FakeDoc:
        paragraphs = [_Para()]

    import errno

    def fake_document(path):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError(errno.EBUSY, "temporary lock")
        return _FakeDoc()

    monkeypatch.setattr("docx.Document", fake_document)

    result = read_docx(str(p))

    assert attempts["n"] == 3
    assert "error" not in result
    assert "berhasil setelah retry" in result["text"]


def test_read_docx_does_not_retry_deterministic_error(tmp_path, monkeypatch):
    p = tmp_path / "test.docx"
    p.write_bytes(b"not a real zip")

    attempts = {"n": 0}

    def fake_document(path):
        attempts["n"] += 1
        raise ValueError("corrupt structure")

    monkeypatch.setattr("docx.Document", fake_document)

    result = read_docx(str(p))

    assert attempts["n"] == 1  # no blind retry of a deterministic failure
    assert "error" in result


def test_read_docx_does_not_retry_permission_error(tmp_path, monkeypatch):
    """PermissionError is an OSError subclass but deterministic (EACCES is
    NOT in _TRANSIENT_ERRNOS) — must fail on the first attempt, not be
    mistaken for a transient condition just because it's an OSError."""
    p = tmp_path / "test.docx"
    p.write_bytes(b"not a real zip")

    attempts = {"n": 0}

    def fake_document(path):
        attempts["n"] += 1
        raise PermissionError("access denied")

    monkeypatch.setattr("docx.Document", fake_document)

    read_docx(str(p))

    assert attempts["n"] == 1


# ── Per-format fallback ──────────────────────────────────────────────────


def test_read_docx_falls_back_to_raw_xml_when_structured_parse_fails(tmp_path, monkeypatch):
    p = tmp_path / "test.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr(
            "word/document.xml",
            b"<w:document><w:body><w:p><w:r><w:t>Halo dari fallback</w:t></w:r></w:p></w:body></w:document>",
        )

    def fake_document(path):
        raise ValueError("python-docx refuses this minimal file")

    monkeypatch.setattr("docx.Document", fake_document)

    result = read_docx(str(p))

    assert result.get("fallback_used") == "raw_xml_extraction"
    assert "Halo dari fallback" in result["text"]
    assert "error" not in result


def test_read_docx_fallback_does_not_insert_spurious_newlines_within_a_paragraph(tmp_path, monkeypatch):
    """Gate 2 finding: the first version of this fallback joined every <w:t>
    RUN with a newline — a real Word paragraph is routinely split across
    several runs (spellcheck/formatting), so one sentence could come back
    with fake line breaks inside it. Fixed to join runs within a <w:p>
    paragraph with no separator, only separating paragraphs themselves."""
    p = tmp_path / "test.docx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr(
            "word/document.xml",
            b"<w:document><w:body>"
            b"<w:p><w:r><w:t>Hello </w:t></w:r><w:r><w:t>world, this is</w:t></w:r><w:r><w:t> one sentence.</w:t></w:r></w:p>"
            b"<w:p><w:r><w:t>Second paragraph.</w:t></w:r></w:p>"
            b"</w:body></w:document>",
        )

    def fake_document(path):
        raise ValueError("python-docx refuses this minimal file")

    monkeypatch.setattr("docx.Document", fake_document)

    result = read_docx(str(p))

    lines = result["text"].split("\n")
    assert lines[0] == "Hello world, this is one sentence."
    assert lines[1] == "Second paragraph."


def test_read_docx_fallback_gives_clean_error_when_not_even_a_zip(tmp_path, monkeypatch):
    p = tmp_path / "test.docx"
    p.write_bytes(b"definitely not a zip file")

    def fake_document(path):
        raise ValueError("corrupt")

    monkeypatch.setattr("docx.Document", fake_document)

    result = read_docx(str(p))

    assert "error" in result
    assert "fallback_used" not in result


def test_read_pdf_falls_back_to_lenient_parse_when_strict_fails(tmp_path, monkeypatch):
    p = tmp_path / "test.pdf"
    p.write_bytes(b"%PDF-fake")

    calls = []

    class _FakePage:
        def extract_text(self):
            return "Halo PDF lenient"

    class _FakeReader:
        def __init__(self, path, strict):
            calls.append(strict)
            if strict:
                raise ValueError("strict parse failed")
            self.pages = [_FakePage()]

    monkeypatch.setattr("pypdf.PdfReader", _FakeReader)

    result = read_pdf(str(p))

    assert calls == [True, False]
    assert result.get("fallback_used") == "lenient_parse"
    assert "Halo PDF lenient" in result["text"]


def test_read_pdf_reports_error_when_both_strict_and_lenient_fail(tmp_path, monkeypatch):
    p = tmp_path / "test.pdf"
    p.write_bytes(b"%PDF-fake")

    class _FakeReader:
        def __init__(self, path, strict):
            raise ValueError("hopelessly corrupt")

    monkeypatch.setattr("pypdf.PdfReader", _FakeReader)

    result = read_pdf(str(p))

    assert "error" in result
    assert "fallback_used" not in result
