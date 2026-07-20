"""Central tool registry — no tool executes outside this."""
import os
from typing import Callable, Dict, Any, Optional

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}
        self._ext_map: Dict[str, str] = {}

    def register(self, name: str, func: Callable, description: str, extensions: list = None):
        self._tools[name] = func
        self._descriptions[name] = description
        if extensions:
            for ext in extensions:
                self._ext_map[ext.lower()] = name

    def get(self, name: str): return self._tools.get(name)
    def has(self, name: str): return name in self._tools
    def list_tools(self): return dict(self._descriptions)
    def auto_reader(self, file_path: str) -> Optional[str]:
        ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        return self._ext_map.get(ext)

    def schema_for_planner(self) -> str:
        return "\n".join(f"- {n}: {d}" for n, d in self._descriptions.items())

    def execute(self, name: str, input_data: Any, role: Optional[str] = None) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not in registry. Available: {list(self._tools.keys())}")
        if role is not None:
            # RBAC pilot (Bab 30 rule 2, ADR-0013) — no-op for callers that
            # don't pass a role (e.g. core/chat/, unchanged) and for tools
            # outside TOOL_RISK_ACTIONS (everything but write_pdf, for now).
            from security.permissions import check_tool_permission
            check_tool_permission(role, name)
        fn = self._tools[name]
        if input_data is None: return fn()
        elif isinstance(input_data, dict): return fn(**input_data)
        else: return fn(input_data)


