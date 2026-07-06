"""Regression tripwire (Tahap 37): moving inline prompts into
prompts/<agent>/<name>_v<N>.md must not silently change or truncate the
text that drives live model behavior. These assertions are independent of
the .md files themselves (hardcoded expected substrings), so a future
edit that drops content will fail here even if the loader itself works.
"""
from agent.core import PLANNER_SYSTEM
from core.ai.prompt_templates import (
    GEMMA_SYSTEM_GENERAL,
    GEMMA_SYSTEM_GIS,
    GEMMA_SYSTEM_MINING,
    PromptTemplate,
)
from core.chat.engine import SYSTEM_PROMPT


def test_chat_system_prompt_retains_key_rules():
    assert "ATURAN:" in SYSTEM_PROMPT
    assert "workspace_write_file" in SYSTEM_PROMPT
    assert "total_area_ha" in SYSTEM_PROMPT
    assert "JANGAN PERNAH mengarang angka" in SYSTEM_PROMPT


def test_planner_system_retains_tool_placeholder_and_rules():
    assert "TOOLS:\n{tools}" in PLANNER_SYSTEM
    assert "HANYA JSON valid" in PLANNER_SYSTEM
    assert '{{"tool": "DONE"}}' in PLANNER_SYSTEM


def test_gemma_system_prompts_retain_domain_expertise():
    assert "Regulasi pertambangan Indonesia" in GEMMA_SYSTEM_MINING
    assert "Shapefile, GeoJSON" in GEMMA_SYSTEM_GIS
    assert "akurat, terstruktur" in GEMMA_SYSTEM_GENERAL


def test_prompt_template_members_retain_variables():
    assert "$data" in PromptTemplate.GEOLOGICAL_SUMMARY.value
    assert "$coordinates" in PromptTemplate.WIUP_AREA_ANALYSIS.value
    assert "$text" in PromptTemplate.DOCUMENT_SUMMARIZE.value
    assert "$max_words" in PromptTemplate.DOCUMENT_SUMMARIZE.value
