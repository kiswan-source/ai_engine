"""Fase 15 — narrow transient-only retry applied to agent/tools/writers.py's
write functions. Uses write_txt (simplest) to exercise the shared
_with_transient_retry wrapper without needing real docx/pdf rendering.
"""
import errno

from agent.tools import writers


def test_write_txt_retries_transient_open_error_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(writers, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr("agent.tools.readers.time.sleep", lambda s: None)

    real_open = open
    attempts = {"n": 0}

    def flaky_open(path, mode="r", *a, **kw):
        if "w" in mode and str(path).endswith("flaky.txt"):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise OSError(errno.EBUSY, "temporary lock")
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", flaky_open)

    result = writers.write_txt("flaky.txt", "isi laporan")

    assert attempts["n"] == 2
    assert result["success"] is True
    assert (tmp_path / "flaky.txt").read_text() == "isi laporan"


def test_write_docx_writes_via_tmp_then_replace_no_leftover_tmp(tmp_path, monkeypatch):
    """Gate 2 finding: write_docx/write_pdf/write_xlsx/write_pptx used to
    doc.save(path) directly — a failure mid-save (now retried up to 2 more
    times) could leave `path` truncated/corrupted with no attempt ever
    fully succeeding. Fixed to save to `path + ".tmp"` then os.replace, same
    established pattern append_pdf_section/edit_docx_section already use."""
    monkeypatch.setattr(writers, "OUTPUT_DIR", str(tmp_path))

    result = writers.write_docx("laporan.docx", "Judul", "Isi laporan sederhana.")

    assert result["success"] is True
    assert (tmp_path / "laporan.docx").exists()
    assert not (tmp_path / "laporan.docx.tmp").exists()


def test_write_txt_does_not_retry_deterministic_error(tmp_path, monkeypatch):
    monkeypatch.setattr(writers, "OUTPUT_DIR", str(tmp_path))

    real_open = open
    attempts = {"n": 0}

    def always_fails_open(path, mode="r", *a, **kw):
        if "w" in mode and str(path).endswith("bad.txt"):
            attempts["n"] += 1
            raise IsADirectoryError("deliberately not transient")
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", always_fails_open)

    result = writers.write_txt("bad.txt", "isi")

    assert attempts["n"] == 1
    assert result["success"] is False
    assert "error" in result
