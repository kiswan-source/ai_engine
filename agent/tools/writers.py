"""File writers: DOCX, PDF, HTML, TXT, JSON."""
import os, json
from typing import Any, Dict

OUTPUT_DIR = os.path.expanduser("~/ai_engine/reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def _path(filename: str) -> str:
    return os.path.join(OUTPUT_DIR, filename) if not os.path.dirname(filename) else filename

def write_txt(filename: str, content: str) -> Dict[str, Any]:
    path = _path(filename)
    try:
        with open(path, "w", encoding="utf-8") as f: f.write(content)
        return {"success": True, "file": path, "filename": filename, "size": os.path.getsize(path), "type": "txt"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def write_json(filename: str, data: Any) -> Dict[str, Any]:
    path = _path(filename)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return {"success": True, "file": path, "filename": filename, "size": os.path.getsize(path), "type": "json"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def write_html(filename: str, content: str) -> Dict[str, Any]:
    path = _path(filename)
    try:
        if "<html" not in content.lower():
            content = f"""<!DOCTYPE html><html lang="id"><head><meta charset="UTF-8">
<title>AI Engine Report</title>
<style>body{{font-family:'Segoe UI',sans-serif;max-width:900px;margin:40px auto;padding:0 24px;background:#f8f9fa;color:#212529;line-height:1.7}}
h1{{color:#00c896;border-bottom:2px solid #00c896;padding-bottom:8px}}h2{{color:#495057;margin-top:28px}}
table{{width:100%;border-collapse:collapse;margin:16px 0}}th,td{{border:1px solid #dee2e6;padding:8px 12px}}
th{{background:#00c896;color:white}}tr:nth-child(even){{background:#f2f2f2}}
.card{{background:white;border-radius:8px;padding:20px;margin:16px 0;box-shadow:0 1px 4px rgba(0,0,0,.1)}}
code{{background:#e9ecef;padding:2px 6px;border-radius:4px;font-family:monospace}}
pre{{background:#1e2020;color:#e8eaea;padding:16px;border-radius:8px;overflow-x:auto}}</style>
</head><body>{content}</body></html>"""
        with open(path, "w", encoding="utf-8") as f: f.write(content)
        return {"success": True, "file": path, "filename": filename, "size": os.path.getsize(path), "type": "html"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def write_docx(filename: str, title: str, content: str) -> Dict[str, Any]:
    path = _path(filename)
    try:
        from docx import Document
        from docx.shared import RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from core.document.markdown_render import render_docx_body
        doc = Document()
        t = doc.add_heading(title, 0)
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in t.runs: run.font.color.rgb = RGBColor(0x00, 0xc8, 0x96)
        doc.add_paragraph()
        render_docx_body(doc, content)
        doc.save(path)
        return {"success": True, "file": path, "filename": filename, "size": os.path.getsize(path), "type": "docx"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def write_pdf(filename: str, title: str, content: str) -> Dict[str, Any]:
    path = _path(filename)
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
        from core.document.markdown_render import render_pdf_story
        doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=2.2*cm, leftMargin=2.2*cm, topMargin=2.5*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        accent = HexColor("#00c896")
        content_styles = {
            "h1": ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceBefore=12, spaceAfter=4),
            "h2": ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12, spaceBefore=8, spaceAfter=3),
            "body": ParagraphStyle("B", parent=styles["Normal"], fontSize=10, leading=16, alignment=TA_JUSTIFY),
            "bullet": ParagraphStyle("BU", parent=styles["Normal"], fontSize=10, leading=14, leftIndent=16),
            "quote": ParagraphStyle("Q", parent=styles["Normal"], fontSize=10, leading=14, leftIndent=16,
                                     textColor=HexColor("#495057")),
            "code": ParagraphStyle("C", parent=styles["Normal"], fontName="Courier", fontSize=9, leading=12,
                                    backColor=HexColor("#f1f3f5"), borderPadding=6),
            "table_header": ParagraphStyle("TH", parent=styles["Normal"], fontSize=9, leading=12),
            "table_cell": ParagraphStyle("TC", parent=styles["Normal"], fontSize=9, leading=12),
        }
        s_title = ParagraphStyle("T", parent=styles["Title"], textColor=accent, fontSize=18, spaceAfter=6, alignment=TA_CENTER)
        story = [Paragraph(title, s_title), HRFlowable(width="100%", thickness=1.5, color=accent, spaceAfter=8), Spacer(1, 0.3*cm)]
        story.extend(render_pdf_story(content, content_styles))
        doc.build(story)
        return {"success": True, "file": path, "filename": filename, "size": os.path.getsize(path), "type": "pdf"}
    except Exception as e:
        return {"success": False, "error": str(e)}
