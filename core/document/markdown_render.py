"""Shared Markdown -> structured-blocks parser for document generation
(Fase 11 — "format profesional" fix).

`agent/tools/writers.py::write_docx`/`write_pdf` used to hand-parse content
line by line (`"# "`/`"## "` prefix match, `line.split("**")` for bold) —
that missed numbered lists, tables, nested formatting inside a heading, and
italic/inline-code entirely, so a heading like ``### **Ringkasan**`` or any
GFM table the model produced (the system prompt explicitly asks for both)
came out with literal ``###``/``**``/``|`` characters still in the generated
document. Same root cause the frontend chat renderer fix (Fase 10,
`web/src/components/chat/ChatMarkdown.tsx`) already closed for the chat
bubble — this is the Python-ecosystem equivalent, one parse (`markdown-it-py`,
CommonMark + GFM tables) feeding both `write_docx` (python-docx) and
`write_pdf` (ReportLab) so there's exactly one place that understands
Markdown, not two hand-rolled parsers that drift apart.

Deliberately a plain intermediate representation (`Block`/`Run` dataclasses)
rather than handing raw HTML to either library — python-docx has no HTML
importer at all, and ReportLab's `Paragraph` only understands a small
hand-picked HTML-like subset, so a real AST walk is the only approach that
works for both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from markdown_it import MarkdownIt

_MD = MarkdownIt("commonmark").enable("table")


@dataclass
class Run:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


BlockKind = Literal[
    "heading", "paragraph", "bullet_list", "ordered_list", "table", "hr", "blockquote", "code_block"
]


@dataclass
class Block:
    kind: BlockKind
    level: int = 0
    runs: list[Run] = field(default_factory=list)
    items: list[list[Run]] = field(default_factory=list)
    header: list[list[Run]] = field(default_factory=list)
    rows: list[list[list[Run]]] = field(default_factory=list)
    text: str = ""


def _inline_runs(inline_token) -> list[Run]:
    """Flatten one `inline` token's children into a flat run list — nested
    bold/italic/code become independent boolean flags per run rather than a
    tree, since neither python-docx nor ReportLab needs anything richer than
    "this span is bold/italic/code" (no bold-within-italic-within-code
    distinction the model would plausibly produce in a report)."""
    runs: list[Run] = []
    bold = italic = False
    for c in inline_token.children or []:
        if c.type == "text":
            if c.content:
                runs.append(Run(c.content, bold, italic))
        elif c.type == "code_inline":
            runs.append(Run(c.content, bold, italic, code=True))
        elif c.type in ("softbreak", "hardbreak"):
            runs.append(Run("\n", bold, italic))
        elif c.type == "strong_open":
            bold = True
        elif c.type == "strong_close":
            bold = False
        elif c.type == "em_open":
            italic = True
        elif c.type == "em_close":
            italic = False
        # link_open/close, s_open/close (strikethrough): rendered as plain
        # text runs — a generated report doesn't need clickable links, and
        # strikethrough has no natural equivalent worth the complexity here.
    return runs


def parse_markdown(content: str) -> list[Block]:
    """One markdown-it-py pass -> a flat list of `Block`s, in document order."""
    tokens = _MD.parse(content)
    blocks: list[Block] = []
    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        if t.type == "heading_open":
            blocks.append(Block(kind="heading", level=int(t.tag[1]), runs=_inline_runs(tokens[i + 1])))
            i += 3
        elif t.type == "paragraph_open":
            blocks.append(Block(kind="paragraph", runs=_inline_runs(tokens[i + 1])))
            i += 3
        elif t.type in ("bullet_list_open", "ordered_list_open"):
            kind: BlockKind = "bullet_list" if t.type == "bullet_list_open" else "ordered_list"
            items: list[list[Run]] = []
            depth = 1
            i += 1
            while i < n and depth > 0:
                tok = tokens[i]
                if tok.type in ("bullet_list_open", "ordered_list_open"):
                    depth += 1
                elif tok.type in ("bullet_list_close", "ordered_list_close"):
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                elif tok.type == "inline" and depth == 1:
                    items.append(_inline_runs(tok))
                i += 1
            blocks.append(Block(kind=kind, items=items))
        elif t.type == "table_open":
            header: list[list[Run]] = []
            rows: list[list[list[Run]]] = []
            current_row: list[list[Run]] | None = None
            in_body = False
            i += 1
            while i < n and tokens[i].type != "table_close":
                tok = tokens[i]
                if tok.type == "tbody_open":
                    in_body = True
                elif tok.type == "tr_open":
                    current_row = []
                elif tok.type == "tr_close" and current_row is not None:
                    if in_body:
                        rows.append(current_row)
                    else:
                        header = current_row
                    current_row = None
                elif tok.type == "inline" and current_row is not None:
                    current_row.append(_inline_runs(tok))
                i += 1
            blocks.append(Block(kind="table", header=header, rows=rows))
            i += 1
        elif t.type == "blockquote_open":
            runs: list[Run] = []
            i += 1
            while i < n and tokens[i].type != "blockquote_close":
                if tokens[i].type == "inline":
                    if runs:
                        runs.append(Run("\n"))
                    runs.extend(_inline_runs(tokens[i]))
                i += 1
            blocks.append(Block(kind="blockquote", runs=runs))
            i += 1
        elif t.type in ("fence", "code_block"):
            blocks.append(Block(kind="code_block", text=t.content.rstrip("\n")))
            i += 1
        elif t.type == "hr":
            blocks.append(Block(kind="hr"))
            i += 1
        else:
            i += 1
    return blocks


def render_docx_body(doc, content: str) -> None:
    """Append parsed ``content`` to an existing python-docx ``Document`` —
    called after the title/heading-0 block `write_docx` already added, so
    markdown headings map to docx levels 1-4 (never 0, reserved for the
    document title)."""
    from docx.shared import Pt

    def add_runs(paragraph, runs: list[Run]) -> None:
        for r in runs:
            if r.text == "\n":
                paragraph.add_run().add_break()
                continue
            run = paragraph.add_run(r.text)
            run.bold = r.bold
            run.italic = r.italic
            if r.code:
                run.font.name = "Consolas"
                run.font.size = Pt(10)

    for block in parse_markdown(content):
        if block.kind == "heading":
            add_runs(doc.add_heading("", level=min(max(block.level, 1), 4)), block.runs)
        elif block.kind == "paragraph":
            add_runs(doc.add_paragraph(), block.runs)
        elif block.kind == "bullet_list":
            for item_runs in block.items:
                add_runs(doc.add_paragraph(style="List Bullet"), item_runs)
        elif block.kind == "ordered_list":
            for item_runs in block.items:
                add_runs(doc.add_paragraph(style="List Number"), item_runs)
        elif block.kind == "table":
            n_cols = len(block.header) if block.header else (len(block.rows[0]) if block.rows else 0)
            if n_cols == 0:
                continue
            table = doc.add_table(rows=0, cols=n_cols)
            table.style = "Light Grid Accent 1"
            if block.header:
                cells = table.add_row().cells
                for i, cell_runs in enumerate(block.header):
                    add_runs(cells[i].paragraphs[0], cell_runs)
                    for run in cells[i].paragraphs[0].runs:
                        run.bold = True
            for row in block.rows:
                cells = table.add_row().cells
                for i, cell_runs in enumerate(row):
                    if i < n_cols:
                        add_runs(cells[i].paragraphs[0], cell_runs)
        elif block.kind == "blockquote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Pt(18)
            add_runs(p, block.runs)
        elif block.kind == "code_block":
            p = doc.add_paragraph()
            run = p.add_run(block.text)
            run.font.name = "Consolas"
            run.font.size = Pt(9)
        elif block.kind == "hr":
            doc.add_paragraph("─" * 40)


def render_pdf_story(content: str, styles: dict) -> list:
    """Parsed ``content`` -> a list of ReportLab flowables. ``styles`` must
    provide ``body``/``h1``/``h2``/``bullet``/``quote``/``code``/
    ``table_header``/``table_cell`` `ParagraphStyle`s — built by
    `write_pdf` so the accent color/fonts stay consistent with its title."""
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def runs_to_markup(runs: list[Run]) -> str:
        parts = []
        for r in runs:
            if r.text == "\n":
                parts.append("<br/>")
                continue
            text = esc(r.text)
            if r.code:
                text = f'<font face="Courier">{text}</font>'
            if r.bold:
                text = f"<b>{text}</b>"
            if r.italic:
                text = f"<i>{text}</i>"
            parts.append(text)
        return "".join(parts)

    story: list = []
    for block in parse_markdown(content):
        if block.kind == "heading":
            style = styles["h1"] if block.level <= 1 else styles["h2"]
            story.append(Paragraph(runs_to_markup(block.runs), style))
        elif block.kind == "paragraph":
            story.append(Paragraph(runs_to_markup(block.runs), styles["body"]))
        elif block.kind in ("bullet_list", "ordered_list"):
            for idx, item_runs in enumerate(block.items):
                prefix = "•" if block.kind == "bullet_list" else f"{idx + 1}."
                story.append(Paragraph(f"{prefix} {runs_to_markup(item_runs)}", styles["bullet"]))
        elif block.kind == "table":
            data = []
            if block.header:
                data.append([Paragraph(runs_to_markup(c), styles["table_header"]) for c in block.header])
            for row in block.rows:
                data.append([Paragraph(runs_to_markup(c), styles["table_cell"]) for c in row])
            if data:
                tbl = Table(data, hAlign="LEFT")
                cmds = [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
                if block.header:
                    cmds.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#00c896")))
                    cmds.append(("TEXTCOLOR", (0, 0), (-1, 0), colors.white))
                tbl.setStyle(TableStyle(cmds))
                story.append(tbl)
        elif block.kind == "blockquote":
            story.append(Paragraph(runs_to_markup(block.runs), styles["quote"]))
        elif block.kind == "code_block":
            story.append(Paragraph(esc(block.text).replace("\n", "<br/>"), styles["code"]))
        elif block.kind == "hr":
            story.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#dee2e6")))
        story.append(Spacer(1, 0.15 * cm))
    return story
