"""Unit tests for Agent Workspace Context wiring in ChatEngine (Bab 69.5,
Tahap 23) — `_run_tool`'s workspace_id injection/override and `stream_run`'s
session-level binding persistence.

Same fake-registry + fake-streaming-Ollama technique as
`test_chat_engine_rbac.py` (`core.chat.engine.build_registry`/
`httpx.AsyncClient` monkeypatch).
"""
import json

import pytest

from agent.tools.registry import ToolRegistry
from core.chat.engine import ChatEngine, _extract_file_reference


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamCM:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return _FakeStreamResponse(self._lines)

    async def __aexit__(self, *args):
        return False


class _FakeAsyncClient:
    rounds: list[list[str]] = []

    def __init__(self, *args, **kwargs):
        self._round_index = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None):
        idx = min(self._round_index, len(self.rounds) - 1)
        self._round_index += 1
        return _FakeStreamCM(self.rounds[idx])


def _tool_call_round(tool_name: str, arguments: dict) -> str:
    return json.dumps(
        {"message": {"content": "", "tool_calls": [{"function": {"name": tool_name, "arguments": arguments}}]}, "done": True}
    )


def _final_round(text: str = "Selesai.") -> str:
    return json.dumps({"message": {"content": text}, "done": True})


def _echo_registry() -> ToolRegistry:
    """A fake workspace_list_files that just echoes the args it actually
    received back — lets tests assert what _run_tool injected."""
    reg = ToolRegistry()
    reg.register(
        "workspace_list_files",
        lambda **kwargs: {"success": True, "received_args": kwargs, "text": "ok"},
        "fake workspace_list_files echoing received args",
    )
    return reg


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _echo_registry())
    return ChatEngine()


async def _run(monkeypatch, engine, rounds, **stream_kwargs):
    class Client(_FakeAsyncClient):
        pass

    Client.rounds = rounds
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    events = []
    async for ev in engine.stream_run("sess-1", "lihat isi workspace", **stream_kwargs):
        events.append(ev)
    return events


# ─── _run_tool direct unit tests ────────────────────────────────────────

async def test_run_tool_injects_workspace_id_overriding_model_supplied_value(engine):
    registry = _echo_registry()
    result = await engine._run_tool(
        registry, "workspace_list_files", {"workspace_id": "fake-hallucinated-id"}, role=None, workspace_id="real-ws-id"
    )
    assert result["received_args"]["workspace_id"] == "real-ws-id"


async def test_run_tool_returns_not_connected_error_without_workspace_id(engine):
    registry = _echo_registry()
    result = await engine._run_tool(registry, "workspace_list_files", {}, role=None, workspace_id=None)
    assert result["success"] is False
    assert "belum terhubung" in result["error"].lower()


async def test_run_tool_injects_workspace_id_for_find_file(engine):
    registry = _echo_registry()
    registry.register("workspace_find_file", lambda **kw: {"success": True, "received_args": kw}, "fake")
    result = await engine._run_tool(
        registry, "workspace_find_file", {"filename": "x"}, role=None, workspace_id="real-ws-id"
    )
    assert result["received_args"]["workspace_id"] == "real-ws-id"
    # Read-only — no actor stamped, unlike the mutating tools below.
    assert "actor" not in result["received_args"]


async def test_run_tool_leaves_unrelated_tools_untouched(engine):
    registry = ToolRegistry()
    registry.register("write_txt", lambda **kw: {"success": True, "received_args": kw}, "fake")
    result = await engine._run_tool(registry, "write_txt", {"filename": "a.txt", "content": "hi"}, role=None, workspace_id="real-ws-id")
    assert "workspace_id" not in result["received_args"]


# ─── Workspace Write Access RBAC (Bab 69.7 write_output, Tahap 30) ──────

def _write_echo_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        "workspace_write_file",
        lambda **kwargs: {"success": True, "received_args": kwargs},
        "fake workspace_write_file echoing received args",
    )
    return reg


async def test_run_tool_denies_write_for_viewer_role(engine):
    registry = _write_echo_registry()
    result = await engine._run_tool(
        registry, "workspace_write_file", {"folder_id": "f1", "relative_path": "a.txt", "content": "x"},
        role=None, workspace_id="real-ws-id", workspace_role="viewer",
    )
    assert result["success"] is False
    assert "akses ditolak" in result["error"].lower()


async def test_run_tool_denies_write_when_no_workspace_role_bound(engine):
    registry = _write_echo_registry()
    result = await engine._run_tool(
        registry, "workspace_write_file", {"folder_id": "f1", "relative_path": "a.txt", "content": "x"},
        role=None, workspace_id="real-ws-id", workspace_role=None,
    )
    assert result["success"] is False


async def test_run_tool_allows_write_for_owner_role(engine):
    registry = _write_echo_registry()
    result = await engine._run_tool(
        registry, "workspace_write_file", {"folder_id": "f1", "relative_path": "a.txt", "content": "x"},
        role=None, workspace_id="real-ws-id", workspace_role="owner",
    )
    assert result["success"] is True
    assert result["received_args"]["workspace_id"] == "real-ws-id"


