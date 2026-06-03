"""
templates/dokumen_wiup.py
Template Dokumen WIUP per Komoditas
Mengacu UU No. 3 Tahun 2020 & Permen ESDM No. 18 Tahun 2025
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY, TA_RIGHT
from datetime import datetime

C_PRIMARY = HexColor("#1a3a5c")
C_ACCENT  = HexColor("#c8a84b")
C_LIGHT   = HexColor("#f0f4f8")
C_BORDER  = HexColor("#2c5f8a")
C_TEXT    = HexColor("#1a1a2e")
C_SUBTEXT = HexColor("#4a4a6a")

# Klasifikasi komoditas sesuai UU 3/2020
KOMODITAS_INFO = {
    "Batubara": {
        "klasifikasi": "Mineral Energi",
        "dasar_hukum": "UU No. 3 Tahun 2020, Permen ESDM No. 18 Tahun 2025",
        "jenis_iup": "IUP Eksplorasi / IUP Operasi Produksi",
        "kewenangan": "Menteri ESDM / Gubernur (sesuai lokasi)",
        "luas_max_eksplorasi": "50.000 Ha",
        "luas_max_produksi": "15.000 Ha",
        "jangka_eksplorasi": "7 tahun",
        "jangka_produksi": "20 tahun (dapat diperpanjang)",
    },
    "Emas": {
        "klasifikasi": "Mineral Logam",
        "dasar_hukum": "UU No. 3 Tahun 2020, Permen ESDM No. 18 Tahun 2025",
        "jenis_iup": "IUP Eksplorasi / IUP Operasi Produksi",
        "kewenangan": "Menteri ESDM / Gubernur (sesuai lokasi)",
        "luas_max_eksplorasi": "100.000 Ha",
        "luas_max_produksi": "25.000 Ha",
        "jangka_eksplorasi": "8 tahun",
        "jangka_produksi": "20 tahun (dapat diperpanjang)",
    },
    "Batu Gamping": {
        "klasifikasi": "Mineral Bukan Logam",
        "dasar_hukum": "UU No. 3 Tahun 2020, PP No. 96 Tahun 2021",
        "jenis_iup": "IUP Eksplorasi / IUP Operasi Produksi",
        "kewenangan": "Bupati/Walikota / Gubernur (sesuai lokasi)",
        "luas_max_eksplorasi": "5.000 Ha",
        "luas_max_produksi": "1.000 Ha",
        "jangka_eksplorasi": "3 tahun",
        "jangka_produksi": "10 tahun (dapat diperpanjang)",
    },
    "Andesit": {
        "klasifikasi": "Mineral Bukan Logam (Batuan)",
        "dasar_hukum": "UU No. 3 Tahun 2020, PP No. 96 Tahun 2021",
        "jenis_iup": "IUP Eksplorasi / IUP Operasi Produksi",
        "kewenangan": "Bupati/Walikota / Gubernur (sesuai lokasi)",
        "luas_max_eksplorasi": "5.000 Ha",
        "luas_max_produksi": "1.000 Ha",
        "jangka_eksplorasi": "3 tahun",
        "jangka_produksi": "5 tahun (dapat diperpanjang)",
    },
    "Pasir Silika": {
        "klasifikasi": "Mineral Bukan Logam",
        "dasar_hukum": "UU No. 3 Tahun 2020, PP No. 96 Tahun 2021",
        "jenis_iup": "IUP Eksplorasi / IUP Operasi Produksi",
        "kewenangan": "Bupati/Walikota / Gubernur (sesuai lokasi)",
        "luas_max_eksplorasi": "5.000 Ha",
        "luas_max_produksi": "1.000 Ha",
        "jangka_eksplorasi": "3 tahun",
        "jangka_produksi": "10 tahun (dapat diperpanjang)",
    },
}

def build_dokumen_wiup(data: dict, output_path: str) -> str:
    """
    Generate dokumen WIUP / IUP sesuai komoditas.
    Args:
        data: {
            'jenis_dokumen'   : str,  # "permohonan_wiup" / "laporan_eksplorasi" / "permohonan_iup_op"
            'komoditas'       : str,
            'nama_perusahaan' : str,
            'nib'             : str,
            'npwp'            : str,
            'alamat'          : str,
            'nama_direksi'    : str,
            'jabatan_direksi' : str,
            'nama_wilayah'    : str,
            'lokasi'          : str,  # Kab, Provinsi
            'luas_ha'         : float,
            'koordinat_text'  : str,  # koordinat formatted
            'komoditas_teknis': str,
            'rencana_produksi': str,
            'nama_ahli'       : str,
            'keahlian'        : str,
            'nomor_sertifikat': str,
            'tanggal'         : str,
            'nomor_surat'     : str,
            'kepada'          : str,  # tujuan surat
            'narasi_teknis'   : str,  # dari AI
        }
    """
    jenis = data.get('jenis_dokumen', 'permohonan_wiup')
    komoditas = data.get('komoditas', 'Batubara')
    info_komoditas = KOMODITAS_INFO.get(komoditas, KOMODITAS_INFO['Batubara'])

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        rightMargin=2.5*cm, leftMargin=2.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    story  = []
    tgl = data.get('tanggal', datetime.now().strftime("%d %B %Y"))

    def P(text, **kw):
        return Paragraph(text, ParagraphStyle('_p', parent=styles['Normal'], **kw))

    def section(title):
        t = Table([[P(title, fontSize=10, fontName='Helvetica-Bold',
                     textColor=white, leftIndent=8)]],
                  colWidths=[16*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0),(-1,-1), C_PRIMARY),
            ('ROWPADDING', (0,0),(-1,-1), 7),
            ('LEFTPADDING',(0,0),(-1,-1), 10),
            ('LINEBELOW',  (0,0),(-1,-1), 2, C_ACCENT),
        ]))
        return t

    if jenis == 'permohonan_wiup':
        story += _build_permohonan_wiup(data, info_komoditas, P, section, tgl, styles)
    elif jenis == 'laporan_eksplorasi':
        story += _build_laporan_eksplorasi(data, info_komoditas, P, section, tgl, styles)
    elif jenis == 'permohonan_iup_op':
        story += _build_permohonan_iup_op(data, info_komoditas, P, section, tgl, styles)
    else:
        story += _build_permohonan_wiup(data, info_komoditas, P, section, tgl, styles)

    story.append(Spacer(1, 0.5*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_ACCENT))
    story.append(P(
        f"Dokumen digenerate oleh AI Engine | {tgl} | "
        f"Mengacu {info_komoditas['dasar_hukum']}",
        fontSize=7.5, textColor=C_SUBTEXT, alignment=TA_CENTER
    ))

    doc.build(story)
    return output_path


def _build_permohonan_wiup(data, info, P, section, tgl, styles):
    """Surat Permohonan WIUP."""
    story = []
    nomor = data.get('nomor_surat', f"001/WIUP/{datetime.now().year}")
    kepada = data.get('kepada', 'Yth. Bupati/Walikota ...')

    # KOP
    kop = Table([[P(
        f"<b>{data.get('nama_perusahaan','[NAMA PERUSAHAAN]')}</b><br/>"
        f"<font size=8>{data.get('alamat','[ALAMAT PERUSAHAAN]')}</font>",
        fontSize=14, fontName='Helvetica-Bold',
        textColor=C_PRIMARY, alignment=TA_CENTER, leading=20
    )]], colWidths=[16*cm])
    kop.setStyle(TableStyle([
        ('LINEBELOW', (0,0),(-1,-1), 2, C_PRIMARY),
        ('ROWPADDING',(0,0),(-1,-1), 10),
    ]))
    story.append(kop)
    story.append(Spacer(1, 0.5*cm))

    # Nomor & tanggal
    story.append(P(f"Nomor : {nomor}",
                   fontSize=10, textColor=C_TEXT))
    story.append(P(f"Hal   : Permohonan Wilayah Izin Usaha Pertambangan (WIUP) "
                   f"{info['klasifikasi']} – {data.get('komoditas','')}",
                   fontSize=10, textColor=C_TEXT))
    story.append(P(f"Tanggal: {tgl}", fontSize=10, textColor=C_TEXT))
    story.append(Spacer(1, 0.4*cm))

    story.append(P(kepada, fontSize=10, textColor=C_TEXT))
    story.append(P("di Tempat", fontSize=10, textColor=C_TEXT))
    story.append(Spacer(1, 0.4*cm))

    # Pembuka
    story.append(P("Dengan hormat,", fontSize=10))
    story.append(Spacer(1, 0.2*cm))
    komoditas = data.get('komoditas','')
    nama_perusahaan = data.get('nama_perusahaan','')
    nama_wilayah = data.get('nama_wilayah','')
    lokasi = data.get('lokasi','')
    luas_ha = data.get('luas_ha', 0)

    story.append(P(
        f"Yang bertanda tangan di bawah ini, kami selaku perwakilan dari "
        f"<b>{nama_perusahaan}</b>, dengan ini mengajukan permohonan Wilayah Izin "
        f"Usaha Pertambangan (WIUP) untuk komoditas <b>{komoditas}</b> "
        f"({info['klasifikasi']}) di wilayah <b>{nama_wilayah}</b>, "
        f"Kabupaten/Kota {lokasi}.",
        fontSize=10, leading=16, alignment=TA_JUSTIFY
    ))
    story.append(Spacer(1, 0.3*cm))
    story.append(P(
        "Permohonan ini diajukan sesuai dengan ketentuan yang berlaku, yaitu "
        f"<b>{info['dasar_hukum']}</b>, dengan rincian sebagai berikut:",
        fontSize=10, leading=16, alignment=TA_JUSTIFY
    ))
    story.append(Spacer(1, 0.3*cm))

    # Data permohonan
    story.append(section("A. DATA PEMOHON"))
    rows_pemohon = [
        ["Nama Perusahaan",    data.get('nama_perusahaan','-')],
        ["Nomor Induk Berusaha (NIB)", data.get('nib','-')],
        ["NPWP",               data.get('npwp','-')],
        ["Alamat",             data.get('alamat','-')],
        ["Nama Direksi",       data.get('nama_direksi','-')],
        ["Jabatan",            data.get('jabatan_direksi','-')],
    ]
    _info_table(story, rows_pemohon, P)

    story.append(Spacer(1, 0.3*cm))
    story.append(section("B. DATA WILAYAH YANG DIMOHON"))
    rows_wilayah = [
        ["Nama Wilayah",       data.get('nama_wilayah','-')],
        ["Lokasi",             data.get('lokasi','-')],
        ["Komoditas",          f"{komoditas} ({info['klasifikasi']})"],
        ["Luas Wilayah",       f"{luas_ha:,.4f} Ha"],
        ["Luas Maksimum WIUP", info['luas_max_eksplorasi']],
        ["Jenis IUP",          info['jenis_iup']],
        ["Kewenangan",         info['kewenangan']],
    ]
    _info_table(story, rows_wilayah, P)

    story.append(Spacer(1, 0.3*cm))
    story.append(section("C. KOORDINAT WILAYAH"))
    koordinat_text = data.get('koordinat_text', '-')
    story.append(P(koordinat_text, fontSize=9, fontName='Courier',
                   textColor=C_TEXT, leading=14))

    story.append(Spacer(1, 0.3*cm))
    story.append(section("D. PERNYATAAN TEKNIS"))
    story.append(P(
        f"Berdasarkan kajian awal yang dilakukan oleh tenaga ahli kami, "
        f"<b>{data.get('nama_ahli','[Nama Ahli]')}</b> "
        f"({data.get('keahlian','Ahli Geologi/Pertambangan')}, "
        f"No. Sertifikat: {data.get('nomor_sertifikat','-')}), "
        f"wilayah yang dimohon memiliki potensi {komoditas} yang layak untuk "
        f"dikembangkan.",
        fontSize=10, leading=16, alignment=TA_JUSTIFY
    ))

    # Narasi teknis AI
    narasi = data.get('narasi_teknis','')
    if narasi:
        story.append(Spacer(1, 0.2*cm))
        for line in narasi.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith(('*','-')):
                story.append(P(f"• {line.lstrip('*- ')}", fontSize=9,
                               leftIndent=12, spaceBefore=2))
            else:
                story.append(P(line, fontSize=10, leading=16, alignment=TA_JUSTIFY))

    story.append(Spacer(1, 0.3*cm))
    story.append(section("E. PERSYARATAN YANG DILAMPIRKAN"))
    persyaratan = [
        "Fotokopi Nomor Induk Berusaha (NIB)",
        "Fotokopi NPWP Perusahaan",
        "Susunan pengurus dan daftar pemegang saham",
        "Surat pernyataan dari tenaga ahli geologi/pertambangan bersertifikat",
        "Pernyataan kesanggupan mematuhi regulasi lingkungan hidup",
        "Bukti jaminan kesungguhan eksplorasi",
        "Peta wilayah yang dimohon (skala 1:50.000)",
        "Daftar koordinat batas wilayah",
    ]
    for i, p in enumerate(persyaratan, 1):
        story.append(P(f"{i}. {p}", fontSize=9, leftIndent=10, spaceBefore=2))

    story.append(Spacer(1, 0.4*cm))
    story.append(P(
        "Demikian permohonan ini kami sampaikan. Atas perhatian dan persetujuan "
        "Bapak/Ibu, kami mengucapkan terima kasih.",
        fontSize=10, leading=16, alignment=TA_JUSTIFY
    ))
    story.append(Spacer(1, 0.6*cm))

    # TTD
    ttd = Table([
        [P("", fontSize=9), P(f"Hormat kami,", fontSize=10, alignment=TA_CENTER)],
        [P(""), P(f"<br/><br/><br/>", fontSize=10)],
        [P(""), P(f"<b>{data.get('nama_direksi','[Nama Direksi]')}</b>",
                  fontSize=10, fontName='Helvetica-Bold', alignment=TA_CENTER)],
        [P(""), P(f"{data.get('jabatan_direksi','Direktur Utama')}",
                  fontSize=9, alignment=TA_CENTER)],
        [P(""), P(f"<b>{nama_perusahaan}</b>",
                  fontSize=9, fontName='Helvetica-Bold', alignment=TA_CENTER)],
    ], colWidths=[8*cm, 8*cm])
    story.append(ttd)
    return story


def _build_laporan_eksplorasi(data, info, P, section, tgl, styles):
    """Laporan Akhir Eksplorasi."""
    story = []
    story.append(Table([[P(
        f"<b>LAPORAN AKHIR EKSPLORASI</b><br/>"
        f"<font size=12>{data.get('komoditas','')} — {data.get('nama_wilayah','')}</font><br/>"
        f"<font size=10>{data.get('nama_perusahaan','')}</font>",
        fontSize=18, fontName='Helvetica-Bold',
        textColor=white, alignment=TA_CENTER, leading=28
    )]], colWidths=[16*cm]))
    story[-1].setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), C_PRIMARY),
        ('ROWPADDING', (0,0),(-1,-1), 16),
        ('LINEBELOW',  (0,0),(-1,-1), 3, C_ACCENT),
    ]))

    story.append(Spacer(1, 0.5*cm))
    story.append(section("I. INFORMASI UMUM"))
    rows = [
        ["Nama Wilayah",    data.get('nama_wilayah','-')],
        ["Perusahaan",      data.get('nama_perusahaan','-')],
        ["Komoditas",       f"{data.get('komoditas','-')} ({info['klasifikasi']})"],
        ["Lokasi",          data.get('lokasi','-')],
        ["Luas Wilayah",    f"{data.get('luas_ha',0):,.4f} Ha"],
        ["Dasar Hukum",     info['dasar_hukum']],
        ["Tanggal Laporan", tgl],
    ]
    _info_table(story, rows, P)

    story.append(Spacer(1, 0.4*cm))
    story.append(section("II. HASIL EKSPLORASI"))
    narasi = data.get('narasi_teknis', '')
    if narasi:
        for line in narasi.split('\n'):
            line = line.strip()
            if not line: story.append(Spacer(1, 0.1*cm)); continue
            story.append(P(line, fontSize=10, leading=15, alignment=TA_JUSTIFY))
    else:
        story.append(P(
            f"Kegiatan eksplorasi telah dilaksanakan di wilayah {data.get('nama_wilayah','')} "
            f"seluas {data.get('luas_ha',0):,.2f} Ha. Berdasarkan hasil pemetaan dan "
            f"pengambilan sampel, ditemukan indikasi keberadaan {data.get('komoditas','')} "
            f"di wilayah tersebut.",
            fontSize=10, leading=15, alignment=TA_JUSTIFY
        ))

    story.append(Spacer(1, 0.3*cm))
    story.append(section("III. KOORDINAT WILAYAH"))
    story.append(P(data.get('koordinat_text','-'),
                   fontSize=9, fontName='Courier', leading=14))
    return story


def _build_permohonan_iup_op(data, info, P, section, tgl, styles):
    """Permohonan IUP Operasi Produksi."""
    story = []
    story.append(Table([[P(
        f"<b>PERMOHONAN IUP OPERASI PRODUKSI</b><br/>"
        f"<font size=11>{data.get('komoditas','')} ({info['klasifikasi']})</font>",
        fontSize=16, fontName='Helvetica-Bold',
        textColor=white, alignment=TA_CENTER, leading=24
    )]], colWidths=[16*cm]))
    story[-1].setStyle(TableStyle([
        ('BACKGROUND', (0,0),(-1,-1), C_PRIMARY),
        ('ROWPADDING', (0,0),(-1,-1), 14),
        ('LINEBELOW',  (0,0),(-1,-1), 3, C_ACCENT),
    ]))
    story.append(Spacer(1, 0.4*cm))
    story.append(section("I. DATA PERUSAHAAN"))
    rows = [
        ["Nama Perusahaan", data.get('nama_perusahaan','-')],
        ["NIB",             data.get('nib','-')],
        ["NPWP",            data.get('npwp','-')],
        ["Alamat",          data.get('alamat','-')],
        ["Direksi",         data.get('nama_direksi','-')],
    ]
    _info_table(story, rows, P)

    story.append(Spacer(1, 0.3*cm))
    story.append(section("II. DATA WILAYAH IUP"))
    rows2 = [
        ["Nama Wilayah",       data.get('nama_wilayah','-')],
        ["Lokasi",             data.get('lokasi','-')],
        ["Komoditas",          f"{data.get('komoditas','-')} ({info['klasifikasi']})"],
        ["Luas Wilayah",       f"{data.get('luas_ha',0):,.4f} Ha"],
        ["Luas Maks. Produksi",info['luas_max_produksi']],
        ["Jangka Waktu",       info['jangka_produksi']],
        ["Rencana Produksi",   data.get('rencana_produksi','-')],
    ]
    _info_table(story, rows2, P)

    story.append(Spacer(1, 0.3*cm))
    story.append(section("III. KOORDINAT WILAYAH"))
    story.append(P(data.get('koordinat_text','-'),
                   fontSize=9, fontName='Courier', leading=14))

    story.append(Spacer(1, 0.3*cm))
    story.append(section("IV. PERNYATAAN TEKNIS AHLI"))
    story.append(P(
        f"Saya yang bertanda tangan, <b>{data.get('nama_ahli','[Nama Ahli]')}</b>, "
        f"dengan keahlian {data.get('keahlian','Ahli Geologi/Pertambangan')}, "
        f"No. Sertifikat: {data.get('nomor_sertifikat','-')}, menyatakan bahwa "
        f"wilayah yang dimohon layak untuk kegiatan Operasi Produksi "
        f"{data.get('komoditas','')}.",
        fontSize=10, leading=15, alignment=TA_JUSTIFY
    ))
    narasi = data.get('narasi_teknis','')
    if narasi:
        story.append(Spacer(1, 0.2*cm))
        for line in narasi.split('\n'):
            line = line.strip()
            if not line: continue
            story.append(P(line, fontSize=10, leading=15, alignment=TA_JUSTIFY))
    return story


def _info_table(story, rows, P):
    t = Table(
        [[P(r[0], fontSize=9, fontName='Helvetica-Bold', textColor=C_SUBTEXT),
          P(str(r[1]), fontSize=9)] for r in rows],
        colWidths=[4.5*cm, 11.5*cm]
    )
    t.setStyle(TableStyle([
        ('GRID',        (0,0),(-1,-1), 0.3, HexColor("#dddddd")),
        ('ROWPADDING',  (0,0),(-1,-1), 6),
        ('LEFTPADDING', (0,0),(-1,-1), 8),
        ('BACKGROUND',  (0,0),(0,-1),  C_LIGHT),
    ]))
    story.append(t)
