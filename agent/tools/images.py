"""
Image tools (Pillow) — convert / resize / crop / rotate / compress / images→PDF.

Note: this is image *editing/transformation*, not image *generation*. A local
text LLM (Gemma) cannot synthesise new images; it can only read them (see
readers.read_image) and drive these deterministic transforms.
"""
import os
from typing import Any, Dict, List

from core.utils.logger import get_logger

logger = get_logger(__name__)

OUTPUT_DIR = os.path.expanduser("~/ai_engine/reports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Pillow save format names keyed by lowercase extension.
_FORMAT = {
    "jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "tif": "TIFF",
    "tiff": "TIFF", "webp": "WEBP", "bmp": "BMP", "gif": "GIF",
}


def _out_path(filename: str) -> str:
    return filename if os.path.dirname(filename) else os.path.join(OUTPUT_DIR, filename)


def _open(file_path: str):
    from PIL import Image
    return Image.open(file_path)


def _save(img, out_path: str, fmt: str = None, quality: int = None):
    """Save image, flattening alpha to RGB when the target can't hold it."""
    ext = os.path.splitext(out_path)[1].lower().lstrip(".")
    pil_fmt = fmt or _FORMAT.get(ext, "PNG")
    if pil_fmt in ("JPEG", "BMP") and img.mode in ("RGBA", "P", "LA"):
        from PIL import Image
        bg = Image.new("RGB", img.size, (255, 255, 255))
        img_rgb = img.convert("RGBA")
        bg.paste(img_rgb, mask=img_rgb.split()[-1])
        img = bg
    kwargs = {}
    if quality is not None and pil_fmt in ("JPEG", "WEBP"):
        kwargs["quality"] = int(quality)
        kwargs["optimize"] = True
    img.save(out_path, pil_fmt, **kwargs)
    return out_path


def _result(out_path: str, **extra) -> Dict[str, Any]:
    return {"success": True, "file": out_path, "filename": os.path.basename(out_path),
            "size": os.path.getsize(out_path), "type": "image", **extra}


def image_convert(file_path: str, to_format: str, filename: str = None) -> Dict[str, Any]:
    """Convert an image to another format (jpg/png/tiff/webp/bmp/gif)."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    fmt = (to_format or "").lower().lstrip(".")
    if fmt not in _FORMAT:
        return {"error": f"Unsupported target format: {to_format}"}
    try:
        base = os.path.splitext(os.path.basename(filename or file_path))[0]
        out = _out_path(f"{base}.{fmt}")
        with _open(file_path) as img:
            _save(img, out, fmt=_FORMAT[fmt])
        return _result(out, format=fmt)
    except Exception as e:
        return {"success": False, "error": str(e)}


def image_resize(file_path: str, width: int = None, height: int = None,
                 filename: str = None) -> Dict[str, Any]:
    """Resize an image. Give width and/or height; aspect ratio kept if one is omitted."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    if not width and not height:
        return {"error": "Provide width and/or height"}
    try:
        from PIL import Image
        with _open(file_path) as img:
            w, h = img.size
            if width and not height:
                height = int(h * (int(width) / w))
            elif height and not width:
                width = int(w * (int(height) / h))
            resized = img.resize((int(width), int(height)), Image.LANCZOS)
            base, ext = os.path.splitext(os.path.basename(filename or file_path))
            out = _out_path(f"{base}_{width}x{height}{ext or '.png'}")
            _save(resized, out)
        return _result(out, width=int(width), height=int(height))
    except Exception as e:
        return {"success": False, "error": str(e)}


def image_crop(file_path: str, left: int, top: int, right: int, bottom: int,
               filename: str = None) -> Dict[str, Any]:
    """Crop an image to the box (left, top, right, bottom) in pixels."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        with _open(file_path) as img:
            cropped = img.crop((int(left), int(top), int(right), int(bottom)))
            base, ext = os.path.splitext(os.path.basename(filename or file_path))
            out = _out_path(f"{base}_crop{ext or '.png'}")
            _save(cropped, out)
        return _result(out)
    except Exception as e:
        return {"success": False, "error": str(e)}


def image_rotate(file_path: str, degrees: float, filename: str = None) -> Dict[str, Any]:
    """Rotate an image counter-clockwise by `degrees`, expanding the canvas."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        with _open(file_path) as img:
            rotated = img.rotate(float(degrees), expand=True)
            base, ext = os.path.splitext(os.path.basename(filename or file_path))
            out = _out_path(f"{base}_rot{int(degrees)}{ext or '.png'}")
            _save(rotated, out)
        return _result(out, degrees=float(degrees))
    except Exception as e:
        return {"success": False, "error": str(e)}


def image_compress(file_path: str, quality: int = 70, filename: str = None) -> Dict[str, Any]:
    """Compress to JPEG/WEBP at the given quality (1-95) to shrink file size."""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    try:
        base, ext = os.path.splitext(os.path.basename(filename or file_path))
        ext = ext.lower().lstrip(".")
        if ext not in ("jpg", "jpeg", "webp"):
            ext = "jpg"
        out = _out_path(f"{base}_q{quality}.{ext}")
        with _open(file_path) as img:
            _save(img, out, fmt=_FORMAT[ext], quality=quality)
        return _result(out, quality=int(quality))
    except Exception as e:
        return {"success": False, "error": str(e)}


def images_to_pdf(file_paths: List[str], filename: str = "images.pdf") -> Dict[str, Any]:
    """Combine one or more images into a single PDF (one image per page)."""
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    paths = [p for p in file_paths if os.path.exists(p)]
    if not paths:
        return {"error": "No valid image files provided"}
    try:
        from PIL import Image
        imgs = [Image.open(p).convert("RGB") for p in paths]
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        out = _out_path(filename)
        imgs[0].save(out, "PDF", save_all=True, append_images=imgs[1:])
        for im in imgs:
            im.close()
        return {"success": True, "file": out, "filename": os.path.basename(out),
                "size": os.path.getsize(out), "type": "pdf", "page_count": len(paths)}
    except Exception as e:
        return {"success": False, "error": str(e)}
