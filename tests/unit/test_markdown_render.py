"""Unit tests for core/document/markdown_render.py (Fase 11 — "format
profesional" fix). agent/tools/writers.py::write_docx/write_pdf used to
hand-parse markdown line by line and left literal "###"/"**"/"|" characters
in generated documents — these tests lock in the real, structured output a
single markdown-it-py pass now produces for both formats.
"""
from core.document.markdown_render import (
    Run,
    parse_markdown,
    render_docx_body,
    render_pdf_story,
    render_pptx_slides,
    render_xlsx_workbook,
)


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


# ─── render_xlsx_workbook / render_pptx_slides (Workspace Slice 3, Fase 12) ─

def test_render_xlsx_workbook_h1_starts_new_sheet():
    md = "# Ringkasan\nIsi ringkasan.\n\n# Data\nIsi data."
    wb = render_xlsx_workbook(md, default_title="Laporan")
    assert wb.sheetnames == ["Ringkasan", "Data"]


def test_render_xlsx_workbook_content_before_first_heading_uses_default_title():
    md = "Paragraf pembuka tanpa heading.\n\n# Detail\nIsi."
    wb = render_xlsx_workbook(md, default_title="Laporan")
    assert wb.sheetnames == ["Laporan", "Detail"]
    assert wb["Laporan"]["A1"].value == "Paragraf pembuka tanpa heading."


def test_render_xlsx_workbook_no_heading_at_all_uses_one_default_sheet():
    wb = render_xlsx_workbook("Cuma satu paragraf.", default_title="Laporan")
    assert wb.sheetnames == ["Laporan"]


def test_render_xlsx_workbook_table_becomes_real_rows():
    md = "# Data\n| Nama | Luas |\n| --- | --- |\n| Blok A | 11.35 |\n| Blok B | 5.20 |"
    wb = render_xlsx_workbook(md, default_title="Laporan")
    ws = wb["Data"]
    rows = [[c.value for c in row] for row in ws.iter_rows()]
    assert rows == [["Nama", "Luas"], ["Blok A", "11.35"], ["Blok B", "5.20"]]
    header_cell = ws["A1"]
    assert header_cell.font.bold is True


def test_render_xlsx_workbook_duplicate_heading_names_get_unique_sheet_names():
    md = "# Data\nSatu.\n\n# Data\nDua."
    wb = render_xlsx_workbook(md, default_title="Laporan")
    assert wb.sheetnames == ["Data", "Data-2"]


def test_render_xlsx_workbook_heavy_duplication_stays_within_31_char_limit():
    """Adversarial review finding: a fixed base[:28] truncation only stays
    within Excel's 31-char sheet-name limit while the dedup counter is 1-2
    digits — 100+ duplicate headings used to silently produce an invalid,
    spec-violating (32+ char) sheet name."""
    md = "\n\n".join(f"# {'X' * 31}" for _ in range(105))
    wb = render_xlsx_workbook(md, default_title="Laporan")
    assert all(len(name) <= 31 for name in wb.sheetnames)
    assert len(wb.sheetnames) == len(set(wb.sheetnames))  # still unique


def test_render_xlsx_workbook_consecutive_headings_with_no_body_are_not_dropped():
    """Adversarial review finding: an H1 immediately followed by another H1
    (no body in between — a realistic shape of model output, e.g. an
    outline heading not yet filled in) used to vanish with zero trace,
    since the old logic only kept non-empty groups."""
    md = "# Ringkasan\nIsi ringkasan lengkap.\n\n# Rekomendasi\n\n# Penutup\nTerima kasih."
    wb = render_xlsx_workbook(md, default_title="Laporan")
    assert wb.sheetnames == ["Ringkasan", "Rekomendasi", "Penutup"]


def test_render_pptx_slides_consecutive_headings_with_no_body_are_not_dropped():
    md = "# Ringkasan\nIsi ringkasan lengkap.\n\n# Rekomendasi\n\n# Penutup\nTerima kasih."
    prs = render_pptx_slides(md, default_title="Laporan")
    titles = [s.shapes.title.text for s in prs.slides]
    assert titles == ["Ringkasan", "Rekomendasi", "Penutup"]


def test_render_xlsx_workbook_sanitizes_invalid_sheet_name_characters():
    md = "# A/B:C*D\nIsi."
    wb = render_xlsx_workbook(md, default_title="Laporan")
    assert wb.sheetnames == ["A-B-C-D"]


def test_render_pptx_slides_h1_starts_new_slide():
    md = "# Ringkasan\nIsi ringkasan.\n\n# Data\nIsi data."
    prs = render_pptx_slides(md, default_title="Laporan")
    titles = [s.shapes.title.text for s in prs.slides]
    assert titles == ["Ringkasan", "Data"]


def test_render_pptx_slides_body_gets_bullet_lines():
    md = "# Ringkasan\n- Poin satu\n- Poin dua"
    prs = render_pptx_slides(md, default_title="Laporan")
    slide = next(iter(prs.slides))
    body_text = slide.placeholders[1].text_frame.text
    assert "Poin satu" in body_text


def test_render_pptx_slides_table_gets_its_own_slide_with_real_table_shape():
    md = "# Data\n| A | B |\n| --- | --- |\n| 1 | 2 |"
    prs = render_pptx_slides(md, default_title="Laporan")
    slides = list(prs.slides)
    assert len(slides) == 2
    assert slides[1].shapes.title.text == "Data — Tabel"
    table_shapes = [s for s in slides[1].shapes if s.has_table]
    assert len(table_shapes) == 1
    table = table_shapes[0].table
    assert [c.text for c in table.rows[0].cells] == ["A", "B"]
    assert [c.text for c in table.rows[1].cells] == ["1", "2"]


def test_render_pptx_slides_no_heading_at_all_uses_one_default_slide():
    prs = render_pptx_slides("Cuma satu paragraf.", default_title="Laporan")
    assert len(list(prs.slides)) == 1
    assert next(iter(prs.slides)).shapes.title.text == "Laporan"
