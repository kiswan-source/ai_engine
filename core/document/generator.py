"""
core/document/generator.py
Main document generator — menghubungkan data ke template
"""
import os, sys, json, csv, io
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

def _ts(): return datetime.now().strftime("%Y%m%d_%H%M%S")

# ── 1. LAPORAN WILAYAH dari KML ────────────────────────────
def generate_laporan_wilayah(kml_content: str, extra: dict = {}) -> dict:
    from core.gis.processor import KMLProcessor
    from templates.laporan_wilayah import build_laporan_wilayah

    polygons = KMLProcessor.parse(kml_content)
    if not polygons:
        raise ValueError("Tidak ada polygon ditemukan dalam file KML")

    poly = polygons[0]
    coords = poly.get("coordinates", [])
    coord_list = [{"lat": c[1], "lon": c[0]} for c in coords]

    data = {
        "nama_wilayah":   extra.get("nama_wilayah", poly.get("name", "Wilayah Tambang")),
        "nama_pemilik":   extra.get("nama_pemilik", "-"),
        "lokasi":         extra.get("lokasi", "-"),
        "komoditas":      extra.get("komoditas", "-"),
        "koordinat":      coord_list,
        "luas_ha":        poly.get("area_ha", 0),
        "luas_m2":        poly.get("area_ha", 0) * 10000,
        "centroid":       poly.get("centroid", {}),
        "bbox":           poly.get("bbox", {}),
        "jumlah_titik":   poly.get("vertex_count", len(coord_list)),
        "deskripsi_ai":   extra.get("deskripsi_ai", ""),
        "tanggal":        datetime.now().strftime("%d %B %Y"),
        "nomor_laporan":  extra.get("nomor_laporan", f"LW-{_ts()}-001"),
    }

    out = str(REPORTS_DIR / f"laporan_wilayah_{_ts()}.pdf")
    build_laporan_wilayah(data, out)
    return {"success": True, "file": out, "filename": Path(out).name,
            "luas_ha": data["luas_ha"], "jumlah_titik": data["jumlah_titik"],
            "data": data}

# ── 2. LAPORAN PRODUKSI dari CSV ───────────────────────────
def generate_laporan_produksi(csv_content: str, extra: dict = {}) -> dict:
    from templates.laporan_produksi import build_laporan_produksi

    rows = list(csv.DictReader(io.StringIO(csv_content)))
    if not rows:
        raise ValueError("File CSV kosong atau format tidak valid")

    # Auto-detect kolom
    keys = [k.lower().strip() for k in rows[0].keys()]
    col_periode   = _find_col(keys, ['periode','bulan','month','tanggal','date','waktu'])
    col_target    = _find_col(keys, ['target','rencana','plan'])
    col_realisasi = _find_col(keys, ['realisasi','aktual','actual','produksi','hasil'])
    col_satuan    = _find_col(keys, ['satuan','unit','uom'])

    prod_data = []
    total_target = total_real = 0
    anomali = []
    orig_keys = list(rows[0].keys())

    for row in rows:
        rk = {k.lower().strip(): v for k, v in row.items()}
        periode = rk.get(col_periode, "-") if col_periode else "-"
        try:
            tgt  = float(str(rk.get(col_target, "0") or "0").replace(",", ""))
            real = float(str(rk.get(col_realisasi, "0") or "0").replace(",", ""))
        except:
            tgt = real = 0
        satuan = rk.get(col_satuan, "Ton") if col_satuan else extra.get("satuan", "Ton")
        prod_data.append({"periode": periode, "target": tgt, "realisasi": real, "satuan": satuan})
        total_target += tgt
        total_real   += real
        if tgt > 0 and (real / tgt) < 0.7:
            anomali.append({"periode": periode,
                            "keterangan": f"Realisasi hanya {real/tgt*100:.1f}% dari target"})

    satuan_final = prod_data[0]["satuan"] if prod_data else extra.get("satuan", "Ton")
    pct_overall  = (total_real / total_target * 100) if total_target > 0 else 0
    if pct_overall > 105:   tren = "naik"
    elif pct_overall < 90:  tren = "turun"
    else:                   tren = "stabil"

    data = {
        "nama_perusahaan":  extra.get("nama_perusahaan", "-"),
        "lokasi":           extra.get("lokasi", "-"),
        "komoditas":        extra.get("komoditas", "-"),
        "periode":          extra.get("periode", f"Periode {datetime.now().year}"),
        "tahun":            extra.get("tahun", str(datetime.now().year)),
        "nomor_laporan":    extra.get("nomor_laporan", f"LP-{_ts()}-001"),
        "data_produksi":    prod_data,
        "total_target":     total_target,
        "total_realisasi":  total_real,
        "satuan":           satuan_final,
        "anomali":          anomali,
        "tren":             tren,
        "narasi_ai":        extra.get("narasi_ai", ""),
        "rekomendasi":      extra.get("rekomendasi", []),
    }

    out = str(REPORTS_DIR / f"laporan_produksi_{_ts()}.pdf")
    build_laporan_produksi(data, out)
    return {"success": True, "file": out, "filename": Path(out).name,
            "total_target": total_target, "total_realisasi": total_real,
            "tren": tren, "anomali_count": len(anomali), "data": data}

# ── 3. DOKUMEN WIUP ────────────────────────────────────────
def generate_dokumen_wiup(form_data: dict) -> dict:
    from templates.dokumen_wiup import build_dokumen_wiup

    jenis = form_data.get("jenis_dokumen", "permohonan_wiup")
    nama_map = {
        "permohonan_wiup":    "permohonan_wiup",
        "laporan_eksplorasi": "laporan_eksplorasi",
        "permohonan_iup_op":  "permohonan_iup_op",
    }
    prefix = nama_map.get(jenis, "dokumen_wiup")
    out = str(REPORTS_DIR / f"{prefix}_{_ts()}.pdf")
    build_dokumen_wiup(form_data, out)
    return {"success": True, "file": out, "filename": Path(out).name}

# ── AI Enrichment (panggil Gemma) ──────────────────────────
async def enrich_with_ai(prompt: str, system: str = "") -> str:
    try:
        from core.ai.gemma_client import gemma
        result = await gemma.generate(prompt=prompt, system=system, temperature=0.4)
        return result or ""
    except Exception as e:
        return f"[AI tidak tersedia: {e}]"

# ── Helper ─────────────────────────────────────────────────
def _find_col(keys: list, candidates: list) -> str | None:
    for c in candidates:
        for k in keys:
            if c in k: return k
    return None
