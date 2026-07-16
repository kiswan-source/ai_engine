"""
ChatEngine — conversational, streaming, tool-calling loop over local Gemma.

Flow per user turn:
  1. Uploaded files are auto-read into context (text) or attached as vision images.
  2. The model streams its reply via Ollama /api/chat with `tools` exposed.
  3. If it emits tool_calls, we execute them through the shared ToolRegistry,
     feed the results back, and continue — up to MAX_TOOL_ROUNDS.
  4. Any tool that produces a file (result has a "file" key) is surfaced to the
     client as a downloadable card.

Events yielded by `stream_run` (consumed by api/routes/chat.py → SSE):
  {"type": "token", "text": str}
  {"type": "tool_start", "name": str, "args": dict}
  {"type": "tool_result", "name": str, "ok": bool, "summary": str}
  {"type": "file", "filename": str, "ftype": str, "size": int}
  {"type": "error", "message": str}
  {"type": "done"}

RBAC (Tahap 20, closes the gap every Tahap since 10 acknowledged): `stream_run`
takes an optional `role: str | None = None`, threaded to every tool execution
via `ToolRegistry.execute(role=...)` — the same generic gate `agent/core.py`
already uses, unchanged since Tahap 10. `api/routes/chat.py` supplies it from
`security.auth.get_current_principal`. `role=None` (no caller opts in) is a
complete no-op, identical to behavior before this Tahap. A denied tool call
does NOT raise — `_run_tool` catches `PermissionError` and returns it as a
normal `{"error": ...}` result (same shape `_summarize_result`/`ok` already
handle), so one denied call ends that tool call, not the whole SSE stream.

Session ownership (Tahap 22, closes the gap Tahap 20 explicitly left open):
`Session.owner` records the `Principal.api_key` of whoever first touches a
`session_id` (via `get_session`/`stream_run`'s `owner=` kwarg) and never
changes after that. This module does not enforce anything from it —
`api/routes/chat.py` checks `owner` against the caller's `Principal` before
letting a request through, the same "engine stays framework-agnostic, the
route does authorization" split `api/routes/workspace.py` already uses.
`owner=None` (no caller opts in) behaves exactly as before every Tahap 20/22
change: unowned, anyone can touch it — matches every RBAC feature in this
app being a no-op when its caller doesn't opt in.

Agent Workspace Context (Bab 69.5, Tahap 23): `Session.workspace_id`, same
first-non-null-wins shape as `owner`. `api/routes/chat.py` checks the
caller's Project role against the target Workspace *once per HTTP request*
(not per tool call) before passing `workspace_id` in — this module trusts
that check the same way it trusts `owner`. The two new tools
(`workspace_list_files`/`workspace_read_file`, `agent/tools/workspace_reader.py`)
never receive `workspace_id` from the model — `_run_tool` injects
`session.workspace_id` into their arguments, overriding anything the model
supplied, so a hallucinated or prompt-injected ID can never reach a
Workspace this session wasn't authorized for.

Download ownership (Tahap 24, closes the gap Tahap 22/23 explicitly left
open): `Session.produced_files` records the basename of every file a
tool actually generated in that session (both the main tool-calling loop
and `_fallback`). `api/routes/chat.py`'s `/download/{filename}` now
requires `session_id` + ownership *and* that `filename` is in that
session's `produced_files` — previously any caller could fetch anything in
`reports/` by filename alone, with no session concept at all. Note:
`GET /reports/{filename}` (`api/routes/files.py`, a different, older route
serving the same directory) still has no such check — a separate, wider
gap this Tahap does not close, documented in `docs/PROGRESS.md`.

Workspace images (Bab 69.5 Vision, Tahap 29): when `workspace_read_file`
(`agent/tools/workspace_reader.py`) returns an image (`type == "image"`,
category detection lives in `tools/adapters/filesystem.py::classify`),
`stream_run` follows the tool-role result with a synthetic `user`-role
message carrying `images: [base64]` — the same mechanism already used for
uploaded images, just triggered mid-tool-loop instead of at turn start.
The raw base64 is stripped from the tool-role JSON first (it would waste
most of `TOOL_RESULT_MAX_CHARS` on a truncated fragment the model can't
see anyway). GIS files from Workspace return the same compact
area/centroid/bbox summary `read_kml`/`read_geojson`/`read_shp` already
produce — no engine change needed for those, they flow through the
existing generic tool-result path.

Workspace Write Access (Bab 69.7 `write_output`, Tahap 30): `Session.workspace_role`,
same first-non-null-wins shape as `workspace_id` — caches the Project role
`api/routes/chat.py` resolved once at bind time. `_run_tool` checks
`require_workspace_permission(workspace_role, "write_output")` specifically
for `workspace_write_file`, catching `PermissionError` into the same
denial-dict shape every other RBAC check here already uses. This keeps the
same "engine trusts the route's one-time check, agent/tools/ never
re-derives Project role itself" split Tahap 23 established.

Tool-call resilience (Tahap 31): `_run_tool` now catches any exception a
tool raises (not just `PermissionError`) and returns it as the same
denial-dict shape — found live during Tahap 30 verification, where a
model call missing a required argument raised a raw `TypeError` that
propagated out of the tool loop entirely and killed the whole SSE turn.
Every tool shared this gap, not just the newest one.

Friendly tool-error messages (Tahap 41): Tahap 31's denial dict embedded
the raw `str(exception)` verbatim (e.g. a stdlib `TypeError`'s English
"missing 1 required positional argument" phrasing) — a normal tool
failure the model could react to, but not phrased for the person reading
the chat. `_friendly_tool_error` prefixes the most common exception
types (missing/wrong argument, missing file, missing dict key, bad value)
with a short Indonesian sentence naming what went wrong; the original
exception text is kept, not hidden, since the model still benefits from
the specifics when composing its own explanation. Anything not in the
map keeps the exact wording Tahap 31 already used.

Prompt/output guardrails (Fase 1, DCF_SECURITY_AUDIT_2026-07-11.md SEC-3):
`agents/generic_agent.py` was the only place `security.prompt_guard`/
`output_validator` were ever wired in — this HTTP-facing, primary-feature
engine never called either, despite both being enabled by default
(`ENABLE_PROMPT_GUARD`/`ENABLE_OUTPUT_VALIDATION` in `api/config.py`).
Input side: `check_prompt(user_text)` runs before the tool-calling loop
starts. Unlike `generic_agent.py` (which can outright refuse a one-shot
dispatch), a suspicious/blocked score here NEUTRALIZES and CONTINUES the
turn rather than ending it — a live, actively-used conversation must not
go silent on a false positive from generic regex patterns; only the
sanitized text reaches the model, and the event is still recorded via
`audit_log.record("prompt_guard.neutralized", ...)` for the Security
Dashboard. Output side: because `stream_run` yields tokens incrementally
over SSE, real per-token validation before send is out of scope for this
pass — `validate()` (which already folds in PII-leak detection, see
`security/output_validator.py`) runs on the FULL ACCUMULATED response
text once, immediately before the terminal `{"type": "done"}` event. This
is detect-and-flag, not prevent: by the time a violation is found, every
token has already reached the client. A violation surfaces as one extra
`{"type": "warning", ...}` SSE event plus an `audit_log.record(...)`
entry — known limitation, not silently swallowed. `ENABLE_PROMPT_GUARD`/
`ENABLE_OUTPUT_VALIDATION` staying `false` in `.env` is the instant
rollback lever if either misfires against real traffic, no code change
needed.

PII redaction (Fase 1, SEC-4): same absence as above — never wired in here.
Applied right alongside the prompt-guard check, gated on
`security.endpoint_policy.is_internal_endpoint(self.base_url)` rather than
provider name (see that module's docstring) — a no-op today (this
deployment's `OLLAMA_BASE_URL` classifies as internal on both live modes),
becomes real the moment `OLLAMA_BASE_URL` ever points somewhere that
isn't. Input-side only, matching Bab 30's actual scope ("sebelum dikirim ke
provider eksternal") — redacting the response after it's already streamed
wouldn't undo anything.
"""
import os
import json
import base64
import asyncio
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from api.config import settings
from agent.tools.registry import build_registry
from agent.tools.readers import read_pdf, read_docx, read_csv, read_txt, read_json
from core.chat.tool_schemas import TOOL_SCHEMAS, EXPOSED_TOOL_NAMES
from core.utils.logger import get_logger
from memory.memory_manager import get_shared_memory_manager
from prompts.loader import load_prompt
from security import audit_log, check_prompt, detect_pii, redact_pii, validate
from security.endpoint_policy import is_internal_endpoint

