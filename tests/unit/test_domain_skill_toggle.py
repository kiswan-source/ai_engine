"""Domain Skill toggle (Fase 5, DCF v5 mandate "Domain Generalization") —
proves, rather than just claims, that the core platform doesn't need
mining/GIS: ENABLE_MINING_GIS_SKILL=False must drop every mining/GIS tool
and router while everything else (core tools, chat, orchestrator, memory,
workspace) keeps working unchanged.
"""
import importlib

import pytest

from agent.tools.registry import build_core_registry, build_registry, register_mining_gis_tools

_MINING_GIS_TOOL_NAMES = {"read_kml", "read_geojson", "read_shp", "calculate_area", "write_geojson", "write_shp", "convert_geo"}
_CORE_TOOL_NAMES = {
    "read_pdf", "read_txt", "read_docx", "read_csv", "read_json", "read_image",
    "image_convert", "image_resize", "image_crop", "image_rotate", "image_compress", "images_to_pdf",
    "analyze_text", "write_docx", "write_pdf", "write_html", "write_txt", "write_json", "generate_code",
    "plugin_weather", "mcp_list_tools", "mcp_call_tool",
    "workspace_list_files", "workspace_read_file", "workspace_write_file",
    "remember_fact", "recall_facts",
}


def test_build_core_registry_has_no_mining_gis_tools():
    reg = build_core_registry("http://localhost:11434", "gemma4:e2b")
    tools = set(reg.list_tools())
    assert _CORE_TOOL_NAMES <= tools
    assert not (_MINING_GIS_TOOL_NAMES & tools)


def test_register_mining_gis_tools_adds_exactly_the_domain_tools():
    reg = build_core_registry("http://localhost:11434", "gemma4:e2b")
    register_mining_gis_tools(reg, "http://localhost:11434", "gemma4:e2b")
    tools = set(reg.list_tools())
    assert _MINING_GIS_TOOL_NAMES <= tools


def test_build_registry_gated_by_setting(monkeypatch):
    monkeypatch.setattr("api.config.settings.ENABLE_MINING_GIS_SKILL", True)
    with_skill = set(build_registry("http://localhost:11434", "gemma4:e2b").list_tools())
    assert _MINING_GIS_TOOL_NAMES <= with_skill
    assert _CORE_TOOL_NAMES <= with_skill

    monkeypatch.setattr("api.config.settings.ENABLE_MINING_GIS_SKILL", False)
    without_skill = set(build_registry("http://localhost:11434", "gemma4:e2b").list_tools())
    assert not (_MINING_GIS_TOOL_NAMES & without_skill)
    # Every core tool is still there — the platform doesn't degrade, just
    # loses the one domain skill.
    assert _CORE_TOOL_NAMES <= without_skill


@pytest.fixture
def app_without_mining_gis_skill(monkeypatch):
    """Reloads api.main with the flag off, so the module-level
    app.include_router(...) calls actually re-run under the new setting —
    router registration happens at import time, not per-request. Restores
    both the setting and the router set on teardown so no other test in
    the suite (many of which do `from api.main import app`) is affected."""
    import api.main as main_module

    monkeypatch.setattr("api.config.settings.ENABLE_MINING_GIS_SKILL", False)
    importlib.reload(main_module)
    try:
        yield main_module.app
    finally:
        monkeypatch.undo()
        importlib.reload(main_module)


def test_gis_dokumen_pipeline_routes_absent_when_skill_disabled(app_without_mining_gis_skill):
    paths = {route.path for route in app_without_mining_gis_skill.routes}
    assert not any(p.startswith("/api/v1/gis") for p in paths)
    assert not any(p.startswith("/api/v1/pipeline") for p in paths)
    assert not any(p.startswith("/api/dokumen") for p in paths)


def test_core_routes_still_present_when_mining_gis_skill_disabled(app_without_mining_gis_skill):
    """The actual proof: chat, orchestrator, memory, workspace, projects,
    automation, plugins, knowledge, monitoring, agent, docs, health, files —
    none of them depend on the mining/GIS domain skill being enabled."""
    paths = {route.path for route in app_without_mining_gis_skill.routes}
    for prefix in (
        "/api/v1/chat", "/api/v1/orchestrator", "/api/v1/memory", "/api/v1/workspace",
        "/api/v1/projects", "/api/v1/automation", "/api/v1/plugins", "/api/v1/knowledge",
        "/api/v1/monitoring", "/api/v1/agent", "/api/v1/docs", "/health",
    ):
        assert any(p.startswith(prefix) for p in paths), f"{prefix} missing with mining/GIS skill disabled"
