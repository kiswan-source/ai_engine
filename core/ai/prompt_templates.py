"""
Prompt templates optimised for Gemma 4:26B instruction format.
Gemma uses <start_of_turn>user / <start_of_turn>model convention.

Prompt Versioning (Bab 51, Tahap 37) — every template/system prompt below
is loaded from prompts/<agent>/<name>_v<N>.md rather than embedded inline;
version is registered explicitly at each call site, never inferred from
the highest version number on disk.
"""
from enum import Enum
from string import Template

from prompts.loader import load_prompt


class PromptTemplate(str, Enum):
    """Pre-built prompts for common AI Engine tasks."""

    # ── GIS / Mining ──────────────────────────────────────────────────────────
    GEOLOGICAL_SUMMARY = load_prompt("templates", "geological_summary", version=1)
    WIUP_AREA_ANALYSIS = load_prompt("templates", "wiup_area_analysis", version=1)

    # ── Document Processing ───────────────────────────────────────────────────
    DOCUMENT_SUMMARIZE = load_prompt("templates", "document_summarize", version=1)
    DOCUMENT_EXTRACT_ENTITIES = load_prompt("templates", "document_extract_entities", version=1)

    # ── Report Generation ─────────────────────────────────────────────────────
    FIELD_INSPECTION_REPORT = load_prompt("templates", "field_inspection_report", version=1)

    # ── General ───────────────────────────────────────────────────────────────
    QA_WITH_CONTEXT = load_prompt("templates", "qa_with_context", version=1)
    TRANSLATE_TO_ENGLISH = load_prompt("templates", "translate_to_english", version=1)
    CLASSIFY_DOCUMENT = load_prompt("templates", "classify_document", version=1)


def render(template: PromptTemplate, **kwargs) -> str:
    """Render a prompt template with given variables."""
    return Template(template.value).safe_substitute(**kwargs)


GEMMA_SYSTEM_MINING = load_prompt("system", "mining", version=1)
GEMMA_SYSTEM_GIS = load_prompt("system", "gis", version=1)
GEMMA_SYSTEM_GENERAL = load_prompt("system", "general", version=1)
