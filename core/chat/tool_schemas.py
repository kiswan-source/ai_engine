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

    # ── Agent Workspace Context (Bab 69.5) ── no workspace_id property on
    # either — ChatEngine injects it from the session, never from the model.
    _fn("workspace_list_files", "Daftar semua file di Project Workspace yang terhubung ke sesi chat ini (folder lokal yang diregistrasikan). Panggil ini dulu sebelum membaca file dari Workspace.",
        {}, []),
    _fn("workspace_read_file", "Baca satu file dari Project Workspace. Dokumen (pdf/txt/docx/csv/json) dikembalikan sebagai teks. Gambar (jpg/png/dll) akan DITAMPILKAN ke kamu sebagai gambar sungguhan pada giliran berikutnya — deskripsikan isinya. File GIS (kml/geojson/shp) dikembalikan sebagai ringkasan luas/centroid. Pakai folder_id dan relative_path PERSIS dari hasil workspace_list_files.",
        {"folder_id": _STR, "relative_path": _STR}, ["folder_id", "relative_path"]),
    _fn("workspace_write_file", "Buat atau edit satu file LANGSUNG di Project Workspace, bukan di folder laporan biasa. Pakai ini saat pengguna minta membuat/mengedit file di dalam Workspace/folder proyek mereka. File TEKS (txt/md/log/csv/json/html): mode='overwrite' (default, ganti seluruh isi) atau mode='append' (tambahkan ke akhir file). File PDF/DOCX SUNGGUHAN: kirim isi sebagai teks markdown di `content` (heading #/##, list -/*, **tebal** didukung), beri `title` (opsional, kalau tak diisi diambil dari nama file) — HANYA mendukung mode='overwrite', append tidak didukung untuk PDF/DOCX. Pakai folder_id PERSIS dari hasil workspace_list_files.",
        {"folder_id": _STR, "relative_path": _STR, "content": _STR,
         "mode": {"type": "string", "enum": ["overwrite", "append"]},
         "title": _STR},
        ["folder_id", "relative_path", "content"]),

    # ── Cross-session memory (Fase 3) — no owner property on either;
    # ChatEngine injects it from the session, never from the model.
    _fn("remember_fact", "Simpan satu fakta atau preferensi permanen tentang pengguna ini, supaya bisa kamu ingat lagi di sesi chat lain di masa depan. HANYA pakai ini kalau pengguna secara eksplisit minta diingat (mis. 'ingat bahwa...', 'simpan preferensi saya...') — jangan panggil otomatis tiap pesan.",
        {"key": _STR, "value": _STR}, ["key", "value"]),
    _fn("recall_facts", "Ambil semua fakta yang pernah diminta pengguna ini untuk diingat, dari sesi chat manapun. Panggil ini kalau pengguna bertanya sesuatu yang mungkin pernah mereka minta kamu ingat sebelumnya.",
        {}, []),

    # ── Chat -> Orchestrator bridge (Fase 6) ──
    _fn("run_orchestrated_workflow",
        "Jalankan alur kerja multi-agent PENUH: rencana, pilih satu atau beberapa agent, jalankan workflow, validasi, dan eskalasi ke persetujuan manusia kalau confidence-nya rendah — BUKAN sekadar satu panggilan tool. Pakai ini untuk permintaan kompleks yang butuh riset+analisis+penulisan berlapis, atau butuh beberapa sudut pandang/agent (mis. 'analisa dokumen ini dari berbagai sisi dan buat laporan lengkap'). JANGAN pakai untuk tugas sederhana satu-langkah (baca file, buat satu dokumen, konversi format) — tool biasa sudah cukup dan lebih cepat/murah untuk itu. roles: daftar peran dari planner/research/analyst/writer/reviewer/vision/reflection/critic/consensus (urutkan sesuai kebutuhan tugas). mode: sequential (berurutan, default), parallel, reflection (agent mengevaluasi ulang jawabannya sendiri), voting (beberapa agent independen, mayoritas menang), consensus (debat terstruktur lalu arbitrase). Hasilnya BUKAN langsung selesai — kalau escalate=true, sampaikan ke pengguna bahwa ini butuh persetujuan manusia di halaman Approval.",
        {"goal": _STR,
         "roles": {"type": "array", "items": _STR},
         "mode": {"type": "string", "enum": ["sequential", "parallel", "reflection", "voting", "consensus"]}},
        ["goal", "roles"]),
]

# Quick lookup of which tools we expose to the model.
EXPOSED_TOOL_NAMES = {t["function"]["name"] for t in TOOL_SCHEMAS}
