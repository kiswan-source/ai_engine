"""File readers: PDF, TXT, DOCX, CSV, JSON, Image."""
import os, json, csv
from typing import Dict, Any

def read_pdf(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append({"page": i+1, "text": text.strip()})
        full_text = "\n\n".join(p["text"] for p in pages if p["text"])
        return {"source": file_path, "type": "pdf", "pages": len(reader.pages),
                "text": full_text[:10000], "truncated": len(full_text)>10000, "char_count": len(full_text)}
    except ImportError:
        return {"error": "pypdf not installed"}
    except Exception as e:
        return {"error": str(e), "source": file_path}

def read_txt(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return {"source": file_path, "type": "txt", "text": content[:10000],
                "truncated": len(content)>10000, "char_count": len(content), "line_count": content.count("\n")}
    except Exception as e:
        return {"error": str(e)}

def read_docx(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        from docx import Document
        doc = Document(file_path)
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        full_text = "\n".join(paragraphs)
        return {"source": file_path, "type": "docx", "text": full_text[:10000],
                "paragraph_count": len(paragraphs), "char_count": len(full_text)}
    except Exception as e:
        return {"error": str(e)}

def read_csv(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        rows = []
        with open(file_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)
            headers = list(reader.fieldnames or [])
            for i, row in enumerate(reader):
                if i >= 500: break
                rows.append(dict(row))
        summary = ",".join(headers) + "\n" + "\n".join(",".join(str(v) for v in r.values()) for r in rows[:20])
        return {"source": file_path, "type": "csv", "headers": headers,
                "row_count": len(rows), "rows": rows[:50], "text": summary}
    except Exception as e:
        return {"error": str(e)}

def read_json(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        text = json.dumps(data, indent=2, ensure_ascii=False)
        return {"source": file_path, "type": "json", "data": data,
                "text": text[:10000], "truncated": len(text)>10000}
    except Exception as e:
        return {"error": str(e)}

def read_image(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        from PIL import Image
        img = Image.open(file_path)
        w, h = img.size
        desc = f"Image: {w}x{h}px, mode={img.mode}"
        try:
            import pytesseract
            ocr = pytesseract.image_to_string(img, lang="eng+ind").strip()
        except Exception:
            ocr = ""
        return {"source": file_path, "type": "image", "description": desc,
                "width": w, "height": h,
                "text": ocr if ocr else f"[Image: {os.path.basename(file_path)}, no OCR text]",
                "has_ocr_text": bool(ocr)}
    except ImportError:
        return {"error": "Pillow not installed"}
    except Exception as e:
        return {"error": str(e)}
