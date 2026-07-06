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
"""
import os
import json
import base64
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from api.config import settings
from agent.tools.registry import build_registry
from agent.tools.readers import read_pdf, read_docx, read_csv, read_txt, read_json
from core.chat.tool_schemas import TOOL_SCHEMAS, EXPOSED_TOOL_NAMES
from core.utils.logger import get_logger

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
# the model (Bab 69.5, Tahap 23) — see _run_tool.
WORKSPACE_TOOL_NAMES = {"workspace_list_files", "workspace_read_file"}

SYSTEM_PROMPT = """Kamu adalah asisten AI lokal untuk pekerjaan file & GIS, berjalan dengan model Gemma.
Kamu bisa membaca dan membuat/mengonversi file: PDF, DOCX, TXT, CSV, JSON, gambar (JPG/PNG/TIFF), dan GIS (KML/GeoJSON/SHP).

ATURAN:
- Bila pengguna meminta membaca, mengonversi, atau membuat file, PANGGIL tool yang sesuai. Jangan mengarang isi file.
- Gunakan PERSIS path file yang diberikan pada bagian "File terlampir" sebagai argumen `file_path`.
- Untuk hasil output, beri nama file yang singkat dan jelas (mis. "ringkasan.pdf", "hasil.geojson").
- Setelah tool selesai, susun laporan yang LENGKAP, terstruktur, dan informatif dalam Bahasa Indonesia berdasarkan SELURUH data yang dikembalikan tool — bukan jawaban seadanya. Pakai heading, poin, dan tabel markdown bila membantu. Akhiri dengan observasi/kesimpulan singkat yang relevan.
- JANGAN PERNAH mengarang angka. Sebutkan angka (luas, koordinat, jumlah) PERSIS seperti yang dikembalikan tool. Bila tool belum memberi angka itu, panggil tool dulu.
- Tulis angka sebagai teks biasa (mis. 11.3507 Ha). JANGAN memakai format matematika LaTeX atau tanda `$...$` — UI tidak merendernya.
- GIS: untuk pertanyaan LUAS/centroid/jumlah poligon, pakai read_kml / read_geojson / read_shp — hasilnya memuat `total_area_ha` (HEKTAR), `mean_area_ha`, `largest_polygon`, `smallest_polygon`, `total_vertices`, dan daftar `polygons` (nama, area_ha, centroid, bbox). JANGAN memakai convert_geo hanya untuk menghitung luas; convert_geo hanya untuk mengubah format file.
- Untuk hasil GIS, buat laporan mencakup: jumlah bidang/poligon (`polygon_count`), total luas, rata-rata luas, poligon terbesar & terkecil beserta namanya, lalu TABEL rincian tiap bidang yang tersedia (Nama | Luas (Ha) | Centroid). Bila `polygons_truncated` true, sebutkan bahwa hanya `polygons_shown` dari `polygon_count` bidang yang dirinci sedangkan agregat sudah mencakup semua.
- Bila informasi yang ditanyakan sudah ada di hasil tool sebelumnya pada percakapan ini, jawab langsung tanpa memanggil tool lagi.
- Kamu TIDAK bisa membuat/menggambar gambar baru; untuk gambar hanya bisa baca, konversi, resize, crop, rotate, kompres.
- Bila sesi ini terhubung ke sebuah Project Workspace (lihat catatan "[Project Workspace terhubung]" di pesan pengguna), dan permintaan pengguna merujuk pekerjaan/dokumen pada Project itu (bukan file yang diunggah langsung), PANGGIL `workspace_list_files` dulu untuk melihat daftar filenya, lalu `workspace_read_file` untuk membaca isi salah satu file sebelum menjawab. Jangan mengarang isi file Workspace.
"""


class Session:
    def __init__(self, session_id: str, owner: Optional[str] = None, workspace_id: Optional[str] = None):
        self.id = session_id
        self.owner = owner  # Principal.api_key of whoever created it (Tahap 22); None if unset
        self.workspace_id = workspace_id  # bound Project Workspace (Tahap 23); None if unset
        self.messages: List[Dict[str, Any]] = []   # Ollama-format chat history
        self.history: List[Dict[str, Any]] = []     # display items for the UI
        self.files: List[str] = []  # absolute paths of uploaded files

    def add_file(self, path: str):
        if path not in self.files:
            self.files.append(path)


class ChatEngine:
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.default_model = settings.GEMMA_MODEL
        self._registries: Dict[str, Any] = {}
        self.sessions: Dict[str, Session] = {}

    # ── Session helpers ──
    def get_session(
        self, session_id: str, owner: Optional[str] = None, workspace_id: Optional[str] = None
    ) -> Session:
        """Fetch or create a session. ``owner`` is only recorded at creation —
        an existing session's owner never changes (Tahap 22: first caller to
        touch a session_id owns it; api/routes/chat.py enforces this before
        calling here, this method itself doesn't check anything). ``workspace_id``
        is first-non-null-wins (Tahap 23): binds on creation, or on a later
        call if the session didn't have one yet — never overwrites an
        already-bound value."""
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(session_id, owner=owner, workspace_id=workspace_id)
        else:
            session = self.sessions[session_id]
            if session.workspace_id is None and workspace_id is not None:
                session.workspace_id = workspace_id
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
            parts.append(
                "\n\n[Project Workspace terhubung — pakai tool workspace_list_files/"
                "workspace_read_file untuk membaca isinya bila relevan dengan permintaan ini.]"
            )

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
        self, registry, name: str, args: Any, role: Optional[str] = None, workspace_id: Optional[str] = None
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

    # ── Main entry: stream a full assistant turn ──
    async def stream_run(self, session_id: str, user_text: str,
                         new_files: Optional[List[str]] = None,
                         model: Optional[str] = None,
                         role: Optional[str] = None,
                         owner: Optional[str] = None,
                         workspace_id: Optional[str] = None) -> AsyncIterator[Dict[str, Any]]:
        model = model or self.default_model
        session = self.get_session(session_id, owner=owner, workspace_id=workspace_id)
        new_files = [self.resolve_path(f) for f in (new_files or [])]
        for f in new_files:
            session.add_file(f)

        if not session.messages:
            session.messages.append({"role": "system", "content": SYSTEM_PROMPT})
        session.messages.append(self._build_user_message(session, user_text, new_files))
        session.history.append({"type": "user", "content": user_text,
                                "files": [os.path.basename(f) for f in new_files]})

        produced_files: List[str] = []
        any_tool_called = False

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
                        result = await self._run_tool(registry, name, args, role, session.workspace_id)
                        ok = not (isinstance(result, dict) and (result.get("success") is False or
                                  ("error" in result and "success" not in result)))
                        summary = self._summarize_result(result)
                        yield {"type": "tool_result", "name": name, "ok": ok, "summary": summary}

                        if ok and isinstance(result, dict) and result.get("file"):
                            fpath = result["file"]
                            produced_files.append(fpath)
                            file_item = {"type": "file", "filename": os.path.basename(fpath),
                                         "ftype": result.get("type", ""),
                                         "size": result.get("size", 0)}
                            session.history.append(file_item)
                            yield file_item

                        session.messages.append({
                            "role": "tool", "tool_name": name,
                            # Keep enough of the result for the model to actually
                            # use what it just read. Readers already cap their text
                            # at ~10k chars; cutting to 4k here threw most of a
                            # document away right after "reading" it.
                            "content": json.dumps(result, ensure_ascii=False, default=str)[:TOOL_RESULT_MAX_CHARS],
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
            for k in ("total_area_ha", "result", "text", "description"):
                if result.get(k):
                    return str(result[k])[:200]
            return "Selesai."
        return str(result)[:200]


# Singleton
chat_engine = ChatEngine()