logger = get_logger(__name__)

UPLOADS_DIR = os.path.expanduser("~/ai_engine/uploads")
REPORTS_DIR = os.path.expanduser("~/ai_engine/reports")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

MAX_TOOL_ROUNDS = 5
# How much of a tool result to feed back to the model. Readers cap their own
# text at ~10k chars; this must be large enough not to clip that again.
TOOL_RESULT_MAX_CHARS = 12000
# How much auto-read file content to inline into the user turn for context.
INLINE_SNIPPET_CHARS = 8000
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "gif", "tif", "tiff"}
TEXT_READERS = {"pdf": read_pdf, "docx": read_docx, "csv": read_csv,
                "txt": read_txt, "md": read_txt, "json": read_json}
# Tools whose workspace_id arg is always injected from the session, never
# the model (Bab 69.5, Tahap 23) — see _run_tool. Fase 8 Slice 1 adds the
# search/move/copy/create-folder tools to this set — same injection rule,
# they're just as capable of reaching outside an authorized Workspace via a
# hallucinated/injected ID as the original three.
WORKSPACE_TOOL_NAMES = {
    "workspace_list_files", "workspace_read_file", "workspace_write_file",
    "workspace_find_file", "workspace_create_folder", "workspace_move_file", "workspace_copy_file",
}
# Mutating subset of WORKSPACE_TOOL_NAMES — gated on the write_output
# Workspace Permission (Bab 69.7) and stamped with `actor` for audit/version
# snapshots, same as workspace_write_file already was (Fase 4). Deliberately
# excludes workspace_list_files/workspace_read_file/workspace_find_file
# (read-only, no permission check needed — same posture those two always had).
WORKSPACE_MUTATING_TOOL_NAMES = {"workspace_write_file", "workspace_create_folder", "workspace_move_file", "workspace_copy_file"}
# Fase 8 (DCF v5 mandate "Workspace Native File Access & Chat UX Repair",
# Slice 1) — Chat Decision Flow. Injected into every user turn a Workspace is
# bound to (see _build_user_message). Encodes the mandate's mandatory STEP
# 1-5 order and its PROHIBITED RESPONSE list verbatim as a steering
# instruction to the model — this is prompt-level guidance, not a hard
# guarantee: gemma4:e2b can still ignore it on a given turn (no different
# from any other system-prompt instruction in this codebase), but it is the
# actual mechanism available given the chat path is LLM-driven native tool
# calling (core/chat/, see CLAUDE.md §9), not a scripted dialogue tree.
WORKSPACE_DECISION_FLOW_NOTE = (
    "[Project Workspace terhubung. WAJIB ikuti urutan ini kalau pengguna menyebut "
    "sebuah file:\n"
    "1) Pengguna kasih path/nama file -> panggil workspace_list_files (kalau belum) "
    "lalu cocokkan ke relative_path hasilnya, baru workspace_read_file.\n"
    "2) Ketemu -> langsung kerjakan, JANGAN tanya konfirmasi lagi.\n"
    "3) Tidak ketemu di listing -> panggil workspace_find_file dengan nama filenya "
    "(Smart Search, mencari ke semua folder Workspace). Satu hasil cocok -> langsung "
    "pakai. Lebih dari satu -> minta pengguna pilih salah satu.\n"
    "4) workspace_find_file tetap nol hasil -> baru minta pengguna sebutkan lokasi lain.\n"
    "5) HANYA kalau sudah lewat langkah 1-4 dan benar-benar tidak ketemu -> baru "
    "tawarkan upload sebagai pilihan TERAKHIR.\n"
    "DILARANG langsung menjawab 'saya tidak punya akses ke drive', 'saya hanya bisa "
    "baca file yang diupload', atau 'tolong upload filenya' SEBELUM langkah 1-4 di atas "
    "benar-benar dijalankan. Workspace juga punya tool workspace_create_folder/"
    "workspace_move_file/workspace_copy_file untuk membuat folder/memindahkan/"
    "mengganti nama/menyalin file — pakai kalau relevan. Format jawaban ringkas dan "
    "profesional (mis. '✓ File ditemukan' / '✓ Analisis selesai'), jangan bertele-tele.]"
)
# Fase 3 (DCF v5 mandate, Memory Intelligence Evolution): same injection rule
# as WORKSPACE_TOOL_NAMES, for owner instead of workspace_id — see _run_tool
# and agent/tools/memory_tools.py.
MEMORY_TOOL_NAMES = {"remember_fact", "recall_facts"}
# How many turns between rolling-summary refreshes (Fase 3) — SummaryMemory's
# own summarizer call costs an LLM round-trip, so this isn't done every turn.
MEMORY_SUMMARY_EVERY_N_TURNS = 5

