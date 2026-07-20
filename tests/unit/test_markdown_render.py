"""Unit tests for core/document/markdown_render.py (Fase 11 — "format
profesional" fix). agent/tools/writers.py::write_docx/write_pdf used to
hand-parse markdown line by line and left literal "###"/"**"/"|" characters
in generated documents — these tests lock in the real, structured output a
single markdown-it-py pass now produces for both formats.
"""
from core.document.markdown_render import Run, parse_markdown, render_docx_body, render_pdf_story


def _pdf_styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontSize=14, leading=18),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=12, leading=15),
        "body": ParagraphStyle("B", parent=base["Normal"], fontSize=10, leading=16),
        "bullet": ParagraphStyle("BU", parent=base["Normal"], fontSize=10, leading=14, leftIndent=16),
        "quote": ParagraphStyle("Q", parent=base["Normal"], fontSize=10, leading=14, leftIndent=16),
        "code": ParagraphStyle("C", parent=base["Normal"], fontName="Courier", fontSize=9, leading=12),
        "table_header": ParagraphStyle("TH", parent=base["Normal"], fontSize=9, leading=12),
        "table_cell": ParagraphStyle("TC", parent=base["Normal"], fontSize=9, leading=12),
    }


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
    assert [runs[0].text for _depth, runs in blocks[0].items] == ["Poin satu", "Poin dua"]
    assert [depth for depth, _runs in blocks[0].items] == [1, 1]


def test_ordered_list_items():
    blocks = parse_markdown("1. Nomor satu\n2. Nomor dua")
    assert len(blocks) == 1
    assert blocks[0].kind == "ordered_list"
    assert [runs[0].text for _depth, runs in blocks[0].items] == ["Nomor satu", "Nomor dua"]


def test_ordered_list_custom_start_number_is_preserved():
    blocks = parse_markdown("3. Tiga\n4. Empat")
    assert blocks[0].start == 3


def test_nested_bullet_list_items_are_kept_not_dropped():
    """Gate 2 regression: nested items used to vanish entirely (depth > 1
    was skipped outright), not just render unindented."""
    blocks = parse_markdown("- Item 1\n  - Nested A\n  - Nested B\n- Item 2")
    assert len(blocks) == 1
    texts = [runs[0].text for _depth, runs in blocks[0].items]
    assert texts == ["Item 1", "Nested A", "Nested B", "Item 2"]
    depths = [depth for depth, _runs in blocks[0].items]
    assert depths == [1, 2, 2, 1]


def test_image_produces_placeholder_run_not_empty():
    """Gate 2 regression: images used to produce zero runs (silently
    dropped) with no trace at all."""
    blocks = parse_markdown("![Peta lokasi](http://example.com/map.png)")
    assert len(blocks) == 1
    assert blocks[0].runs
    assert "Peta lokasi" in blocks[0].runs[0].text


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


def test_render_docx_body_nested_list_uses_distinct_style():
    from docx import Document

    doc = Document()
    render_docx_body(doc, "- Item 1\n  - Nested A\n- Item 2")

    styles = [p.style.name for p in doc.paragraphs if p.text.strip()]
    assert styles == ["List Bullet", "List Bullet 2", "List Bullet"]


# ─── render_pdf_story: heading fidelity, nested/start-numbered lists ──────

def test_render_pdf_story_differentiates_h2_h3_h4_font_sizes():
    """Gate 2 regression: every level >= 2 used to collapse into one h2
    style, so a document with H2/H3/H4 structure rendered visually flat."""
    story = render_pdf_story("## H2\n\n### H3\n\n#### H4", _pdf_styles())
    sizes = [p.style.fontSize for p in story if hasattr(p, "style")]
    assert sizes[0] > sizes[1] > sizes[2]


def test_render_pdf_story_ordered_list_respects_custom_start():
    story = render_pdf_story("3. Tiga\n4. Empat", _pdf_styles())
    texts = [p.text for p in story if hasattr(p, "text")]
    assert texts[0].startswith("3.")
    assert texts[1].startswith("4.")


def test_render_pdf_story_nested_list_item_is_kept_and_indented():
    story = render_pdf_story("- Item 1\n  - Nested A\n- Item 2", _pdf_styles())
    paragraphs = [p for p in story if hasattr(p, "text")]
    texts = [p.text for p in paragraphs]
    assert any("Nested A" in t for t in texts)
    nested = next(p for p in paragraphs if "Nested A" in p.text)
    top = next(p for p in paragraphs if "Item 1" in p.text)
    assert nested.style.leftIndent > top.style.leftIndent