async def test_run_tool_allows_write_for_editor_role(engine):
    registry = _write_echo_registry()
    result = await engine._run_tool(
        registry, "workspace_write_file", {"folder_id": "f1", "relative_path": "a.txt", "content": "x"},
        role=None, workspace_id="real-ws-id", workspace_role="editor",
    )
    assert result["success"] is True


# ─── Fase 8 Slice 1: same write_output gate extended to create/move/copy ───

def _mutating_echo_registry(tool_name: str) -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(tool_name, lambda **kwargs: {"success": True, "received_args": kwargs}, "fake")
    return reg


@pytest.mark.parametrize("tool_name", ["workspace_create_folder", "workspace_move_file", "workspace_copy_file"])
async def test_run_tool_denies_mutating_workspace_tools_for_viewer_role(engine, tool_name):
    registry = _mutating_echo_registry(tool_name)
    result = await engine._run_tool(
        registry, tool_name, {"folder_id": "f1", "relative_path": "a"},
        role=None, workspace_id="real-ws-id", workspace_role="viewer",
    )
    assert result["success"] is False
    assert "akses ditolak" in result["error"].lower()


@pytest.mark.parametrize("tool_name", ["workspace_create_folder", "workspace_move_file", "workspace_copy_file"])
async def test_run_tool_allows_mutating_workspace_tools_for_owner_role(engine, tool_name):
    registry = _mutating_echo_registry(tool_name)
    result = await engine._run_tool(
        registry, tool_name, {"folder_id": "f1", "relative_path": "a"},
        role=None, workspace_id="real-ws-id", workspace_role="owner", owner="alice",
    )
    assert result["success"] is True
    assert result["received_args"]["actor"] == "alice"
    assert result["received_args"]["workspace_id"] == "real-ws-id"


# ─── Fase 8 Slice 1: Chat Decision Flow prompt injection ───────────────────

def test_build_user_message_injects_decision_flow_note_when_workspace_bound(engine):
    from core.chat.engine import Session, WORKSPACE_DECISION_FLOW_NOTE

    session = Session("s1", workspace_id="ws-1")
    msg = engine._build_user_message(session, "ringkas file laporan.pdf", [])
    assert WORKSPACE_DECISION_FLOW_NOTE in msg["content"]


def test_build_user_message_omits_decision_flow_note_without_workspace(engine):
    from core.chat.engine import Session, WORKSPACE_DECISION_FLOW_NOTE

    session = Session("s1")
    msg = engine._build_user_message(session, "halo", [])
    assert WORKSPACE_DECISION_FLOW_NOTE not in msg["content"]


# ─── stream_run integration (binding persistence across messages) ──────

async def test_stream_run_binds_workspace_id_on_first_message(monkeypatch, engine):
    rounds = [
        [_tool_call_round("workspace_list_files", {})],
        [_final_round()],
    ]
    events = await _run(monkeypatch, engine, rounds, workspace_id="ws-1")

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True
    assert engine.sessions["sess-1"].workspace_id == "ws-1"


async def test_session_keeps_bound_workspace_id_when_later_message_omits_it(monkeypatch, engine):
    # First message binds ws-1.
    await _run(monkeypatch, engine, [[_final_round()]], workspace_id="ws-1")
    # Second message on the SAME session doesn't resupply workspace_id.
    rounds = [
        [_tool_call_round("workspace_list_files", {})],
        [_final_round()],
    ]
    events = await _run(monkeypatch, engine, rounds, workspace_id=None)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert tool_results[0]["ok"] is True  # still connected via the session's remembered binding
    assert engine.sessions["sess-1"].workspace_id == "ws-1"


# ─── Workspace image → real vision turn (Bab 69.5, Tahap 29) ───────────────

def _image_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        "workspace_read_file",
        lambda **kw: {
            "success": True, "path": "site.png", "type": "image",
            "image_base64": "ZmFrZS1pbWFnZS1ieXRlcw==", "mime_type": "image/png",
            "text": "Gambar dari Workspace: site.png",
        },
        "fake workspace_read_file returning an image result",
    )
    return reg


async def test_image_tool_result_injects_followup_vision_message(monkeypatch):
    monkeypatch.setattr("core.chat.engine.build_registry", lambda base_url, model: _image_registry())
    engine = ChatEngine()
    rounds = [
        [_tool_call_round("workspace_read_file", {"folder_id": "f1", "relative_path": "site.png"})],
        [_final_round("Gambar menunjukkan lokasi tambang.")],
    ]
    await _run(monkeypatch, engine, rounds, workspace_id="ws-1")

    messages = engine.sessions["sess-1"].messages
    tool_idx = next(i for i, m in enumerate(messages) if m.get("role") == "tool")
    vision_msg = messages[tool_idx + 1]
    assert vision_msg["role"] == "user"
    assert vision_msg["images"] == ["ZmFrZS1pbWFnZS1ieXRlcw=="]
    # The base64 must NOT leak into the tool-role JSON fed back as text.
    assert "ZmFrZS1pbWFnZS1ieXRlcw==" not in messages[tool_idx]["content"]