# Prompt Versioning (Bab 51, Tahap 37) — content lives at
# prompts/chat/system_v1.md; version is registered explicitly here, never
# inferred from the highest version number on disk.
SYSTEM_PROMPT = load_prompt("chat", "system", version=1)

# Friendly tool-error prefixes (Tahap 41) — the most common exception
# shapes a tool call raises, keyed by exact type (not isinstance, so a
# more specific subclass some future tool raises isn't silently matched
# to the wrong sentence). Anything not listed keeps Tahap 31's original
# "Tool '<name>' gagal: <e>" wording.
_FRIENDLY_ERROR_PREFIXES = {
    TypeError: "Argumen tool tidak lengkap atau salah",
    FileNotFoundError: "File tidak ditemukan",
    KeyError: "Data yang dibutuhkan tool tidak lengkap",
    ValueError: "Nilai argumen tool tidak valid",
}


def _friendly_tool_error(name: str, e: Exception) -> str:
    prefix = _FRIENDLY_ERROR_PREFIXES.get(type(e))
    if prefix is None:
        return f"Tool '{name}' gagal: {e}"
    return f"{prefix} untuk tool '{name}': {e}"


class Session:
    def __init__(self, session_id: str, owner: Optional[str] = None, workspace_id: Optional[str] = None,
                 workspace_role: Optional[str] = None):
        self.id = session_id
        self.owner = owner  # Principal.api_key of whoever created it (Tahap 22); None if unset
        self.workspace_id = workspace_id  # bound Project Workspace (Tahap 23); None if unset
        self.workspace_role = workspace_role  # caller's Project role on that Workspace (Tahap 30); None if unset
        self.messages: List[Dict[str, Any]] = []   # Ollama-format chat history
        self.history: List[Dict[str, Any]] = []     # display items for the UI
        self.files: List[str] = []  # absolute paths of uploaded files
        self.produced_files: set = set()  # basenames this session's tools generated (Tahap 24)
        self.turn_count: int = 0  # Fase 3 — gates SummaryMemory refresh cadence

    def add_file(self, path: str):
        if path not in self.files:
            self.files.append(path)


