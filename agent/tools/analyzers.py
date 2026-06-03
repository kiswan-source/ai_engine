"""AI text analyzer and code generator using Ollama/Gemma."""
import json, urllib.request, urllib.error
from typing import Dict, Any, Callable

def make_analyzer(ollama_url: str, model: str) -> Callable:
    def analyze_text(text: str, instruction: str = "Ringkas dan ekstrak poin penting dari teks ini.") -> Dict[str, Any]:
        if not text or not text.strip():
            return {"error": "Empty text", "result": ""}
        prompt = f"{instruction}\n\nTEXT:\n{text[:6000]}\n\nRespond in Indonesian. Be structured."
        payload = json.dumps({"model": model, "prompt": prompt, "stream": False,
                              "options": {"temperature": 0.3, "num_predict": 1024}}).encode()
        try:
            req = urllib.request.Request(f"{ollama_url}/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
                return {"success": True, "result": data.get("response","").strip(),
                        "model": model, "instruction": instruction}
        except Exception as e:
            return _fallback_analyze(text, instruction)
    return analyze_text

def make_code_generator(ollama_url: str, model: str) -> Callable:
    def generate_code(language: str, requirement: str, context: str = "") -> Dict[str, Any]:
        system = f"Kamu adalah expert programmer. Generate kode {language.upper()} yang bersih dan lengkap. Output HANYA kode, gunakan komentar untuk penjelasan."
        prompt = f"Buat kode {language} untuk: {requirement}"
        if context: prompt += f"\n\nKonteks:\n{context}"
        payload = json.dumps({"model": model, "prompt": prompt, "system": system,
                              "stream": False, "options": {"temperature": 0.2, "num_predict": 2048}}).encode()
        try:
            req = urllib.request.Request(f"{ollama_url}/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode())
                code = data.get("response","").strip()
                if "```" in code:
                    parts = code.split("```")
                    for p in parts[1::2]:
                        lines = p.strip().split("\n")
                        if lines[0].lower() in (language,"html","js","py","python","javascript","sql","css","json",""):
                            code = "\n".join(lines[1:]).strip()
                            break
                return {"success": True, "language": language, "code": code, "model": model}
        except Exception as e:
            return {"success": False, "error": str(e), "language": language, "code": ""}
    return generate_code

def _fallback_analyze(text: str, instruction: str) -> Dict[str, Any]:
    words = text.split()
    stop = {"yang","dan","di","ke","dari","untuk","dengan","ini","itu","adalah","pada","the","a","an","of","to","in"}
    freq = {}
    for w in words:
        w = w.lower().strip(".,;:!?()")
        if len(w) > 3 and w not in stop:
            freq[w] = freq.get(w, 0) + 1
    keywords = sorted(freq, key=lambda x: freq[x], reverse=True)[:8]
    result = f"## Analisis (Fallback)\n**Statistik:** {len(words)} kata, {len(text)} karakter\n**Kata kunci:** {', '.join(keywords)}\n**Ringkasan:** {' '.join(text.split()[:50])}..."
    return {"success": True, "result": result, "model": "fallback", "instruction": instruction}
