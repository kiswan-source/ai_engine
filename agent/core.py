import os
"""
AI Agent Core v2 — Integrated Universal Agent.
Loop: plan → execute → evaluate → repeat.
"""
from datetime import datetime
import json, re, time, urllib.request
from typing import Optional
from agent.schemas import StepResult, ToolCall, AgentResult
from agent.memory import Memory
from core.utils.logger import get_logger
from prompts.loader import load_prompt

logger = get_logger(__name__)
MAX_STEPS = 8

# Prompt Versioning (Bab 51, Tahap 37) — content lives at
# prompts/planner/planner_v1.md; version is registered explicitly here,
# never inferred from the highest version number on disk.
PLANNER_SYSTEM = load_prompt("planner", "planner", version=1)


class AIAgent:
    def __init__(self, ollama_url: str = "http://172.29.239.93:11434",
                 model: str = "gemma4:e2b", max_steps: int = MAX_STEPS,
                 role: Optional[str] = None):
        self.ollama_url = ollama_url
        self.model = model
        self.max_steps = max_steps
        self.role = role
        from agent.tools.registry import build_registry
        self.registry = build_registry(ollama_url=ollama_url, model=model)
        self.tools_schema = self.registry.schema_for_planner()
        self.system = PLANNER_SYSTEM.replace("{tools}", self.tools_schema)

    async def run(self, task: str, context: Optional[str] = None) -> dict:
        # ── Baca isi file yang diupload ──────────────────────────
        import os as _os
        file_content = ""
        uploads_dir = _os.path.expanduser("~/ai_engine/uploads")
        _ctx = context if isinstance(context, dict) else {}
        for fname in _ctx.get("uploaded_files", []):
            fpath = _os.path.join(uploads_dir, fname)
            if not _os.path.exists(fpath):
                continue
            ext = fname.split(".")[-1].lower()
            try:
                if ext == "pdf":
                    from agent.tools.readers import read_pdf
                    r = read_pdf(fpath)
                    file_content += f"\n\n[ISI FILE {fname}]:\n{r.get('text','')[:4000]}"
                elif ext in ["csv","txt","json","kml","xml","geojson"]:
                    with open(fpath,"r",encoding="utf-8",errors="ignore") as fh:
                        file_content += f"\n\n[ISI FILE {fname}]:\n{fh.read()[:4000]}"
            except Exception as e:
                file_content += f"\n\n[FILE {fname}: gagal dibaca - {e}]"

        ctx_str = ""
        if isinstance(context, dict):
            ctx_meta = {k:v for k,v in context.items() if k != "uploaded_files"}
            if ctx_meta:
                ctx_str = f"\n\nContext:\n{ctx_meta}"
        elif context:
            ctx_str = f"\n\nContext:\n{context}"

        full_goal = task + file_content + ctx_str
        memory = Memory(goal=full_goal, max_steps=self.max_steps)
        logger.info("Agent v2 started", task=task[:80])
        steps = []

        for step_num in range(1, self.max_steps + 2):
            logger.info(f"Agent step {step_num}/{self.max_steps}")

            # Plan
            tool_call = self._smart_plan(full_goal, memory, step_num)
            logger.info("Agent action", action=tool_call.tool,
                        thought=str(tool_call.input)[:60] if tool_call.input else "")

            if tool_call.tool == "DONE":
                logger.info("Agent finished", steps=step_num-1)
                break

            # Execute
            result = await self._execute(tool_call, step_num)
            memory.add(result)
            steps.append({
                "step": step_num,
                "thought": f"Executing {tool_call.tool}",
                "action": tool_call.tool,
                "action_input": tool_call.input,
                "observation": result.output,
            })

            # Evaluate
            if step_num >= self.max_steps:
                logger.info("Agent max steps reached")
                break

        # Build summary
        output_files = memory.get_output_files()
        success = any(s.success for s in memory.get_steps())
        summary = self._summarize(memory)

        return {
            "success": success,
            "result": summary,
            "steps": steps,
            "output_files": output_files,
        }



    def _smart_plan(self, goal: str, memory: Memory, step_num: int) -> ToolCall:
        """Rule-based planner — reliable, no LLM confusion."""
        import re, os
        g = goal.lower()
        steps = memory.get_steps()
        executed = {s.tool for s in steps if s.success}
        last = memory.last_output()

        # Step 1 — no history
        if not steps:
            # File input? Hanya jika file BENAR-BENAR ada di disk
            pm = re.search(r'[\w/\\.:\-]+\.(?:pdf|txt|docx|csv|json|kml|jpg|png|jpeg|webp)', goal)
            if pm:
                fp = pm.group()
                if os.path.exists(fp):  # cek file ada dulu!
                    reader = self.registry.auto_reader(fp)
                    if reader: return ToolCall(tool=reader, input=fp)
            # Code generation? — cek dari task asli SAJA, bukan isi file
            task_only = goal.split("[ISI FILE")[0].lower()
            # Jika task minta laporan/analisa/jelaskan → langsung analyze_text
            report_keywords = ["laporan","analisa","jelaskan","ringkas",
                                "buat report","summarize","extract","ekstrak"]
            if any(k in task_only for k in report_keywords):
                return ToolCall(tool="analyze_text", input={
                    "text": goal,
                    "instruction": "Buat konten laporan lengkap berdasarkan data yang tersedia dalam format markdown."})
            # Kode hanya jika eksplisit diminta
            for lang, keys in [("html",["buat html","buat dashboard","buat website"]),
                                ("python",["buat script","kode python","buat program"]),
                                ("javascript",["kode javascript","buat js"]),
                                ("css",["buat css","stylesheet"]),
                                ("sql",["buat query","buat sql"])]:
                if any(k in task_only for k in keys):
                    return ToolCall(tool="generate_code", input={
                        "language": lang, "requirement": goal, "context": ""})
            # Default analyze
            return ToolCall(tool="analyze_text", input={
                "text": goal,
                "instruction": "Buat konten laporan lengkap berdasarkan permintaan ini dalam format markdown."})

        # After generate_code → save the file
        if "generate_code" in executed and "write_html" not in executed and "write_txt" not in executed:
            if last and "code" in last:
                code = last.get("code","")
                lang = last.get("language","html")
                # Cari nama file dari goal
                fm = re.search(r'[\w_\-]+\.(?:html|js|py|css|sql|txt)', g)
                fname = fm.group() if fm else f"output.{lang}"
                if lang == "html" or fname.endswith(".html"):
                    return ToolCall(tool="write_html", input={"filename": fname, "content": code})
                else:
                    return ToolCall(tool="write_txt", input={"filename": fname, "content": code})

        # After read_* → analyze
        if last and "text" in last and "analyze_text" not in executed:
            return ToolCall(tool="analyze_text", input={
                "text": last["text"][:5000],
                "instruction": "Ringkas, ekstrak entitas penting, dan buat rekomendasi terstruktur."})

        # After analyze → write file
        if last and "result" in last:
            result_text = last.get("result","")
            fm = re.search(r'[\w_\-]+\.(?:pdf|docx|html|txt|json)', g)
            fname_match = fm.group() if fm else None
            if ("pdf" in g or (fname_match and fname_match.endswith(".pdf"))) and "write_pdf" not in executed:
                fn = fname_match or f"laporan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                return ToolCall(tool="write_pdf", input={"filename":fn,"title": goal[:60] if goal else "Laporan AI Engine","content":result_text})
            if ("docx" in g or "word" in g or (fname_match and fname_match.endswith(".docx"))) and "write_docx" not in executed:
                fn = fname_match or f"laporan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
                return ToolCall(tool="write_docx", input={"filename":fn,"title": goal[:60] if goal else "Laporan AI Engine","content":result_text})
            if ("html" in g or (fname_match and fname_match.endswith(".html"))) and "write_html" not in executed:
                fn = fname_match or "laporan.html"
                return ToolCall(tool="write_html", input={"filename":fn,"content":f"<h1>Laporan</h1><div>{result_text}</div>"})
            if "write_txt" not in executed:
                fn = fname_match or "laporan.txt"
                return ToolCall(tool="write_txt", input={"filename":fn,"content":result_text})

        # Also write additional formats if requested
        if last and ("file" in last or "result" in last):
            result_text = last.get("result", str(last.get("code","")))
            if "json" in g and "write_json" not in executed:
                return ToolCall(tool="write_json", input={"filename":"output.json","data":{"result":result_text,"goal":goal}})

        return ToolCall(tool="DONE")

    def _smart_start(self, goal: str):
        """Step 1 always uses smart rules — no LLM needed."""
        import re
        g = goal.lower()
        # Cari file path di goal
        path_match = re.search(r'[\w/\\.:\-]+\.(?:pdf|txt|docx|csv|json|kml|jpg|png|jpeg|webp)', goal)
        if path_match:
            fp = path_match.group()
            reader = self.registry.auto_reader(fp)
            if reader:
                return ToolCall(tool=reader, input=fp)
        # Generate code? — hanya jika task EKSPLISIT minta kode/program
        # Cek dari task asli (sebelum file content), bukan dari isi file
        task_only = goal.split("[ISI FILE")[0].lower()
        lang = None
        code_keywords = ["buat kode", "generate code", "buatkan script",
                         "buat script", "buat program", "kode python",
                         "kode javascript", "kode html murni", "buatkan html"]
        is_code_request = any(kw in task_only for kw in code_keywords)
        if is_code_request:
            if "javascript" in task_only or " js " in task_only: lang = "javascript"
            elif "python" in task_only or ".py" in task_only: lang = "python"
            elif "css" in task_only: lang = "css"
            elif "sql" in task_only: lang = "sql"
            elif "html" in task_only: lang = "html"
            if lang:
                return ToolCall(tool="generate_code", input={
                    "language": lang,
                    "requirement": goal,
                    "context": ""
                })
        # Default: analyze
        return ToolCall(tool="analyze_text", input={
            "text": goal,
            "instruction": "Analisis permintaan ini dan buat konten terstruktur yang diminta."
        })

    def _plan(self, goal: str, memory: Memory, step_num: int) -> ToolCall:
        context = memory.to_context()
        executed = {s.tool for s in memory.get_steps()}
        prompt = f"""GOAL: {goal}

HISTORY:
{context}

Step {step_num} — what tool next? JSON only:"""
        try:
            payload = json.dumps({
                "model": self.model, "prompt": prompt,
                "system": self.system, "stream": False,
                "options": {"temperature": 0.1, "num_predict": 256}
            }).encode()
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate", data=payload,
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = json.loads(resp.read())["response"].strip()
            return self._parse(raw)
        except Exception as e:
            logger.warning("Planner LLM failed, using fallback", error=str(e))
            return self._fallback_plan(goal, memory)

    def _parse(self, raw: str) -> ToolCall:
        raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
        s, e = raw.find("{"), raw.rfind("}") + 1
        if s >= 0 and e > s:
            try:
                obj = json.loads(raw[s:e])
                return ToolCall(tool=obj.get("tool","DONE"), input=obj.get("input"))
            except Exception:
                pass
        return ToolCall(tool="DONE")

    def _fallback_plan(self, goal: str, memory: Memory) -> ToolCall:
        """Rule-based fallback when LLM planner fails."""
        executed = {s.tool for s in memory.get_steps() if s.success}
        last = memory.last_output()
        g = goal.lower()

        if not memory.get_steps():
            path_match = re.search(r'[\w/\\.:\-]+\.\w{2,5}', goal)
            if path_match:
                fp = path_match.group()
                reader = self.registry.auto_reader(fp)
                if reader: return ToolCall(tool=reader, input=fp)
            return ToolCall(tool="analyze_text",
                input={"text": goal, "instruction": "Analisis permintaan dan buat rencana kerja."})

        if last and "text" in last and "analyze_text" not in executed:
            return ToolCall(tool="analyze_text",
                input={"text": last["text"][:5000],
                       "instruction": "Ringkas, ekstrak entitas penting, dan buat rekomendasi."})

        if last and "result" in last:
            result_text = last.get("result", "")
            if "pdf" in g and "write_pdf" not in executed:
                return ToolCall(tool="write_pdf",
                    input={"filename": f"laporan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf","title": goal[:60] if goal else "Laporan AI Engine","content":result_text})
            if ("word" in g or "docx" in g) and "write_docx" not in executed:
                return ToolCall(tool="write_docx",
                    input={"filename": f"laporan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx","title": goal[:60] if goal else "Laporan AI Engine","content":result_text})
            if "html" in g and "write_html" not in executed:
                return ToolCall(tool="write_html",
                    input={"filename": f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html","content":f"<h1>Laporan</h1><div>{result_text}</div>"})
            if "write_txt" not in executed:
                return ToolCall(tool="write_txt",
                    input={"filename":"laporan_agent.txt","content":result_text})

        return ToolCall(tool="DONE")

    async def _execute(self, tool_call: ToolCall, step_num: int) -> StepResult:
        if not self.registry.has(tool_call.tool):
            return StepResult(step=step_num, tool=tool_call.tool, input=tool_call.input,
                output=None, success=False, error=f"Tool '{tool_call.tool}' not in registry")
        try:
            output = self.registry.execute(tool_call.tool, tool_call.input, role=self.role)
            if isinstance(output, dict) and output.get("success") is False:
                success = False
            elif isinstance(output, dict) and "error" in output and "success" not in output:
                success = False
            else:
                success = True
            if not success:
                logger.warning("Tool failed", tool=tool_call.tool, error=str(output.get("error","unknown") if isinstance(output,dict) else output)[:200])
            else:
                logger.info("Tool success", tool=tool_call.tool, has_file="file" in (output or {}))
            return StepResult(step=step_num, tool=tool_call.tool, input=tool_call.input,
                output=output, success=success, error=str(output.get("error","")) if not success and isinstance(output,dict) else None)
        except PermissionError as e:
            logger.warning("Tool access denied", tool=tool_call.tool, role=self.role, error=str(e))
            from security import audit_log
            await audit_log.record("tool_access.denied", actor=self.role or "anonymous",
                                    detail={"tool": tool_call.tool})
            return StepResult(step=step_num, tool=tool_call.tool, input=tool_call.input,
                output=None, success=False, error=str(e))
        except Exception as e:
            logger.error("Tool exception", tool=tool_call.tool, error=str(e))
            return StepResult(step=step_num, tool=tool_call.tool, input=tool_call.input,
                output=None, success=False, error=str(e))

    def _summarize(self, memory: Memory) -> str:
        steps = memory.get_steps()
        files = memory.get_output_files()
        lines = [f"## Hasil Agent v2\n", f"**Steps:** {len(steps)} | **Files:** {len(files)}"]
        if files:
            lines.append("\n**File Output:**")
            for f in files: lines.append(f"- {f}")
        lines.append("\n**Detail:**")
        for s in steps:
            icon = "✓" if s.success else "✗"
            lines.append(f"{icon} Step {s.step}: `{s.tool}`")
            if s.error: lines.append(f"  Error: {s.error}")
            elif s.success and isinstance(s.output, dict):
                if "file" in s.output: lines.append(f"  → {s.output['file']}")
                elif "result" in s.output: lines.append(f"  → {str(s.output['result'])[:100]}…")
                elif "text" in s.output: lines.append(f"  → Read {s.output.get('char_count',0)} chars")
        return "\n".join(lines)