class ChatEngine:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.default_model = settings.GEMMA_MODEL
        self._registries: Dict[str, Any] = {}
        self.sessions: Dict[str, Session] = {}
        # Fase 3 — the SAME instance api/routes/memory.py reads, not a
        # private build_memory_manager() call (see get_shared_memory_manager
        # docstring for why that matters for the in-memory dev/CI backends).
        self.memory = get_shared_memory_manager()

    # ── Session helpers ──
    def get_session(
        self, session_id: str, owner: Optional[str] = None, workspace_id: Optional[str] = None,
        workspace_role: Optional[str] = None,
    ) -> Session:
        """Fetch or create a session. ``owner`` is only recorded at creation —
        an existing session's owner never changes (Tahap 22: first caller to
        touch a session_id owns it; api/routes/chat.py enforces this before
        calling here, this method itself doesn't check anything). ``workspace_id``
        (and ``workspace_role``, Tahap 30, same shape) is first-non-null-wins
        (Tahap 23): binds on creation, or on a later call if the session
        didn't have one yet — never overwrites an already-bound value."""
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(session_id, owner=owner, workspace_id=workspace_id,
                                                 workspace_role=workspace_role)
        else:
            session = self.sessions[session_id]
            if session.workspace_id is None and workspace_id is not None:
                session.workspace_id = workspace_id
            if session.workspace_role is None and workspace_role is not None:
                session.workspace_role = workspace_role
        return self.sessions[session_id]

    def list_sessions(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        """``owner=None`` (default, unchanged since before Tahap 22) lists
        every session. Passing an owner filters to that caller's own —
        api/routes/chat.py always passes one so a user only ever sees their
        own sessions."""
        out = []
        for s in self.sessions.values():
            if owner is not None and s.owner != owner:
                continue
            first_user = next((h["content"] for h in s.history if h["type"] == "user"), "")
            out.append({"id": s.id, "title": (first_user or "Chat baru")[:60],
                        "message_count": len(s.history),
                        "files": [os.path.basename(f) for f in s.files]})
        # Most-recently-active first.
        return out[::-1]

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        s = self.sessions.get(session_id)
        return s.history if s else []

    def delete_session(self, session_id: str) -> bool:
        return self.sessions.pop(session_id, None) is not None

    def _registry(self, model: str):
        if model not in self._registries:
            self._registries[model] = build_registry(self.base_url, model)
        return self._registries[model]

    # ── Path resolution ──
    def resolve_path(self, p: str) -> str:
        if not p:
            return p
        if os.path.isabs(p) and os.path.exists(p):
            return p
        for base in (UPLOADS_DIR, REPORTS_DIR, os.getcwd()):
            cand = os.path.join(base, os.path.basename(p))
            if os.path.exists(cand):
                return cand
        return p

    # ── Build the user message (text context + vision images) ──
    def _build_user_message(self, session: Session, text: str,
                            new_files: List[str]) -> Dict[str, Any]:
        context_blocks = []
        images_b64 = []
        attached = []
        for path in new_files:
            ext = os.path.splitext(path)[1].lower().lstrip(".")
            attached.append(path)
            if ext in IMAGE_EXTS:
                try:
                    with open(path, "rb") as fh:
                        images_b64.append(base64.b64encode(fh.read()).decode())
                except Exception:
                    pass
            elif ext in TEXT_READERS:
                try:
                    r = TEXT_READERS[ext](path)
                    full = r.get("text") or ""
                    snippet = full[:INLINE_SNIPPET_CHARS]
                    if snippet:
                        note = (f"\n[...dipotong, total {len(full)} karakter — "
                                f"panggil tool read untuk isi lengkap]"
                                if len(full) > INLINE_SNIPPET_CHARS else "")
                        context_blocks.append(
                            f"[Isi {os.path.basename(path)}]:\n{snippet}{note}")
                except Exception as e:
                    context_blocks.append(f"[{os.path.basename(path)}: gagal dibaca — {e}]")

        parts = [text]
        if attached:
            listing = "\n".join(f"- {p}" for p in attached)
            parts.append(f"\n\nFile terlampir (pakai path ini untuk argumen file_path):\n{listing}")
        if context_blocks:
            parts.append("\n\n" + "\n\n".join(context_blocks))
        if session.workspace_id:
            parts.append("\n\n" + WORKSPACE_DECISION_FLOW_NOTE)

        msg: Dict[str, Any] = {"role": "user", "content": "".join(parts)}
        if images_b64:
            msg["images"] = images_b64
        return msg

    # ── Low-level streaming call to Ollama /api/chat ──
    async def _stream_chat(self, messages, model, client) -> AsyncIterator[dict]:
        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOL_SCHEMAS,
            "stream": True,
            # gemma4:e2b is a "thinking" model: by default Ollama streams all its
            # reasoning into message.thinking while message.content stays empty.
            # We only surface content, so that phase looked like the assistant was
            # frozen ("tidak menjawab") — several silent seconds per turn, repeated
            # before every tool round on multi-step tasks. Disable it so tokens
            # (and tool_calls) come immediately. Verified tool-calling still works.
            "think": False,
            # num_ctx must be set explicitly — Ollama's 4096-token default would
            # truncate the system prompt + injected file content on long turns,
            # which is why the model would otherwise seem to ignore the file.
            "options": {"temperature": 0.4, "num_ctx": settings.OLLAMA_NUM_CTX},
        }
        async with client.stream("POST", "/api/chat", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.strip():
                    yield json.loads(line)

    # ── Execute one tool call, normalising args + paths ──
    async def _run_tool(
        self, registry, name: str, args: Any, role: Optional[str] = None, workspace_id: Optional[str] = None,
        workspace_role: Optional[str] = None, owner: Optional[str] = None,
    ) -> Dict[str, Any]:
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"input": args}
        if not isinstance(args, dict):
            args = {"input": args}
        if name in WORKSPACE_TOOL_NAMES:
            # Never trust a model-supplied workspace_id (Tahap 23) — this is
            # the actual boundary preventing a hallucinated/injected ID from
            # reaching a Workspace this session wasn't authorized for.
            if not workspace_id:
                return {"error": "Sesi ini belum terhubung ke Project Workspace.", "success": False}
            args["workspace_id"] = workspace_id
        if name in WORKSPACE_MUTATING_TOOL_NAMES:
            # Fase 4 (extended Fase 8 Slice 1 to the whole mutating set) —
            # identifies who triggered a mutation, for the version snapshot +
            # audit log entry each of these records. Same never-trust-the-model
            # rule as workspace_id/owner above.
            args["actor"] = owner or role or "anonymous"
        if name in MEMORY_TOOL_NAMES:
            # Fase 3 — same rule as workspace_id above: never let the model
            # supply its own owner, or one session could recall/overwrite
            # another owner's remembered facts by just naming them in a tool
            # call. None (no authenticated caller) maps to a shared
            # "anonymous" namespace inside agent/tools/memory_tools.py.
            args["owner"] = owner
        if name in WORKSPACE_MUTATING_TOOL_NAMES:
            # Bab 69.7 write_output (Tahap 30, extended Fase 8 Slice 1 to
            # create/move/copy) — checked here with the Project role
            # api/routes/chat.py already resolved once at bind time (cached
            # on session.workspace_role), NOT re-derived here: agent/tools/
            # must not import from api/ (same rule Tahap 23 already
            # documented for why per-tool-call re-derivation was rejected
            # there).
            try:
                from security.permissions import require_workspace_permission
                require_workspace_permission(workspace_role, "write_output")
            except PermissionError as e:
                return {"error": f"Akses ditolak: {e}", "success": False}
        # Resolve any path-ish argument against uploads/reports.
        for key in ("file_path", "path", "source"):
            if key in args and isinstance(args[key], str):
                args[key] = self.resolve_path(args[key])
        if "file_paths" in args and isinstance(args["file_paths"], list):
            args["file_paths"] = [self.resolve_path(p) for p in args["file_paths"]]
        try:
            return await asyncio.to_thread(registry.execute, name, args, role)
        except PermissionError as e:
            # Same result shape as any other tool failure (_summarize_result/
            # the ok= check already handle "error" in a dict) — the model sees
            # a normal denial it can relay, not a crashed turn (role=None,
            # the unchanged default for every caller that doesn't pass one,
            # never hits this: ToolRegistry.execute only checks permissions
            # when role is not None).
            return {"error": f"Akses ditolak: {e}", "success": False}
        except Exception as e:
            # Tahap 31: found live via Tahap 30 verification — a model that
            # omits/mistypes a required tool argument (e.g. calls
            # workspace_write_file without folder_id) raises a raw TypeError
            # here that, uncaught, propagates out of stream_run's tool loop
            # entirely and kills the WHOLE SSE turn (a generic {"type":"error"}
            # event, conversation just stops) — not a per-tool failure the
            # model could see and react to. Every tool shared this gap, not
            # just the new one; it was just never exercised by a tool with
            # this many required arguments before. Same denial-dict shape as
            # the PermissionError case above: one bad call ends that call,
            # not the conversation.
            logger.warning("tool call raised", tool=name, error=str(e))
            return {"error": _friendly_tool_error(name, e), "success": False}

    # ── Memory wiring (Fase 3, DCF v5 mandate "Memory Intelligence Evolution") ──
    # Session-scoped only (working/conversation/summary) — safe by construction,
    # no cross-session/cross-user data ever crosses here. Cross-session memory
    # is the separate, explicit-opt-in remember_fact/recall_facts tools instead
    # (agent/tools/memory_tools.py), never automatic. A memory-tier failure
    # (e.g. Redis/Postgres down) must never break the actual chat turn — Bab
    # 10.4's audit-log principle applies here too, so both helpers below only
    # log a warning on failure, never raise.
    async def _remember_turn_start(self, session_id: str, user_text: str) -> None:
        try:
            await self.memory.conversation.add_message(session_id, "user", user_text, trace_id=session_id)
            await self.memory.working.set(session_id, "last_message_at", time.time())
        except Exception as e:
            logger.warning("memory.remember_turn_start_failed", session_id=session_id, error=str(e))

    async def _remember_turn_end(self, session: Session, user_text: str, full_text: str) -> None:
        if not full_text.strip():
            return
        session_id = session.id
        try:
            await self.memory.conversation.add_message(session_id, "assistant", full_text, trace_id=session_id)
            await self.memory.working.set(
                session_id, "last_files",
                {"uploaded": [os.path.basename(f) for f in session.files],
                 "produced": sorted(session.produced_files)},
            )
            if session.turn_count % MEMORY_SUMMARY_EVERY_N_TURNS == 0:
                await self.memory.summary.summarize_and_store(
                    session_id, f"User: {user_text}\n\nAssistant: {full_text}"
                )
        except Exception as e:
            logger.warning("memory.remember_turn_end_failed", session_id=session_id, error=str(e))

    # ── Main entry: stream a full assistant turn ──
    async def stream_run(self, session_id: str, user_text: str,
                         new_files: Optional[List[str]] = None,
                         model: Optional[str] = None,
                         role: Optional[str] = None,
                         owner: Optional[str] = None,
                         workspace_id: Optional[str] = None,
                         workspace_role: Optional[str] = None) -> AsyncIterator[Dict[str, Any]]:
        model = model or self.default_model
        session = self.get_session(session_id, owner=owner, workspace_id=workspace_id, workspace_role=workspace_role)
        new_files = [self.resolve_path(f) for f in (new_files or [])]
        for f in new_files:
            session.add_file(f)

        if not session.messages:
            session.messages.append({"role": "system", "content": SYSTEM_PROMPT})
        model_input_text = user_text
        if settings.ENABLE_PROMPT_GUARD:
            guard = check_prompt(user_text)
            if guard.suspicious or guard.blocked:
                # Chat is a live conversation, not a one-shot dispatch (unlike
                # agents/generic_agent.py) — neutralize and continue, never
                # hard-block, so a false positive doesn't silently end a turn.
                # Only the text sent to the model is sanitized; session.history
                # (below) keeps the original for the person reading the chat.
                model_input_text = guard.sanitized_text
                await audit_log.record(
                    "prompt_guard.neutralized",
                    actor=role or "anonymous",
                    detail={"matches": guard.matches, "score": guard.score, "session_id": session_id},
                    trace_id=session_id,
                )
        if settings.ENABLE_PII_REDACTION and not is_internal_endpoint(self.base_url):
            pii_matches = detect_pii(model_input_text)
            if pii_matches:
                model_input_text = redact_pii(model_input_text)
                await audit_log.record(
                    "pii.redacted",
                    actor=role or "anonymous",
                    detail={"categories": sorted({m.category for m in pii_matches}), "count": len(pii_matches),
                            "session_id": session_id},
                    trace_id=session_id,
                )
        session.messages.append(self._build_user_message(session, model_input_text, new_files))
        session.history.append({"type": "user", "content": user_text,
                                "files": [os.path.basename(f) for f in new_files]})
        session.turn_count += 1
        await self._remember_turn_start(session_id, user_text)

        produced_files: List[str] = []
        any_tool_called = False
        full_response_text_parts: List[str] = []

        try:
            timeout = httpx.Timeout(settings.OLLAMA_TIMEOUT, connect=10.0)
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout) as client:
                registry = self._registry(model)

                for _round in range(MAX_TOOL_ROUNDS):
                    assistant_content = ""
                    tool_calls: List[dict] = []

                    async for chunk in self._stream_chat(session.messages, model, client):
                        msg = chunk.get("message", {})
                        if msg.get("content"):
                            assistant_content += msg["content"]
                            full_response_text_parts.append(msg["content"])
                            yield {"type": "token", "text": msg["content"]}
                        for tc in msg.get("tool_calls", []) or []:
                            tool_calls.append(tc)
                        if chunk.get("done"):
                            break

                    assistant_msg: Dict[str, Any] = {"role": "assistant", "content": assistant_content}
                    if tool_calls:
                        assistant_msg["tool_calls"] = tool_calls
                    session.messages.append(assistant_msg)
                    if assistant_content.strip():
                        session.history.append({"type": "assistant", "content": assistant_content})

                    if not tool_calls:
                        break

                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        args = fn.get("arguments", {})
                        if name not in EXPOSED_TOOL_NAMES:
                            session.messages.append({"role": "tool", "tool_name": name,
                                                     "content": f"Tool '{name}' tidak tersedia."})
                            continue
                        any_tool_called = True
                        yield {"type": "tool_start", "name": name, "args": args}
                        result = await self._run_tool(
                            registry, name, args, role, session.workspace_id, session.workspace_role,
                            owner=session.owner,
                        )
                        ok = not (isinstance(result, dict) and (result.get("success") is False or
                                  ("error" in result and "success" not in result)))
                        summary = self._summarize_result(result)
                        yield {"type": "tool_result", "name": name, "ok": ok, "summary": summary}

                        if ok and isinstance(result, dict) and result.get("file"):
                            fpath = result["file"]
                            produced_files.append(fpath)
                            session.produced_files.add(os.path.basename(fpath))
                            file_item = {"type": "file", "filename": os.path.basename(fpath),
                                         "ftype": result.get("type", ""),
                                         "size": result.get("size", 0)}
                            session.history.append(file_item)
                            yield file_item

                        is_workspace_image = (
                            ok and isinstance(result, dict)
                            and result.get("type") == "image" and result.get("image_base64")
                        )
                        # Never let the raw base64 reach the tool-role JSON: it would
                        # both eat most of TOOL_RESULT_MAX_CHARS on a truncated,
                        # useless fragment and give the model text it can't see an
                        # image from. The real image goes out as its own vision
                        # turn right below instead.
                        content_for_model = result
                        if is_workspace_image:
                            content_for_model = {k: v for k, v in result.items() if k != "image_base64"}
                        session.messages.append({
                            "role": "tool", "tool_name": name,
                            # Keep enough of the result for the model to actually
                            # use what it just read. Readers already cap their text
                            # at ~10k chars; cutting to 4k here threw most of a
                            # document away right after "reading" it.
                            "content": json.dumps(content_for_model, ensure_ascii=False, default=str)[:TOOL_RESULT_MAX_CHARS],
                        })
                        if is_workspace_image:
                            # Ollama tool-role messages don't reliably carry
                            # `images` — the proven mechanism in this codebase is a
                            # user-role message with an `images` list (same as
                            # uploaded images in _build_user_message above). This
                            # makes the *next* round's _stream_chat call actually
                            # show the model the picture it just "read".
                            session.messages.append({
                                "role": "user",
                                "content": f"(Gambar dari Workspace: {result.get('path', '')})",
                                "images": [result["image_base64"]],
                            })
                else:
                    yield {"type": "token", "text": "\n\n_(Batas langkah tool tercapai.)_"}

            # Optional deterministic fallback when the model ignored tools.
            if not any_tool_called and not produced_files:
                async for ev in self._fallback(session, user_text, new_files, model, role, session.workspace_id):
                    if ev.get("type") == "file":
                        produced_files.append(ev.get("_path", ""))
                    yield {k: v for k, v in ev.items() if not k.startswith("_")}

        except Exception as e:
            logger.error("chat stream failed", error=str(e))
            yield {"type": "error", "message": str(e)}

        full_text = "".join(full_response_text_parts)
        await self._remember_turn_end(session, user_text, full_text)

        if settings.ENABLE_OUTPUT_VALIDATION and full_response_text_parts:
            # Detect-and-flag only — every token above has already reached the
            # client by this point, so this cannot redact/prevent, only warn
            # and record (see module docstring "Prompt/output guardrails").
            validation = validate(full_text)
            if not validation.ok:
                await audit_log.record(
                    "output_validator.violation",
                    actor=role or "anonymous",
                    detail={"violations": validation.violations, "session_id": session_id},
                    trace_id=session_id,
                )
                yield {
                    "type": "warning",
                    "message": "Respons ini menandai pelanggaran kebijakan output setelah dikirim: "
                                + ", ".join(validation.violations),
                    "violations": validation.violations,
                }

        yield {"type": "done"}

    # ── Heuristic fallback (small models that don't emit tool_calls) ──
    async def _fallback(
        self, session, user_text, new_files, model, role: Optional[str] = None, workspace_id: Optional[str] = None
    ) -> AsyncIterator[dict]:
        g = user_text.lower()
        registry = self._registry(model)
        # Only acts on an obvious "convert/create file" intent with an uploaded file.
        target = None
        for fmt in ("geojson", "shp", "kml"):
            if fmt in g and any(f.lower().endswith((".kml", ".geojson", ".json", ".shp", ".zip"))
                                for f in new_files):
                src = next(f for f in new_files
                           if f.lower().endswith((".kml", ".geojson", ".json", ".shp", ".zip")))
                target = ("convert_geo", {"file_path": src, "to_format": fmt})
                break
        if not target:
            return
        name, args = target
        yield {"type": "tool_start", "name": name, "args": args}
        result = await self._run_tool(registry, name, args, role, workspace_id)
        ok = not (isinstance(result, dict) and result.get("success") is False)
        yield {"type": "tool_result", "name": name, "ok": ok, "summary": self._summarize_result(result)}
        if ok and isinstance(result, dict) and result.get("file"):
            session.produced_files.add(os.path.basename(result["file"]))
            item = {"type": "file", "filename": os.path.basename(result["file"]),
                    "ftype": result.get("type", ""), "size": result.get("size", 0)}
            session.history.append(item)
            yield {**item, "_path": result["file"]}

    @staticmethod
    def _summarize_result(result: Any) -> str:
        if isinstance(result, dict):
            if result.get("error"):
                return f"Error: {result['error']}"
            if result.get("file"):
                return f"File dibuat: {os.path.basename(result['file'])}"
            # Fase 6 — run_orchestrated_workflow's distinctive result shape
            # (no other tool returns both "final_output" and "escalate").
            # Escalate takes priority: a chat turn must never quietly show
            # a half-finished workflow's output as if it were the real
            # answer — "message" already explains where to go decide it.
            if "final_output" in result and "escalate" in result:
                if result.get("escalate"):
                    return result.get("message") or "Alur kerja ini membutuhkan persetujuan manusia sebelum selesai."
                return str(result.get("final_output", ""))
            for k in ("total_area_ha", "result", "text", "description"):
                if result.get(k):
                    return str(result[k])[:200]
            return "Selesai."
        return str(result)[:200]


# Singleton
chat_engine = ChatEngine()
