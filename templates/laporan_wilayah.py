"""
templates/laporan_wilayah.py
Template Laporan Wilayah dari data KML
Sesuai standar ATR/BPN dan format koordinat WGS84
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib import colors
from datetime import datetime
import os

# ── Warna tema ────────────────────────────────────────────
C_PRIMARY   = HexColor("#1a3a5c")   # Navy biru
C_ACCENT    = HexColor("#c8a84b")   # Emas
C_LIGHT     = HexColor("#f0f4f8")   # Abu terang
C_BORDER    = HexColor("#2c5f8a")   # Biru border
C_TEXT      = HexColor("#1a1a2e")   # Hitam teks
C_SUBTEXT   = HexColor("#4a4a6a")   # Abu teks sekunder
C_WHITE     = white
C_GREEN     = HexColor("#2d7a4f")   # Hijau
C_RED       = HexColor("#c0392b")   # Merah

def build_laporan_wilayah(data: dict, output_path: str) -> str:
    """
    Generate PDF Laporan Wilayah dari data KML.
    
    Args:
        data: {
            'nama_wilayah'  : str,
            'nama_pemilik'  : str,
            'lokasi'        : str,    # Kab/Kota, Provinsi
            'komoditas'     : str,
            'koordinat'     : list,   # [{lat, lon, no}]
            'luas_ha'       : float,
            'luas_m2'       : float,
            'centroid'      : {lat, lon},
            'bbox'          : {min_lat, max_lat, min_lon, max_lon},
            'jumlah_titik'  : int,
            'deskripsi_ai'  : str,    # dari Gemma
            'tanggal'       : str,
            'nomor_laporan' : str,
        }
        output_path: path lengkap output PDF
    
    Returns:
        output_path
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=f"Laporan Wilayah - {data.get('nama_wilayah','')}"
    )

    styles = getSampleStyleSheet()
    story  = []

    # ── STYLES ────────────────────────────────────────────
    def style(name, **kw):
        base = kw.pop('parent', 'Normal')
        s = ParagraphStyle(name, parent=styles[base], **kw)
        return s

    s_cover_title = style('CoverTitle',
        fontSize=20, fontName='Helvetica-Bold',
        textColor=C_WHITE, alignment=TA_CENTER, leading=26)

    s_cover_sub = style('CoverSub',
        fontSize=11, fontName='Helvetica',
        textColor=HexColor("#d4e8ff"), alignment=TA_CENTER, leading=16)

    s_section = style('Section',
        fontSize=11, fontName='Helvetica-Bold',
        textColor=C_PRIMARY, spaceBefore=14, spaceAfter=6,
        borderPad=4)

    s_body = style('Body',
        fontSize=9.5, fontName='Helvetica',
        textColor=C_TEXT, leading=15, alignment=TA_JUSTIFY,
        spaceBefore=3, spaceAfter=3)

    s_label = style('Label',
        fontSize=9, fontName='Helvetica-Bold',
        textColor=C_SUBTEXT)

    s_value = style('Value',
        fontSize=9.5, fontName='Helvetica',
        textColor=C_TEXT)

    s_center = style('Center',
        fontSize=9, fontName='Helvetica',
        textColor=C_TEXT, alignment=TA_CENTER)

    s_footer = style('Footer',
        fontSize=8, fontName='Helvetica',
        textColor=C_SUBTEXT, alignment=TA_CENTER)

    # ── HEADER / COVER ────────────────────────────────────
    # Header bar biru navy
    header_data = [[
        Paragraph(
            f"<b>LAPORAN WILAYAH</b><br/>"
            f"<font size=10>Hasil Analisis Koordinat &amp; Data Spasial</font>",
            s_cover_title
        )
    ]]
    header_table = Table(header_data, colWidths=[17*cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND',   (0,0), (-1,-1), C_PRIMARY),
        ('ROWPADDING',   (0,0), (-1,-1), 14),
        ('ALIGN',        (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING',(0,0), (-1,-1), 16),
        ('TOPPADDING',   (0,0), (-1,-1), 16),
    ]))
    story.append(header_table)

    # Nomor & tanggal laporan
    nomor = data.get('nomor_laporan', f"LW-{datetime.now().strftime('%Y%m%d')}-001")
    tgl   = data.get('tanggal', datetime.now().strftime("%d %B %Y"))

    meta_data = [
        [Paragraph(f"No. Laporan: <b>{nomor}</b>", s_label),
         Paragraph(f"Tanggal: <b>{tgl}</b>", s_label)],
    ]
    meta_table = Table(meta_data, colWidths=[8.5*cm, 8.5*cm])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), C_LIGHT),
        ('ROWPADDING',    (0,0), (-1,-1), 8),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ('RIGHTPADDING',  (0,0), (-1,-1), 10),
        ('LINEBELOW',     (0,0), (-1,-1), 0.5, C_BORDER),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 0.4*cm))

    # ── BAGIAN 1: IDENTITAS WILAYAH ───────────────────────
    story.append(_section_header("I. IDENTITAS WILAYAH", C_PRIMARY, C_ACCENT))

    info_rows = [
        ["Nama Wilayah",    data.get('nama_wilayah', '-')],
        ["Nama Pemilik",    data.get('nama_pemilik', '-')],
        ["Lokasi",          data.get('lokasi', '-')],
        ["Komoditas",       data.get('komoditas', '-')],
        ["Jumlah Titik",    f"{data.get('jumlah_titik', 0)} titik koordinat"],
        ["Sumber Data",     "File KML (Keyhole Markup Language)"],
        ["Sistem Referensi","WGS84 / Geographic Coordinate System"],
    ]

    info_table = Table(
        [[Paragraph(r[0], s_label), Paragraph(r[1], s_value)] for r in info_rows],
        colWidths=[4.5*cm, 12.5*cm]
    )
    info_table.setStyle(_info_style())
    story.append(info_table)
    story.append(Spacer(1, 0.4*cm))

    # ── BAGIAN 2: DATA LUAS ───────────────────────────────
    story.append(_section_header("II. DATA LUAS WILAYAH", C_PRIMARY, C_ACCENT))

    luas_ha = data.get('luas_ha', 0)
    luas_m2 = data.get('luas_m2', 0)

    luas_rows = [
        [Paragraph("LUAS AREA", style('LHdr', fontSize=9, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
         Paragraph("HEKTARE (Ha)", style('LHdr2', fontSize=9, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
         Paragraph("METER PERSEGI (m²)", style('LHdr3', fontSize=9, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER))],
        [Paragraph("Total", s_center),
         Paragraph(f"<b>{luas_ha:,.4f} Ha</b>", style('LVal', fontSize=11, fontName='Helvetica-Bold', textColor=C_PRIMARY, alignment=TA_CENTER)),
         Paragraph(f"<b>{luas_m2:,.2f} m²</b>", style('LVal2', fontSize=11, fontName='Helvetica-Bold', textColor=C_PRIMARY, alignment=TA_CENTER))],
    ]

    luas_table = Table(luas_rows, colWidths=[3.5*cm, 6.75*cm, 6.75*cm])
    luas_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0), C_PRIMARY),
        ('BACKGROUND',    (0,1), (-1,1), C_LIGHT),
        ('GRID',          (0,0), (-1,-1), 0.5, C_BORDER),
        ('ROWPADDING',    (0,0), (-1,-1), 8),
        ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(luas_table)
    story.append(Spacer(1, 0.3*cm))

    # Centroid & Bbox
    centroid = data.get('centroid', {})
    bbox     = data.get('bbox', {})

    if centroid:
        geo_rows = [
            ["Titik Pusat (Centroid)", f"Lat: {centroid.get('latitude',0):.6f}°, Lon: {centroid.get('longitude',0):.6f}°"],
            ["Batas Utara",  f"{bbox.get('max_lat',0):.6f}°"],
            ["Batas Selatan", f"{bbox.get('min_lat',0):.6f}°"],
            ["Batas Timur",  f"{bbox.get('max_lon',0):.6f}°"],
            ["Batas Barat",  f"{bbox.get('min_lon',0):.6f}°"],
        ]
        geo_table = Table(
            [[Paragraph(r[0], s_label), Paragraph(r[1], s_value)] for r in geo_rows],
            colWidths=[4.5*cm, 12.5*cm]
        )
        geo_table.setStyle(_info_style())
        story.append(geo_table)

    story.append(Spacer(1, 0.4*cm))

    # ── BAGIAN 3: DAFTAR KOORDINAT ────────────────────────
    story.append(_section_header("III. DAFTAR KOORDINAT BATAS WILAYAH", C_PRIMARY, C_ACCENT))

    koordinat = data.get('koordinat', [])
    if koordinat:
        coord_header = [
            Paragraph("NO", style('CH', fontSize=8, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
            Paragraph("LINTANG (°)", style('CH', fontSize=8, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
            Paragraph("BUJUR (°)", style('CH', fontSize=8, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
            Paragraph("LINTANG (DMS)", style('CH', fontSize=8, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
            Paragraph("BUJUR (DMS)", style('CH', fontSize=8, fontName='Helvetica-Bold', textColor=C_WHITE, alignment=TA_CENTER)),
        ]
        coord_rows = [coord_header]

        for i, k in enumerate(koordinat):
            lat = float(k.get('lat', k.get('latitude', 0)))
            lon = float(k.get('lon', k.get('longitude', 0)))
            lat_dms = _dd_to_dms(lat, is_lat=True)
            lon_dms = _dd_to_dms(lon, is_lat=False)
            bg = C_LIGHT if i % 2 == 0 else C_WHITE
            coord_rows.append([
                Paragraph(str(i+1), style(f'cn{i}', fontSize=8, alignment=TA_CENTER)),
                Paragraph(f"{lat:.6f}", style(f'cv{i}', fontSize=8, alignment=TA_CENTER)),
                Paragraph(f"{lon:.6f}", style(f'ce{i}', fontSize=8, alignment=TA_CENTER)),
                Paragraph(lat_dms, style(f'cd{i}', fontSize=8, alignment=TA_CENTER)),
                Paragraph(lon_dms, style(f'cf{i}', fontSize=8, alignment=TA_CENTER)),
            ])

        coord_table = Table(coord_rows, colWidths=[1.2*cm, 3.2*cm, 3.2*cm, 4.7*cm, 4.7*cm])
        coord_style = [
            ('BACKGROUND',   (0,0), (-1,0), C_PRIMARY),
            ('GRID',         (0,0), (-1,-1), 0.3, HexColor("#cccccc")),
            ('ROWPADDING',   (0,0), (-1,-1), 5),
            ('ALIGN',        (0,0), (-1,-1), 'CENTER'),
            ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ]
        for i in range(1, len(coord_rows)):
            bg = C_LIGHT if i % 2 == 1 else C_WHITE
            coord_style.append(('BACKGROUND', (0,i), (-1,i), bg))

        coord_table.setStyle(TableStyle(coord_style))
        story.append(coord_table)
        story.append(Paragraph(
            f"<i>* Sistem koordinat geografis WGS84. Total {len(koordinat)} titik batas.</i>",
            style('Note', fontSize=7.5, textColor=C_SUBTEXT, spaceBefore=4)
        ))
    story.append(Spacer(1, 0.4*cm))

    # ── BAGIAN 4: DESKRIPSI WILAYAH ───────────────────────
    story.append(_section_header("IV. DESKRIPSI DAN ANALISA WILAYAH", C_PRIMARY, C_ACCENT))

    deskripsi = data.get('deskripsi_ai', '')
    if deskripsi:
        for para in deskripsi.split('\n'):
            para = para.strip()
            if not para:
                story.append(Spacer(1, 0.15*cm))
                continue
            if para.startswith('#'):
                story.append(Paragraph(para.lstrip('#').strip(), s_section))
            elif para.startswith('*') or para.startswith('-'):
                story.append(Paragraph(f"• {para.lstrip('*-').strip()}", s_body))
            else:
                story.append(Paragraph(para, s_body))
    else:
        story.append(Paragraph(
            f"Wilayah {data.get('nama_wilayah','')} seluas {luas_ha:.4f} Ha berlokasi di "
            f"{data.get('lokasi','')}. Data koordinat telah diverifikasi dan tersusun dalam "
            f"sistem referensi WGS84 dengan total {data.get('jumlah_titik',0)} titik batas.",
            s_body
        ))

    story.append(Spacer(1, 0.4*cm))

    # ── BAGIAN 5: PERNYATAAN ──────────────────────────────
    story.append(_section_header("V. PERNYATAAN", C_PRIMARY, C_ACCENT))
    story.append(Paragraph(
        "Laporan ini dibuat berdasarkan data koordinat yang diperoleh dari file KML yang diserahkan "
        "oleh pemohon. Data telah diproses secara otomatis menggunakan sistem AI Engine dengan "
        "metode perhitungan luas menggunakan formula geodesi standar (Haversine/Spherical Excess). "
        "Keakuratan data tergantung pada kualitas pengukuran lapangan yang dilakukan oleh surveyor.",
        s_body
    ))
    story.append(Spacer(1, 0.8*cm))

    # Tanda tangan
    ttd_data = [
        [Paragraph("Dibuat oleh,", s_center),
         Paragraph("Diperiksa oleh,", s_center),
         Paragraph("Disetujui oleh,", s_center)],
        [Paragraph("<br/><br/><br/>", s_center)] * 3,
        [Paragraph("___________________", s_center)] * 3,
        [Paragraph("AI Engine System", style('ttd', fontSize=8, fontName='Helvetica-Bold', alignment=TA_CENTER)),
         Paragraph("Penanggung Jawab Teknis", style('ttd2', fontSize=8, alignment=TA_CENTER)),
         Paragraph("Pimpinan", style('ttd3', fontSize=8, alignment=TA_CENTER))],
    ]
    ttd_table = Table(ttd_data, colWidths=[5.67*cm]*3)
    ttd_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(ttd_table)

    # ── Footer ─────────────────────────────────────────────
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_ACCENT))
    story.append(Paragraph(
        f"AI Engine — Mining Intelligence System | {tgl} | Dokumen ini dibuat secara otomatis",
        s_footer
    ))

    doc.build(story)
    return output_path


# ── HELPERS ────────────────────────────────────────────────
def _section_header(title: str, bg_color, accent_color):
    data = [[Paragraph(title, ParagraphStyle(
        'sh', fontSize=10, fontName='Helvetica-Bold',
        textColor=white, leftIndent=8
    ))]]
    t = Table(data, colWidths=[17*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,-1), bg_color),
        ('ROWPADDING',    (0,0), (-1,-1), 7),
        ('LEFTPADDING',   (0,0), (-1,-1), 10),
        ('LINEBELOW',     (0,0), (-1,-1), 2, accent_color),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
    ]))
    return t

def _info_style():
    return TableStyle([
        ('GRID',          (0,0), (-1,-1), 0.3, HexColor("#dddddd")),
        ('ROWPADDING',    (0,0), (-1,-1), 6),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('BACKGROUND',    (0,0), (0,-1), HexColor("#f0f4f8")),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ])

def _dd_to_dms(dd: float, is_lat: bool) -> str:
    direction = ""
    if is_lat:
        direction = "LS" if dd < 0 else "LU"
    else:
        direction = "BT" if dd > 0 else "BB"
    dd = abs(dd)
    d  = int(dd)
    m  = int((dd - d) * 60)
    s  = ((dd - d) * 60 - m) * 60
    return f"{d}°{m}'{s:.2f}\"{direction}"
