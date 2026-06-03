# AI Engine — Asisten File Lokal (Gemma × FastAPI × PostGIS × RQ)

AI engine untuk mining & GIS workflows, powered oleh **Gemma via Ollama** (LLM lokal).

## ✨ Chat Asisten File (fitur utama)

Antarmuka chat gaya ChatGPT yang berjalan sepenuhnya dengan **LLM lokal** untuk **membaca & membuat/mengonversi file**:
PDF · DOCX · TXT · CSV · JSON · gambar (JPG/PNG/TIFF) · GIS (KML/GeoJSON/SHP).

- Buka **`http://localhost:8001/`** (systemd) atau **`:8000/`** (Docker) → langsung chat.
- Unggah file (drag-drop), lalu minta: *"ringkas PDF ini jadi DOCX"*, *"konversi KML ke Shapefile & hitung luas"*, *"resize gambar ke 800px dan ubah ke JPG"*.
- Model bekerja via **tool-calling** (Ollama `/api/chat`), respons di-**stream**, hasil muncul sebagai kartu **unduh**.
- Pilih model `gemma4:e2b` (cepat) atau `gemma4:26b` (untuk hasil formal) lewat selector.

> **Catatan:** Gemma adalah model teks+vision — bisa *membaca* gambar (OCR/deskripsi) dan *mentransformasi* (resize/crop/convert/rotate/compress), **tetapi tidak bisa meng-generate gambar baru**.

Mesin chat: `core/chat/` · API: `api/routes/chat.py` (`/api/v1/chat/*`) · UI: `web/`. OCR butuh binary `tesseract` (opsional; degrade gracefully bila tidak ada).

## Stack
| Layer | Technology |
|---|---|
| API | FastAPI 0.115 + Uvicorn |
| LLM | Gemma via Ollama (`gemma4:e2b` default · `gemma4:26b` formal) |
| Database | PostgreSQL 16 + PostGIS 3.4 |
| Cache/Broker | Redis 7 |
| Queue | RQ (Redis Queue) + Dashboard |
| Container | Docker Compose |

## Quick Start

```bash
# 1. Clone / extract
cd ai_engine

# 2. Setup env
cp .env.example .env
# Edit .env sesuai kebutuhan

# 3. Start semua services
docker compose up -d

# 4. Pull Gemma model (SEKALI saja, ~15GB)
chmod +x scripts/pull_model.sh
./scripts/pull_model.sh

# 5. Check health
curl http://localhost:8000/health/ready
```

## API Endpoints

### 💬 Chat (asisten file)
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/chat/upload` | Unggah file ke sesi |
| POST | `/api/v1/chat/stream` | Chat streaming (SSE) + tool-calling |
| GET | `/api/v1/chat/download/{filename}` | Unduh file hasil |
| GET | `/api/v1/chat/sessions` | Daftar sesi |
| GET | `/api/v1/chat/models` | Model lokal yang tersedia |

### 🤖 AI
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/ai/health` | Check Ollama + Gemma status |
| POST | `/api/v1/ai/chat` | Chat dengan Gemma (sync/stream) |
| POST | `/api/v1/ai/analyze` | Summarize / ekstrak entitas / klasifikasi |
| POST | `/api/v1/ai/geological-summary` | Ringkasan geologi |

### 🗺️ GIS
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/gis/kml/parse` | Parse KML → polygon metadata |
| POST | `/api/v1/gis/kml/to-geojson` | KML → GeoJSON |
| POST | `/api/v1/gis/area/calculate` | Hitung luas (Ha, WGS-84) |
| POST | `/api/v1/gis/wiup/analyze` | Analisis WIUP lengkap + AI narrative |

### ⚡ Pipeline
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/pipeline/wiup-full-report` | KML → Spatial → AI → Report |
| POST | `/api/v1/pipeline/async/enqueue` | Async pipeline via RQ |

## Interactive Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- RQ Dashboard: http://localhost:9181

## Testing

```bash
pip install pytest pytest-asyncio
pytest tests/unit/ -v          # Unit tests (no docker needed)
pytest tests/integration/ -v   # Integration tests (mocked)
```

## Struktur Folder

```
ai_engine/
├── api/            FastAPI app + routes (chat, agent, gis, dokumen, …)
├── core/           Business logic — ai/, chat/ (mesin chat), gis/, document/
├── agent/          Tool registry + tools (readers, writers, gis_io, images)
├── web/            UI chat gaya ChatGPT (index.html, app.js, style.css)
├── templates/      Builder dokumen tambang formal (ReportLab)
├── worker/         RQ background workers
├── db/             SQLAlchemy models
├── tests/          Unit + integration tests
├── scripts/        DB init, model pull
└── backups/        Kode lama yang diarsipkan
```

## Notes untuk Seacoz Integration
- Ganti `OLLAMA_BASE_URL` → URL Ollama di Azure VM
- Atau set `ANTHROPIC_API_KEY` untuk fallback ke Claude API
- PostGIS ready untuk spatial queries WIUP/IUP
- Worker queue siap untuk long-running Gemma jobs
