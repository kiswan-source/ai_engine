"""
templates/laporan_produksi.py
Template Laporan Produksi dari CSV/Excel
Mengacu Permen ESDM No. 17 Tahun 2025 (RKAB)
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from reportlab.graphics.shapes import Drawing, Rect, Line, String
from reportlab.graphics import renderPDF
from datetime import datetime

C_PRIMARY = HexColor("#1a3a5c")
C_ACCENT  = HexColor("#c8a84b")
C_LIGHT   = HexColor("#f0f4f8")
C_BORDER  = HexColor("#2c5f8a")
C_TEXT    = HexColor("#1a1a2e")
C_SUBTEXT = HexColor("#4a4a6a")
C_GREEN   = HexColor("#2d7a4f")
C_RED     = HexColor("#c0392b")
C_ORANGE  = HexColor("#e67e22")

def build_laporan_produksi(data: dict, output_path: str) -> str:
    """
    Generate PDF Laporan Produksi.
    Args:
        data: {
            'nama_perusahaan': str,
            'lokasi'         : str,
            'komoditas'      : str,
            'periode'        : str,   # "Januari 2025" atau "Q1 2025"
            'tahun'          : str,
            'nomor_laporan'  : str,
            'data_produksi'  : list,  # [{periode, target, realisasi, satuan}]
            'total_target'   : float,
            'total_realisasi': float,
            'satuan'         : str,
            'anomali'        : list,  # [{periode, keterangan}]
            'tren'           : str,   # "naik"/"turun"/"stabil"
            'narasi_ai'      : str,
            'rekomendasi'    : list,
        }
    """
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Laporan Produksi - {data.get('nama_perusahaan','')}"
    )
    styles = getSampleStyleSheet()
    story  = []

    def P(text, **kw):
        return Paragraph(text, ParagraphStyle('p', parent=styles['Normal'], **kw))

    def section(title):
        t = Table([[P(title, fontSize=10, fontName='Helvetica-Bold',
                     textColor=white, leftIndent=8)]],
                  colWidths=[17*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,-1), C_PRIMARY),
            ('ROWPADDING',    (0,0),(-1,-1), 7),
            ('LEFTPADDING',   (0,0),(-1,-1), 10),
            ('LINEBELOW',     (0,0),(-1,-1), 2, C_ACCENT),
        ]))
        return t

    # ── HEADER ────────────────────────────────────────────
    hdr = Table([[P(
        "<b>LAPORAN REALISASI PRODUKSI</b><br/>"
        "<font size=10>Pertambangan Mineral dan Batubara</font><br/>"
        f"<font size=9>Mengacu Permen ESDM No. 17 Tahun 2025</font>",
        fontSize=18, fontName='Helvetica-Bold',
        textColor=white, alignment=TA_CENTER, leading=24
    )]], colWidths=[17*cm])
    hdr.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,-1), C_PRIMARY),
        ('ROWPADDING',    (0,0),(-1,-1), 16),
        ('LINEBELOW',     (0,0),(-1,-1), 3, C_ACCENT),
    ]))
    story.append(hdr)

    # Meta
    tgl = datetime.now().strftime("%d %B %Y")
    nomor = data.get('nomor_laporan', f"LP-{datetime.now().strftime('%Y%m')}-001")
    meta = Table([[
        P(f"No: <b>{nomor}</b>", fontSize=9, fontName='Helvetica'),
        P(f"Periode: <b>{data.get('periode','')}</b>", fontSize=9, fontName='Helvetica', alignment=TA_CENTER),
        P(f"Tanggal: <b>{tgl}</b>", fontSize=9, fontName='Helvetica', alignment=TA_RIGHT),
    ]], colWidths=[5.67*cm]*3)
    meta.setStyle(TableStyle([
        ('BACKGROUND',   (0,0),(-1,-1), C_LIGHT),
        ('ROWPADDING',   (0,0),(-1,-1), 7),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('LINEBELOW',    (0,0),(-1,-1), 0.5, C_BORDER),
    ]))
    story.append(meta)
    story.append(Spacer(1, 0.4*cm))

    # ── IDENTITAS ─────────────────────────────────────────
    story.append(section("I. IDENTITAS PERUSAHAAN"))
    rows = [
        ["Nama Perusahaan", data.get('nama_perusahaan','-')],
        ["Lokasi Tambang",  data.get('lokasi','-')],
        ["Komoditas",       data.get('komoditas','-')],
        ["Periode Laporan", data.get('periode','-')],
        ["Tahun",           data.get('tahun', str(datetime.now().year))],
        ["Dasar Hukum",     "Permen ESDM No. 17 Tahun 2025 tentang RKAB"],
    ]
    info_t = Table(
        [[P(r[0], fontSize=9, fontName='Helvetica-Bold', textColor=C_SUBTEXT),
          P(r[1], fontSize=9)] for r in rows],
        colWidths=[4.5*cm, 12.5*cm]
    )
    info_t.setStyle(TableStyle([
        ('GRID',         (0,0),(-1,-1), 0.3, HexColor("#dddddd")),
        ('ROWPADDING',   (0,0),(-1,-1), 6),
        ('LEFTPADDING',  (0,0),(-1,-1), 8),
        ('BACKGROUND',   (0,0),(0,-1),  C_LIGHT),
    ]))
    story.append(info_t)
    story.append(Spacer(1, 0.4*cm))

    # ── RINGKASAN EKSEKUTIF ───────────────────────────────
    story.append(section("II. RINGKASAN EKSEKUTIF"))

    total_target = data.get('total_target', 0)
    total_real   = data.get('total_realisasi', 0)
    satuan       = data.get('satuan', 'Ton')
    pct          = (total_real/total_target*100) if total_target > 0 else 0
    status_color = C_GREEN if pct >= 90 else (C_ORANGE if pct >= 70 else C_RED)
    status_text  = "TERCAPAI" if pct >= 90 else ("KURANG" if pct >= 70 else "TIDAK TERCAPAI")
    tren         = data.get('tren','stabil').upper()

    kpi_rows = [[
        _kpi_cell("TARGET PRODUKSI", f"{total_target:,.2f}", satuan, C_PRIMARY),
        _kpi_cell("REALISASI PRODUKSI", f"{total_real:,.2f}", satuan, C_GREEN),
        _kpi_cell("PERSENTASE", f"{pct:.1f}%", status_text, status_color),
        _kpi_cell("TREN", tren, "periode ini", C_BORDER),
    ]]
    kpi_t = Table(kpi_rows, colWidths=[4.25*cm]*4)
    kpi_t.setStyle(TableStyle([
        ('ROWPADDING',  (0,0),(-1,-1), 0),
        ('LEFTPADDING', (0,0),(-1,-1), 0),
        ('RIGHTPADDING',(0,0),(-1,-1), 4),
    ]))
    story.append(kpi_t)
    story.append(Spacer(1, 0.4*cm))

    # ── TABEL REALISASI ───────────────────────────────────
    story.append(section("III. TABEL REALISASI PRODUKSI"))

    prod_data  = data.get('data_produksi', [])
    tbl_header = [
        P("PERIODE", fontSize=8, fontName='Helvetica-Bold', textColor=white, alignment=TA_CENTER),
        P(f"TARGET ({satuan})", fontSize=8, fontName='Helvetica-Bold', textColor=white, alignment=TA_CENTER),
        P(f"REALISASI ({satuan})", fontSize=8, fontName='Helvetica-Bold', textColor=white, alignment=TA_CENTER),
        P("PERSENTASE (%)", fontSize=8, fontName='Helvetica-Bold', textColor=white, alignment=TA_CENTER),
        P("STATUS", fontSize=8, fontName='Helvetica-Bold', textColor=white, alignment=TA_CENTER),
    ]
    tbl_rows = [tbl_header]

    for i, row in enumerate(prod_data):
        tgt  = float(row.get('target', 0))
        real = float(row.get('realisasi', 0))
        pct2 = (real/tgt*100) if tgt > 0 else 0
        st   = "✓ Tercapai" if pct2 >= 90 else ("△ Kurang" if pct2 >= 70 else "✕ Tidak Tercapai")
        sc   = C_GREEN if pct2 >= 90 else (C_ORANGE if pct2 >= 70 else C_RED)
        bg   = C_LIGHT if i % 2 == 0 else white
        tbl_rows.append([
            P(str(row.get('periode','-')), fontSize=8, alignment=TA_CENTER),
            P(f"{tgt:,.2f}", fontSize=8, alignment=TA_CENTER),
            P(f"{real:,.2f}", fontSize=8, alignment=TA_CENTER),
            P(f"{pct2:.1f}%", fontSize=8, alignment=TA_CENTER),
            P(st, fontSize=8, alignment=TA_CENTER, textColor=sc, fontName='Helvetica-Bold'),
        ])

    # Total row
    tbl_rows.append([
        P("<b>TOTAL</b>", fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER),
        P(f"<b>{total_target:,.2f}</b>", fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER),
        P(f"<b>{total_real:,.2f}</b>", fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER),
        P(f"<b>{pct:.1f}%</b>", fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER),
        P(f"<b>{status_text}</b>", fontSize=8, fontName='Helvetica-Bold',
          alignment=TA_CENTER, textColor=status_color),
    ])

    prod_t = Table(tbl_rows, colWidths=[3.4*cm, 3.4*cm, 3.4*cm, 3.4*cm, 3.4*cm])
    prod_style = [
        ('BACKGROUND', (0,0), (-1,0), C_PRIMARY),
        ('BACKGROUND', (0,-1),(-1,-1), C_LIGHT),
        ('GRID',       (0,0), (-1,-1), 0.3, HexColor("#cccccc")),
        ('ROWPADDING', (0,0), (-1,-1), 6),
        ('ALIGN',      (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE',  (0,-1),(-1,-1), 1.5, C_PRIMARY),
    ]
    for i in range(1, len(tbl_rows)-1):
        bg = C_LIGHT if i % 2 == 1 else white
        prod_style.append(('BACKGROUND', (0,i), (-1,i), bg))
    prod_t.setStyle(TableStyle(prod_style))
    story.append(prod_t)
    story.append(Spacer(1, 0.4*cm))

    # ── GRAFIK BATANG (simple reportlab) ─────────────────
    if prod_data:
        story.append(section("IV. VISUALISASI PRODUKSI"))
        story.append(Spacer(1, 0.2*cm))
        chart = _build_bar_chart(prod_data, satuan)
        story.append(chart)
        story.append(Spacer(1, 0.2*cm))

    # ── ANOMALI ───────────────────────────────────────────
    anomali = data.get('anomali', [])
    if anomali:
        story.append(section("V. TEMUAN DAN ANOMALI"))
        for a in anomali:
            story.append(Paragraph(
                f"• <b>{a.get('periode','')}:</b> {a.get('keterangan','')}",
                ParagraphStyle('an', parent=styles['Normal'], fontSize=9,
                               textColor=C_RED, leftIndent=10, spaceBefore=3)
            ))
        story.append(Spacer(1, 0.3*cm))

    # ── NARASI AI ─────────────────────────────────────────
    story.append(section("VI. ANALISA DAN NARASI"))
    narasi = data.get('narasi_ai', '')
    if narasi:
        for para in narasi.split('\n'):
            para = para.strip()
            if not para: story.append(Spacer(1, 0.1*cm)); continue
            if para.startswith(('*','-')):
                story.append(Paragraph(f"• {para.lstrip('*- ')}", ParagraphStyle(
                    'nb', parent=styles['Normal'], fontSize=9, leftIndent=12,
                    textColor=C_TEXT, spaceBefore=2)))
            else:
                story.append(Paragraph(para, ParagraphStyle(
                    'nb2', parent=styles['Normal'], fontSize=9,
                    textColor=C_TEXT, leading=14, alignment=TA_JUSTIFY)))
    story.append(Spacer(1, 0.3*cm))

    # ── REKOMENDASI ───────────────────────────────────────
    rekomendasi = data.get('rekomendasi', [])
    if rekomendasi:
        story.append(section("VII. REKOMENDASI"))
        for i, rek in enumerate(rekomendasi, 1):
            story.append(Paragraph(
                f"{i}. {rek}",
                ParagraphStyle('rk', parent=styles['Normal'], fontSize=9,
                               textColor=C_TEXT, leftIndent=10, spaceBefore=3)
            ))
        story.append(Spacer(1, 0.3*cm))

    # ── FOOTER ────────────────────────────────────────────
    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_ACCENT))
    story.append(Paragraph(
        f"AI Engine — Mining Intelligence System | {tgl} | Dokumen Otomatis",
        ParagraphStyle('ft', parent=styles['Normal'], fontSize=8,
                       textColor=C_SUBTEXT, alignment=TA_CENTER)
    ))

    doc.build(story)
    return output_path


def _kpi_cell(label, value, sub, color):
    data = [[Paragraph(
        f"<font size=8 color='#ffffff'>{label}</font><br/>"
        f"<font size=16><b>{value}</b></font><br/>"
        f"<font size=8 color='#dddddd'>{sub}</font>",
        ParagraphStyle('kpi', fontName='Helvetica-Bold',
                       textColor=white, alignment=TA_CENTER, leading=20)
    )]]
    t = Table(data, colWidths=[4.1*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0),(-1,-1), color),
        ('ROWPADDING',    (0,0),(-1,-1), 10),
        ('RIGHTPADDING',  (0,0),(-1,-1), 2),
    ]))
    return t


def _build_bar_chart(prod_data, satuan):
    """Build simple bar chart using reportlab Drawing."""
    from reportlab.graphics.shapes import Drawing, Rect, Line, String, Group
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics import renderPDF

    drawing = Drawing(480, 180)
    chart   = VerticalBarChart()
    chart.x = 50
    chart.y = 20
    chart.width  = 400
    chart.height = 140

    targets    = [float(r.get('target',0)) for r in prod_data]
    realisasis = [float(r.get('realisasi',0)) for r in prod_data]
    periodes   = [str(r.get('periode','')) for r in prod_data]

    chart.data      = [targets, realisasis]
    chart.groupSpacing = 8
    chart.barSpacing   = 2

    from reportlab.lib.colors import HexColor as H
    chart.bars[0].fillColor = H("#2c5f8a")
    chart.bars[1].fillColor = H("#c8a84b")

    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(targets + realisasis) * 1.2 if targets else 100
    chart.valueAxis.labels.fontSize = 7

    chart.categoryAxis.categoryNames = periodes
    chart.categoryAxis.labels.fontSize  = 7
    chart.categoryAxis.labels.angle     = 30
    chart.categoryAxis.labels.dy        = -12

    drawing.add(chart)

    # Legend
    from reportlab.graphics.shapes import Rect as R, String as S
    drawing.add(R(50, 165, 12, 10, fillColor=H("#2c5f8a"), strokeColor=None))
    drawing.add(S(66, 170, f"Target ({satuan})", fontSize=8, fillColor=H("#333333")))
    drawing.add(R(160, 165, 12, 10, fillColor=H("#c8a84b"), strokeColor=None))
    drawing.add(S(176, 170, f"Realisasi ({satuan})", fontSize=8, fillColor=H("#333333")))

    return drawing