def build_core_registry(ollama_url: str, model: str) -> ToolRegistry:
    """Domain-agnostic tools — everything the platform needs regardless of
    which domain skill(s) are enabled (Fase 5, DCF v5 mandate "Domain
    Generalization"). Mining/GIS tools are deliberately NOT here — see
    :func:`register_mining_gis_tools` and :func:`build_registry`.

    A FRESH ToolRegistry per call — not the module-level `registry`
    singleton this file used to mutate directly, which silently broke the
    Fase 5 toggle: a tool registered on a shared object in one call is
    never removed by a later call with ENABLE_MINING_GIS_SKILL=False,
    caught live by tests/unit/test_domain_skill_toggle.py."""
    registry = ToolRegistry()
    from agent.tools.readers import read_pdf, read_txt, read_docx, read_csv, read_json, read_image, read_xlsx, read_pptx
    from agent.tools.writers import write_docx, write_txt, write_json, write_html, write_pdf, write_xlsx, write_pptx
    from agent.tools.analyzers import make_analyzer
    from agent.tools.images import (
        image_convert, image_resize, image_crop, image_rotate, image_compress, images_to_pdf,
    )

    analyze_text = make_analyzer(ollama_url=ollama_url, model=model)

    # Readers
    registry.register("read_pdf",   read_pdf,   "Baca dan ekstrak teks dari PDF. Input: file_path", ["pdf"])
    registry.register("read_txt",   read_txt,   "Baca file teks/markdown. Input: file_path", ["txt","md","log"])
    registry.register("read_docx",  read_docx,  "Baca dokumen Word. Input: file_path", ["docx","doc"])
    registry.register("read_csv",   read_csv,   "Baca file CSV. Input: file_path", ["csv"])
    registry.register("read_json",  read_json,  "Baca file JSON. Input: file_path", ["json"])
    registry.register("read_image", read_image, "OCR + metadata gambar. Input: file_path", ["jpg","jpeg","png","webp","tif","tiff","bmp","gif"])
    # Workspace Slice 3 (Fase 12)
    registry.register("read_xlsx", read_xlsx, "Baca isi spreadsheet Excel (per-sheet). Input: file_path", ["xlsx"])
    registry.register("read_pptx", read_pptx, "Baca isi presentasi PowerPoint (per-slide). Input: file_path", ["pptx"])

    # Image transforms (Pillow) — bukan generasi gambar
    registry.register("image_convert", image_convert, "Konversi format gambar. Input: {file_path, to_format: jpg|png|tiff|webp|bmp|gif, filename?}")
    registry.register("image_resize", image_resize, "Resize gambar. Input: {file_path, width?, height?, filename?}")
    registry.register("image_crop", image_crop, "Crop gambar. Input: {file_path, left, top, right, bottom, filename?}")
    registry.register("image_rotate", image_rotate, "Rotasi gambar. Input: {file_path, degrees, filename?}")
    registry.register("image_compress", image_compress, "Kompres gambar (perkecil ukuran). Input: {file_path, quality, filename?}")
    registry.register("images_to_pdf", images_to_pdf, "Gabung gambar jadi PDF. Input: {file_paths: [..], filename}")

    # Analyzer
    registry.register("analyze_text", analyze_text, "Analisis teks dengan AI Gemma. Input: {text, instruction}")

    # Writers
    registry.register("write_docx", write_docx, "Buat dokumen Word. Input: {filename, title, content}")
    registry.register("write_pdf",  write_pdf,  "Buat laporan PDF. Input: {filename, title, content}")
    registry.register("write_html", write_html, "Buat file HTML. Input: {filename, content}")
    registry.register("write_txt",  write_txt,  "Simpan teks. Input: {filename, content}")
    registry.register("write_json", write_json, "Simpan JSON. Input: {filename, data}")
    # Workspace Slice 3 (Fase 12) — same {filename, title, content} markdown
    # input as write_docx/write_pdf; H1 headings become new sheets/slides.
    registry.register("write_xlsx", write_xlsx,
        "Buat spreadsheet Excel dari teks markdown (heading H1 jadi sheet baru, tabel jadi baris). Input: {filename, title, content}")
    registry.register("write_pptx", write_pptx,
        "Buat presentasi PowerPoint dari teks markdown (heading H1 jadi slide baru, tabel jadi slide tabel terpisah). Input: {filename, title, content}")

    # Code generator
    def generate_code(language, requirement, context=""):
        from agent.tools.analyzers import make_code_generator
        gen = make_code_generator(ollama_url=ollama_url, model=model)
        return gen(language=language, requirement=requirement, context=context)

    registry.register("generate_code", generate_code,
        "Generate kode program. Input: {language: html|js|python|sql|css, requirement: str, context: str}")

    # Plugins (Bab 59) — one tool per plugin, toggled via registry/plugin_registry.py
    # (its own, separate enable/disable mechanism from Domain Skills).
    def plugin_weather(latitude: float, longitude: float):
        from registry.plugin_registry import get as get_plugin
        plugin = get_plugin("weather")
        if plugin is None:
            return {"success": False, "error": "Plugin 'weather' dinonaktifkan atau tidak ditemukan."}
        return plugin.execute(latitude=latitude, longitude=longitude)

    registry.register("plugin_weather", plugin_weather,
        "Cuaca saat ini (suhu/curah hujan/angin) untuk sebuah lokasi. Input: {latitude, longitude}")

    # MCP (Bab 60) — bridge to Model Context Protocol servers via mcp_client/.
    def mcp_list_tools(server: str):
        from api.config import settings
        if not settings.ENABLE_MCP:
            return {"success": False, "error": "MCP dinonaktifkan (ENABLE_MCP=False)."}
        from mcp_client.config import MCP_SERVERS
        from mcp_client.client import MCPClient
        command = MCP_SERVERS.get(server)
        if command is None:
            return {"success": False, "error": f"MCP server '{server}' tidak dikonfigurasi."}
        import asyncio
        return asyncio.run(MCPClient(command).list_tools())

    def mcp_call_tool(server: str, tool_name: str, arguments: dict = None):
        from api.config import settings
        if not settings.ENABLE_MCP:
            return {"success": False, "error": "MCP dinonaktifkan (ENABLE_MCP=False)."}
        from mcp_client.config import MCP_SERVERS
        from mcp_client.client import MCPClient
        command = MCP_SERVERS.get(server)
        if command is None:
            return {"success": False, "error": f"MCP server '{server}' tidak dikonfigurasi."}
        import asyncio
        return asyncio.run(MCPClient(command).call_tool(tool_name, arguments or {}))

    registry.register("mcp_list_tools", mcp_list_tools,
        "Daftar tool yang tersedia di sebuah MCP server. Input: {server}")
    registry.register("mcp_call_tool", mcp_call_tool,
        "Panggil satu tool di MCP server. Input: {server, tool_name, arguments}")

    # Agent Workspace Context (Bab 69.5, Tahap 23) — workspace_id is always
    # injected by ChatEngine._run_tool from the session's authorized
    # Workspace, never taken from the model's own arguments.
    from agent.tools.workspace_reader import (
        workspace_copy_file,
        workspace_create_folder,
        workspace_find_file,
        workspace_list_files,
        workspace_move_file,
        workspace_read_file,
        workspace_write_file,
    )
    registry.register("workspace_list_files", workspace_list_files,
        "Daftar semua file di Project Workspace yang terhubung ke sesi ini. Input: {}")
    registry.register("workspace_read_file", workspace_read_file,
        "Baca isi satu file dari Project Workspace. Input: {folder_id, relative_path}")
    # Workspace Write Access (Bab 69.7 write_output, Tahap 30) — same
    # workspace_id injection rule as the two tools above; ChatEngine._run_tool
    # also checks the write_output permission before this ever runs.
    registry.register("workspace_write_file", workspace_write_file,
        "Buat/timpa/tambah satu file teks di Project Workspace. Input: {folder_id, relative_path, content, mode}")
    # Fase 8 (DCF v5 mandate "Workspace Native File Access", Slice 1) — Smart
    # Search is read-only (no write_output check, same posture as
    # workspace_list_files/workspace_read_file); create/move/copy are
    # mutations gated on write_output the same as workspace_write_file.
    registry.register("workspace_find_file", workspace_find_file,
        "Cari file berdasarkan nama (Smart Search) di seluruh folder Project Workspace. Input: {filename}")
    registry.register("workspace_create_folder", workspace_create_folder,
        "Buat folder baru di dalam Project Workspace. Input: {folder_id, relative_path}")
    registry.register("workspace_move_file", workspace_move_file,
        "Pindahkan atau ganti nama satu file/folder di dalam Project Workspace. "
        "Input: {folder_id, src_relative_path, dst_relative_path, overwrite?}")
    registry.register("workspace_copy_file", workspace_copy_file,
        "Salin satu file/folder di dalam Project Workspace ke path lain. "
        "Input: {folder_id, src_relative_path, dst_relative_path, overwrite?}")

    # Cross-session memory (Fase 3, DCF v5 mandate) — owner is always
    # injected by ChatEngine._run_tool, never taken from the model. See
    # agent/tools/memory_tools.py module docstring for the full rationale.
    from agent.tools.memory_tools import remember_fact, recall_facts
    registry.register("remember_fact", remember_fact,
        "Simpan satu fakta/preferensi permanen tentang pengguna, bisa diambil lagi di sesi chat lain. Input: {key, value}")
    registry.register("recall_facts", recall_facts,
        "Ambil semua fakta yang pernah diminta pengguna untuk diingat. Input: {}")

    # Chat -> Orchestrator bridge (Fase 6, DCF v5 mandate "Cowork Experience")
    # — see agent/tools/orchestrator_tools.py module docstring.
    from agent.tools.orchestrator_tools import run_orchestrated_workflow
    registry.register("run_orchestrated_workflow", run_orchestrated_workflow,
        "Jalankan alur kerja multi-agent penuh (rencana, pilih agent, workflow, validasi, "
        "eskalasi ke persetujuan manusia bila perlu) untuk tugas kompleks. "
        "Input: {goal, roles: [...], mode?}")

    return registry


