"""Fase 14 moved TOOL_SCHEMAS/EXPOSED_TOOL_NAMES from core/chat/tool_schemas.py
to agent/tools/tool_schemas.py (so agents/generic_agent.py can reuse them
without importing from core/chat/, an inverted dependency direction). This
just proves the re-export is a real identity, not a stale copy that could
silently drift.
"""
from agent.tools.tool_schemas import EXPOSED_TOOL_NAMES as canonical_names
from agent.tools.tool_schemas import TOOL_SCHEMAS as canonical_schemas
from core.chat.tool_schemas import EXPOSED_TOOL_NAMES as reexported_names
from core.chat.tool_schemas import TOOL_SCHEMAS as reexported_schemas


def test_core_chat_tool_schemas_is_the_same_object_as_the_canonical_one():
    assert reexported_schemas is canonical_schemas
    assert reexported_names is canonical_names


def test_run_orchestrated_workflow_still_exposed_to_chat():
    assert "run_orchestrated_workflow" in canonical_names