# ─── Fase 8 follow-up fix: deterministic Workspace file auto-resolution ────
# Live verification against a real gemma4:e2b turn showed the prompt-only
# WORKSPACE_DECISION_FLOW_NOTE steering (tested above) isn't reliable enough
# by itself — given a Windows path, the model called workspace_list_files
# (truncated for a real ~100-file folder, hiding the match) then called the
# WRONG tool (read_pdf on the literal "D:\..." string) instead of
# workspace_find_file/workspace_read_file. These tests cover the
# deterministic, code-level fix instead.

@pytest.mark.parametrize(
    "text,expected",
    [
        (r"Ringkas file di D:\04_Archive\Document\Kesimpulan_Tiga_Framework.pdf", "Kesimpulan_Tiga_Framework.pdf"),
        ("summarize report.docx please", "report.docx"),
        ("lihat /home/user/notes.txt dong", "notes.txt"),
        ("what is version 3.2 of the plan?", None),
        ("halo apa kabar", None),
        ("cek data.xlsx dan gambar.png", "data.xlsx"),
    ],
)
def test_extract_file_reference(text, expected):
    assert _extract_file_reference(text) == expected


def _patch_find_and_read(monkeypatch, find_result, read_result=None):
    async def _fake_find(workspace_id, filename, session_factory=None):
        return find_result

    async def _fake_read(workspace_id, folder_id, relative_path, session_factory=None):
        return read_result

    monkeypatch.setattr("agent.tools.workspace_reader._find_file", _fake_find)
    monkeypatch.setattr("agent.tools.workspace_reader._read_file", _fake_read)


async def test_auto_resolve_returns_none_without_file_reference(engine):
    note = await engine._auto_resolve_workspace_file("ws-1", "halo apa kabar")
    assert note is None


async def test_auto_resolve_zero_matches_tells_model_not_to_pretend(engine, monkeypatch):
    _patch_find_and_read(monkeypatch, {"success": True, "matches": [], "searched_folders": ["Docs"]})
    note = await engine._auto_resolve_workspace_file("ws-1", "ringkas laporan.pdf")
    assert "TIDAK ditemukan" in note
    assert "Docs" in note
    assert "JANGAN pura-pura" in note


async def test_auto_resolve_multiple_matches_lists_them(engine, monkeypatch):
    _patch_find_and_read(monkeypatch, {"success": True, "matches": [
        {"relative_path": "a/laporan.pdf", "folder_id": "f1"},
        {"relative_path": "b/laporan.pdf", "folder_id": "f2"},
    ]})
    note = await engine._auto_resolve_workspace_file("ws-1", "ringkas laporan.pdf")
    assert "2 file cocok" in note
    assert "a/laporan.pdf" in note
    assert "b/laporan.pdf" in note


async def test_auto_resolve_single_document_match_injects_content(engine, monkeypatch):
    _patch_find_and_read(
        monkeypatch,
        {"success": True, "matches": [{"relative_path": "Document/laporan.pdf", "folder_id": "f1"}]},
        {"success": True, "type": "document", "text": "Kadar tembaga 1.85% ditemukan di blok Alpha."},
    )
    note = await engine._auto_resolve_workspace_file("ws-1", "ringkas laporan.pdf")
    assert "Kadar tembaga 1.85%" in note
    assert "JANGAN panggil read_pdf" in note


async def test_auto_resolve_read_failure_reports_error_not_success(engine, monkeypatch):
    _patch_find_and_read(
        monkeypatch,
        {"success": True, "matches": [{"relative_path": "Document/laporan.pdf", "folder_id": "f1"}]},
        {"success": False, "error": "disk penuh"},
    )
    note = await engine._auto_resolve_workspace_file("ws-1", "ringkas laporan.pdf")
    assert "gagal dibaca" in note
    assert "disk penuh" in note


async def test_auto_resolve_image_match_defers_to_workspace_read_file_tool(engine, monkeypatch):
    _patch_find_and_read(
        monkeypatch,
        {"success": True, "matches": [{"relative_path": "site.png", "folder_id": "f1"}]},
        {"success": True, "type": "image"},
    )
    note = await engine._auto_resolve_workspace_file("ws-1", "lihat site.png")
    assert "workspace_read_file" in note
    assert "folder_id=f1" in note


async def test_stream_run_injects_auto_resolved_content_into_user_message(monkeypatch, engine):
    _patch_find_and_read(
        monkeypatch,
        {"success": True, "matches": [{"relative_path": "Document/laporan.pdf", "folder_id": "f1"}]},
        {"success": True, "type": "document", "text": "Isi laporan sungguhan."},
    )

    class Client(_FakeAsyncClient):
        pass

    Client.rounds = [[_final_round("Ringkasan selesai.")]]
    monkeypatch.setattr("core.chat.engine.httpx.AsyncClient", Client)

    events = []
    async for ev in engine.stream_run("sess-1", "ringkas laporan.pdf", workspace_id="ws-1"):
        events.append(ev)

    user_messages = [m for m in engine.sessions["sess-1"].messages if m.get("role") == "user"]
    assert any("Isi laporan sungguhan." in m["content"] for m in user_messages)
