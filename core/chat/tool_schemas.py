"""
JSON-schema descriptions of the agent tools, in the shape Ollama's /api/chat
`tools` parameter expects. Curated + explicitly typed so a small local model
(gemma4:e2b) can call them reliably.

Tool names here MUST match the names registered in agent/tools/registry.py.
"""

def _fn(name: str, description: str, properties: dict, required: list) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}

TOOL_SCHEMAS = [
    # ── Readers ──
    _fn("read_pdf", "Baca/ekstrak teks dari file PDF.",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_docx", "Baca dokumen Word (.docx).",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_csv", "Baca file CSV (header + baris).",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_txt", "Baca file teks/markdown.",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_json", "Baca file JSON.",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_image", "Baca metadata + OCR teks dari gambar.",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_kml", "Parse KML → polygon, luas (Ha), centroid.",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_geojson", "Baca GeoJSON → ringkas luas/centroid.",
        {"file_path": _STR}, ["file_path"]),
    _fn("read_shp", "Baca Shapefile (.shp atau .zip) → ringkas.",
        {"file_path": _STR}, ["file_path"]),

    # ── Writers (dokumen) ──
    _fn("write_pdf", "Buat laporan PDF dari teks markdown.",
        {"filename": _STR, "title": _STR, "content": _STR}, ["filename", "content"]),
    _fn("write_docx", "Buat dokumen Word dari teks markdown.",
        {"filename": _STR, "title": _STR, "content": _STR}, ["filename", "content"]),
    _fn("write_html", "Buat file HTML.",
        {"filename": _STR, "content": _STR}, ["filename", "content"]),
    _fn("write_txt", "Simpan teks ke file .txt.",
        {"filename": _STR, "content": _STR}, ["filename", "content"]),

    # ── GIS ──
    _fn("convert_geo", "Konversi file GIS antar format (KML/GeoJSON/SHP).",
        {"file_path": _STR,
         "to_format": {"type": "string", "enum": ["geojson", "kml", "shp"]},
         "filename": _STR},
        ["file_path", "to_format"]),
    _fn("write_geojson", "Tulis data GeoJSON ke file.",
        {"filename": _STR, "data": {"type": "object"}}, ["filename", "data"]),
    _fn("write_shp", "Tulis GeoJSON ke Shapefile (zip).",
        {"filename": _STR, "data": {"type": "object"}}, ["filename", "data"]),

    # ── Image transforms ──
    _fn("image_convert", "Konversi format gambar.",
        {"file_path": _STR,
         "to_format": {"type": "string", "enum": ["jpg", "png", "tiff", "webp", "bmp", "gif"]},
         "filename": _STR},
        ["file_path", "to_format"]),
    _fn("image_resize", "Resize gambar (px). Beri width dan/atau height.",
        {"file_path": _STR, "width": _INT, "height": _INT, "filename": _STR},
        ["file_path"]),
    _fn("image_crop", "Crop gambar ke kotak (px).",
        {"file_path": _STR, "left": _INT, "top": _INT, "right": _INT, "bottom": _INT,
         "filename": _STR},
        ["file_path", "left", "top", "right", "bottom"]),
    _fn("image_rotate", "Rotasi gambar (derajat).",
        {"file_path": _STR, "degrees": _NUM, "filename": _STR},
        ["file_path", "degrees"]),
    _fn("image_compress", "Kompres gambar untuk perkecil ukuran (quality 1-95).",
        {"file_path": _STR, "quality": _INT, "filename": _STR},
        ["file_path"]),
    _fn("images_to_pdf", "Gabungkan beberapa gambar menjadi satu PDF.",
        {"file_paths": {"type": "array", "items": _STR}, "filename": _STR},
        ["file_paths"]),

    # ── Plugins (Bab 59) ──
    _fn("plugin_weather", "Cuaca saat ini (suhu/curah hujan/angin) untuk sebuah lokasi.",
        {"latitude": _NUM, "longitude": _NUM}, ["latitude", "longitude"]),

    # ── MCP (Bab 60) ──
    _fn("mcp_list_tools", "Daftar tool yang tersedia di sebuah MCP server terkonfigurasi.",
        {"server": _STR}, ["server"]),
    _fn("mcp_call_tool", "Panggil satu tool di MCP server (pakai mcp_list_tools dulu untuk lihat nama & argumennya).",
        {"server": _STR, "tool_name": _STR, "arguments": {"type": "object"}},
        ["server", "tool_name"]),
]

# Quick lookup of which tools we expose to the model.
EXPOSED_TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}
