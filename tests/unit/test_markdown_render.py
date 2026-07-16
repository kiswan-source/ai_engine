"""Unit tests for core/document/markdown_render.py (Fase 11 — "format
profesional" fix). agent/tools/writers.py::write_docx/write_pdf used to
hand-parse markdown line by line and left literal "###"/"**"/"|" characters
in generated documents — these tests lock in the real, structured output a
single markdown-it-py pass now produces for both formats.
"""
from core.document.markdown_render import Run, parse_markdown, render_docx_body


def test_heading_with_bold_produces_single_bold_run_not_literal_asterisks():
    """The exact bug reported live: "### **Ringkasan**" used to become a
    docx heading whose TEXT was the literal string "**Ringkasan**"."""
    blocks = parse_markdown("### **Ringkasan**")
    assert len(blocks) == 1
    assert blocks[0].kind == "heading"
    assert blocks[0].level == 3
    assert blocks[0].runs == [Run("Ringkasan", bold=True)]


def test_paragraph_with_mixed_bold_italic_code():
    blocks = parse_markdown("Ini **bold** dan *italic* serta `kode`.")
    assert len(blocks) == 1
    runs = blocks[0].runs
    texts = [(r.text, r.bold, r.italic, r.code) for r in runs]
    assert ("bold", True, False, False) in texts
    assert ("italic", False, True, False) in texts
    assert ("kode", False, False, True) in texts


def test_bullet_list_items():
    blocks = parse_markdown("- Poin satu\n- Poin dua")
    assert len(blocks) == 1
    assert blocks[0].kind == "bullet_list"
    assert [r[0].text for r in blocks[0].items] == ["Poin satu", "Poin dua"]


def test_ordered_list_items():
    blocks = parse_markdown("1. Nomor satu\n2. Nomor dua")
    assert len(blocks) == 1
    assert blocks[0].kind == "ordered_list"
    assert [r[0].text for r in blocks[0].items] == ["Nomor satu", "Nomor dua"]


def test_gfm_table_header_and_rows():
    table = "| Nama | Luas (Ha) |\n| --- | --- |\n| Blok A | 11.35 |\n| Blok B | 5.20 |"
    blocks = parse_markdown(table)
    assert len(blocks) == 1
    assert blocks[0].kind == "table"
    assert [c[0].text for c in blocks[0].header] == ["Nama", "Luas (Ha)"]
    assert [[c[0].text for c in row] for row in blocks[0].rows] == [["Blok A", "11.35"], ["Blok B", "5.20"]]


def test_blockquote():
    blocks = parse_markdown("> Catatan penting")
    assert blocks[0].kind == "blockquote"
    assert blocks[0].runs[0].text == "Catatan penting"


def test_fenced_code_block():
    blocks = parse_markdown("```\nprint('hi')\n```")
    assert blocks[0].kind == "code_block"
    assert blocks[0].text == "print('hi')"


def test_horizontal_rule():
    blocks = parse_markdown("Sebelum\n\n---\n\nSesudah")
    kinds = [b.kind for b in blocks]
    assert kinds == ["paragraph", "hr", "paragraph"]


# ─── render_docx_body: real python-docx structure, not text dump ──────────

def test_render_docx_body_produces_real_heading_and_bold_run(tmp_path):
    from docx import Document

    doc = Document()
    render_docx_body(doc, "### **Ringkasan**\n\nIsi **penting**.")

    heading = next(p for p in doc.paragraphs if p.style.name == "Heading 3")
    assert heading.text == "Ringkasan"
    assert heading.runs[0].bold is True
    # The literal syntax must never appear anywhere in the document's text.
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "###" not in all_text
    assert "**" not in all_text


def test_render_docx_body_produces_real_bullet_and_number_list_styles():
    from docx import Document

    doc = Document()
    render_docx_body(doc, "- Satu\n- Dua\n\n1. Alpha\n2. Beta")

    styles = [p.style.name for p in doc.paragraphs if p.text.strip()]
    assert styles.count("List Bullet") == 2
    assert styles.count("List Number") == 2
    all_text = "\n".join(p.text for p in doc.paragraphs)
    assert "- Satu" not in all_text
    assert "1. Alpha" not in all_text


def test_render_docx_body_produces_real_table():
    from docx import Document

    doc = Document()
    render_docx_body(doc, "| A | B |\n| --- | --- |\n| x | y |")

    assert len(doc.tables) == 1
    table = doc.tables[0]
    assert [c.text for c in table.rows[0].cells] == ["A", "B"]
    assert [c.text for c in table.rows[1].cells] == ["x", "y"]
    # No paragraph anywhere should contain the raw pipe syntax.
    assert not any("|" in p.text for p in doc.paragraphs)
