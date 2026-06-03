"""
api/routes/dokumen.py
Endpoint untuk 3 modul utama:
1. POST /dokumen/wilayah   - KML → Laporan PDF
2. POST /dokumen/produksi  - CSV → Laporan PDF
3. POST /dokumen/wiup      - Form → Dokumen PDF
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from core.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# ══════════════════════════════════════════════════════════════
# MODUL 1 — LAPORAN WILAYAH
# ══════════════════════════════════════════════════════════════
@router.post("/wilayah")
async def laporan_wilayah(
    file:           UploadFile = File(...),
    nama_wilayah:   str = Form(""),
    nama_pemilik:   str = Form(""),
    lokasi:         str = Form(""),
    komoditas:      str = Form("Batubara"),
    nomor_laporan:  str = Form(""),
    with_ai:        bool = Form(True),
):
    """Upload KML → Generate PDF Laporan Wilayah otomatis."""
    if not file.filename.lower().endswith('.kml'):
        raise HTTPException(400, "File harus berformat KML")

    try:
        kml_content = (await file.read()).decode("utf-8")
        extra = {
            "nama_wilayah":  nama_wilayah or Path(file.filename).stem,
            "nama_pemilik":  nama_pemilik,
            "lokasi":        lokasi,
            "komoditas":     komoditas,
            "nomor_laporan": nomor_laporan,
        }

        # AI enrichment
        if with_ai:
            from core.document.generator import enrich_with_ai
            prompt = (
                f"Buatkan deskripsi wilayah tambang '{extra['nama_wilayah']}' "
                f"di {lokasi} untuk komoditas {komoditas}. "
                f"Jelaskan potensi geologi, aksesibilitas, dan kondisi umum wilayah "
                f"dalam 3-4 paragraf yang profesional dan sesuai format laporan teknis."
            )
            extra["deskripsi_ai"] = await enrich_with_ai(prompt)
            logger.info("AI enrichment done for wilayah")

        from core.document.generator import generate_laporan_wilayah
        result = generate_laporan_wilayah(kml_content, extra)

        logger.info(f"Laporan wilayah generated: {result['filename']}")
        return {
            "success":    True,
            "filename":   result["filename"],
            "file_path":  result["file"],
            "luas_ha":    result["luas_ha"],
            "jumlah_titik": result["jumlah_titik"],
            "download_url": f"/reports/{result['filename']}",
            "message":    f"Laporan wilayah berhasil dibuat: {result['filename']}",
        }

    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Error laporan wilayah: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate laporan: {str(e)}")


# ══════════════════════════════════════════════════════════════
# MODUL 2 — LAPORAN PRODUKSI
# ══════════════════════════════════════════════════════════════
@router.post("/produksi")
async def laporan_produksi(
    file:             UploadFile = File(...),
    nama_perusahaan:  str = Form(""),
    lokasi:           str = Form(""),
    komoditas:        str = Form("Batubara"),
    periode:          str = Form(""),
    tahun:            str = Form(""),
    satuan:           str = Form("Ton"),
    nomor_laporan:    str = Form(""),
    with_ai:          bool = Form(True),
):
    """Upload CSV/Excel → Generate PDF Laporan Produksi."""
    fname = file.filename.lower()
    if not any(fname.endswith(x) for x in ['.csv', '.xlsx', '.xls']):
        raise HTTPException(400, "File harus berformat CSV atau Excel")

    try:
        content = await file.read()

        # Handle Excel
        if fname.endswith(('.xlsx', '.xls')):
            import openpyxl, io, csv as csv_module
            wb = openpyxl.load_workbook(io.BytesIO(content))
            ws = wb.active
            buf = io.StringIO()
            writer = csv_module.writer(buf)
            for row in ws.iter_rows(values_only=True):
                writer.writerow([str(c) if c is not None else "" for c in row])
            csv_content = buf.getvalue()
        else:
            csv_content = content.decode("utf-8-sig")

        from datetime import datetime as dt
        extra = {
            "nama_perusahaan": nama_perusahaan,
            "lokasi":          lokasi,
            "komoditas":       komoditas,
            "periode":         periode or f"Periode {dt.now().year}",
            "tahun":           tahun or str(dt.now().year),
            "satuan":          satuan,
            "nomor_laporan":   nomor_laporan,
        }

        # Generate dulu tanpa AI untuk dapat data
        from core.document.generator import generate_laporan_produksi
        result_pre = generate_laporan_produksi(csv_content, extra)

        # AI enrichment
        if with_ai:
            from core.document.generator import enrich_with_ai
            d = result_pre["data"]
            pct = (d["total_realisasi"]/d["total_target"]*100) if d["total_target"] > 0 else 0
            prompt = (
                f"Buatkan narasi analisa laporan produksi tambang {komoditas} "
                f"untuk {nama_perusahaan} di {lokasi}. "
                f"Data: Target={d['total_target']:,.0f} {satuan}, "
                f"Realisasi={d['total_realisasi']:,.0f} {satuan}, "
                f"Pencapaian={pct:.1f}%, Tren={d['tren']}. "
                f"Anomali ditemukan: {d['anomali_count']} periode. "
                f"Tulis dalam 3-4 paragraf profesional dengan analisa mendalam dan "
                f"rekomendasi konkret sesuai Permen ESDM No. 17 Tahun 2025."
            )
            narasi = await enrich_with_ai(prompt)
            extra["narasi_ai"] = narasi
            # Rekomendasi
            rek_prompt = (
                f"Berikan 5 rekomendasi konkret untuk meningkatkan produksi "
                f"{komoditas} berdasarkan data: pencapaian {pct:.1f}%, tren {d['tren']}. "
                f"Format: satu kalimat per rekomendasi."
            )
            rek_text = await enrich_with_ai(rek_prompt)
            extra["rekomendasi"] = [
                r.strip().lstrip("0123456789.-*• ")
                for r in rek_text.split('\n')
                if r.strip() and len(r.strip()) > 10
            ][:5]

            # Re-generate dengan AI content
            result_pre = generate_laporan_produksi(csv_content, extra)

        logger.info(f"Laporan produksi generated: {result_pre['filename']}")
        return {
            "success":        True,
            "filename":       result_pre["filename"],
            "file_path":      result_pre["file"],
            "total_target":   result_pre["total_target"],
            "total_realisasi":result_pre["total_realisasi"],
            "tren":           result_pre["tren"],
            "anomali_count":  result_pre["anomali_count"],
            "download_url":   f"/reports/{result_pre['filename']}",
            "message":        f"Laporan produksi berhasil dibuat: {result_pre['filename']}",
        }

    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        logger.error(f"Error laporan produksi: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate laporan: {str(e)}")


# ══════════════════════════════════════════════════════════════
# MODUL 3 — DOKUMEN WIUP
# ══════════════════════════════════════════════════════════════
class WIUPRequest(BaseModel):
    jenis_dokumen:    str = "permohonan_wiup"
    komoditas:        str = "Batubara"
    nama_perusahaan:  str = ""
    nib:              str = ""
    npwp:             str = ""
    alamat:           str = ""
    nama_direksi:     str = ""
    jabatan_direksi:  str = "Direktur Utama"
    nama_wilayah:     str = ""
    lokasi:           str = ""
    luas_ha:          float = 0.0
    koordinat_text:   str = ""
    komoditas_teknis: str = ""
    rencana_produksi: str = ""
    nama_ahli:        str = ""
    keahlian:         str = "Ahli Geologi"
    nomor_sertifikat: str = ""
    nomor_surat:      str = ""
    kepada:           str = ""
    with_ai:          bool = True

@router.post("/wiup")
async def dokumen_wiup(req: WIUPRequest):
    """Form data → Generate Dokumen WIUP PDF."""
    try:
        form_data = req.model_dump()

        if req.with_ai:
            from core.document.generator import enrich_with_ai
            prompt = (
                f"Buatkan pernyataan teknis profesional untuk dokumen "
                f"{req.jenis_dokumen.replace('_',' ')} komoditas {req.komoditas} "
                f"({form_data.get('komoditas_teknis','')}) "
                f"di wilayah {req.nama_wilayah}, {req.lokasi}, "
                f"seluas {req.luas_ha:,.2f} Ha. "
                f"Jelaskan potensi geologi, kelayakan teknis, dan rekomendasi "
                f"dalam format dokumen resmi pertambangan Indonesia, "
                f"mengacu UU No. 3 Tahun 2020 dan Permen ESDM No. 18 Tahun 2025."
            )
            form_data["narasi_teknis"] = await enrich_with_ai(prompt)

        from core.document.generator import generate_dokumen_wiup
        result = generate_dokumen_wiup(form_data)

        logger.info(f"Dokumen WIUP generated: {result['filename']}")
        return {
            "success":      True,
            "filename":     result["filename"],
            "file_path":    result["file"],
            "download_url": f"/reports/{result['filename']}",
            "message":      f"Dokumen berhasil dibuat: {result['filename']}",
        }

    except Exception as e:
        logger.error(f"Error dokumen WIUP: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate dokumen: {str(e)}")


# ══════════════════════════════════════════════════════════════
# INFO KOMODITAS
# ══════════════════════════════════════════════════════════════
@router.get("/komoditas")
async def get_komoditas_info():
    """Daftar komoditas dan informasi regulasi."""
    from templates.dokumen_wiup import KOMODITAS_INFO
    return {"komoditas": list(KOMODITAS_INFO.keys()), "detail": KOMODITAS_INFO}


@router.get("/templates")
async def list_templates():
    """Daftar template dokumen tersedia."""
    return {"templates": [
        {"id": "permohonan_wiup",    "label": "Permohonan WIUP",
         "desc": "Surat permohonan wilayah izin usaha pertambangan"},
        {"id": "laporan_eksplorasi", "label": "Laporan Akhir Eksplorasi",
         "desc": "Laporan hasil kegiatan eksplorasi"},
        {"id": "permohonan_iup_op",  "label": "Permohonan IUP Operasi Produksi",
         "desc": "Permohonan peningkatan IUP ke tahap operasi produksi"},
    ]}