def register_mining_gis_tools(target: ToolRegistry, ollama_url: str, model: str) -> None:
    """Mining/GIS domain skill (Fase 5) — the platform's first domain skill,
    not a core-engine assumption. Gated by ``settings.ENABLE_MINING_GIS_SKILL``
    in :func:`build_registry`; a deployment with it off keeps every tool in
    :func:`build_core_registry` working unchanged (proven by
    ``tests/unit/test_domain_skill_toggle.py``, not just claimed)."""
    from agent.tools.gis_io import (
        read_geojson, read_shp, write_geojson, write_shp, convert_geo, _summarize_fc,
    )
    from core.gis.processor import KMLProcessor, haversine_area_ha, centroid, bbox

    def gis_calculate_area(coordinates):
        coords = coordinates if isinstance(coordinates, list) else []
        return {"area_ha": haversine_area_ha(coords), "centroid": centroid(coords), "bbox": bbox(coords), "vertex_count": len(coords)}

    def gis_parse_kml(file_path):
        # Return the SAME clean summary shape as read_geojson/read_shp:
        # total_area_ha + per-polygon area/centroid/bbox, plus a compact `text`.
        # Crucially we do NOT dump the full coordinate FeatureCollection into the
        # result — that blob (hundreds of KB) buried the area numbers and made the
        # model unable to answer "berapa luasnya", so it fabricated one.
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            fc = KMLProcessor.to_geojson(content)
            s = _summarize_fc(fc)
            s.update({"source": file_path, "type": "kml"})
            return s
        except Exception as e:
            return {"error": str(e), "source": file_path}

    target.register("read_kml", gis_parse_kml, "Parse file KML polygon. Input: file_path", ["kml"])
    target.register("read_geojson", read_geojson, "Baca GeoJSON + ringkas luas/centroid. Input: file_path", ["geojson"])
    target.register("read_shp", read_shp, "Baca Shapefile (.shp atau .zip) + ringkas. Input: file_path", ["shp", "zip"])
    target.register("calculate_area", gis_calculate_area, "Hitung luas polygon (Ha). Input: coordinates [[lon,lat],...]")
    target.register("write_geojson", write_geojson, "Tulis GeoJSON. Input: {filename, data}")
    target.register("write_shp", write_shp, "Tulis Shapefile (zip). Input: {filename, data: GeoJSON}")
    target.register("convert_geo", convert_geo, "Konversi GIS antar format. Input: {file_path, to_format: geojson|kml|shp, filename?}")


def build_registry(ollama_url: str, model: str) -> ToolRegistry:
    """Core tools + the mining/GIS domain skill if enabled (Fase 5). This is
    still the one entry point every existing caller
    (``core/chat/engine.py``, ``agent/core.py``, ``mcp_server/server.py``)
    uses — the domain-skill split is internal to this module, not a
    breaking change to callers."""
    from api.config import settings

    core = build_core_registry(ollama_url, model)
    if settings.ENABLE_MINING_GIS_SKILL:
        register_mining_gis_tools(core, ollama_url, model)
    return core
