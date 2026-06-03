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

    def execute(self, name: str, input_data: Any) -> Any:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not in registry. Available: {list(self._tools.keys())}")
        fn = self._tools[name]
        if input_data is None: return fn()
        elif isinstance(input_data, dict): return fn(**input_data)
        else: return fn(input_data)

registry = ToolRegistry()

def build_registry(ollama_url: str, model: str) -> ToolRegistry:
    from agent.tools.readers import read_pdf, read_txt, read_docx, read_csv, read_json, read_image
    from agent.tools.writers import write_docx, write_txt, write_json, write_html, write_pdf
    from agent.tools.analyzers import make_analyzer
    from agent.tools.gis_io import (
        read_geojson, read_shp, write_geojson, write_shp, convert_geo, _summarize_fc,
    )
    from agent.tools.images import (
        image_convert, image_resize, image_crop, image_rotate, image_compress, images_to_pdf,
    )
    from core.gis.processor import KMLProcessor, haversine_area_ha, centroid, bbox

    analyze_text = make_analyzer(ollama_url=ollama_url, model=model)

    # GIS tools (dari ai_engine existing)
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

    # Readers
    registry.register("read_pdf",   read_pdf,   "Baca dan ekstrak teks dari PDF. Input: file_path", ["pdf"])
    registry.register("read_txt",   read_txt,   "Baca file teks/markdown. Input: file_path", ["txt","md","log"])
    registry.register("read_docx",  read_docx,  "Baca dokumen Word. Input: file_path", ["docx","doc"])
    registry.register("read_csv",   read_csv,   "Baca file CSV. Input: file_path", ["csv"])
    registry.register("read_json",  read_json,  "Baca file JSON. Input: file_path", ["json"])
    registry.register("read_image", read_image, "OCR + metadata gambar. Input: file_path", ["jpg","jpeg","png","webp","tif","tiff","bmp","gif"])
    registry.register("read_kml",   gis_parse_kml, "Parse file KML polygon. Input: file_path", ["kml"])
    registry.register("read_geojson", read_geojson, "Baca GeoJSON + ringkas luas/centroid. Input: file_path", ["geojson"])
    registry.register("read_shp",   read_shp,   "Baca Shapefile (.shp atau .zip) + ringkas. Input: file_path", ["shp","zip"])

    # GIS
    registry.register("calculate_area", gis_calculate_area, "Hitung luas polygon (Ha). Input: coordinates [[lon,lat],...]")
    registry.register("write_geojson", write_geojson, "Tulis GeoJSON. Input: {filename, data}")
    registry.register("write_shp", write_shp, "Tulis Shapefile (zip). Input: {filename, data: GeoJSON}")
    registry.register("convert_geo", convert_geo, "Konversi GIS antar format. Input: {file_path, to_format: geojson|kml|shp, filename?}")

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

    # Code generator
    async def generate_code_sync(language, requirement, context=""):
        from agent.tools.analyzers import make_code_generator
        gen = make_code_generator(ollama_url=ollama_url, model=model)
        return gen(language=language, requirement=requirement, context=context)

    import asyncio
    def generate_code(language, requirement, context=""):
        from agent.tools.analyzers import make_code_generator
        gen = make_code_generator(ollama_url=ollama_url, model=model)
        return gen(language=language, requirement=requirement, context=context)

    registry.register("generate_code", generate_code,
        "Generate kode program. Input: {language: html|js|python|sql|css, requirement: str, context: str}")

    return registry
