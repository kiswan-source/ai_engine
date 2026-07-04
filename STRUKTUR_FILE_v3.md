# STRUKTUR FILE AI ENGINE
## Asisten File Lokal (Gemma × FastAPI × PostGIS × RQ) — v3.0
## Status: Chat Engine Era — 4 Juli 2026

> Menggantikan `STRUKTUR_FILE_v2.md` (28 Mei 2026). Kode eksperimental "enhanced"
> (`core_enhanced.py`, `agent_enhanced.py`, `skills/`, `logger_enhanced.py`, `*.bak`)
> sudah **diarsipkan** ke `backups/archived_20260602/` — tidak lagi ada di pohon aktif.

```
ai_engine/
│
├── 📄 .env / .env.example            ← config (GEMMA_MODEL, OLLAMA_BASE_URL, DATABASE_URL, REDIS_URL)
├── 📄 CLAUDE.md                      ← [AKTIF] panduan arsitektur untuk Claude Code
├── 📄 README.md                      ← [AKTIF] dokumentasi + badge CI
├── 📄 STRUKTUR_FILE_v3.md            ← [BARU] dokumen ini (v2 diarsip)
├── 📄 docker-compose.yml             ← orkestrasi service (api, worker_ai, worker_gis, redis, postgres, rq-dashboard)
├── 📄 requirements.txt / pytest.ini  ← dependencies + config test (asyncio_mode=auto, testpaths=tests)
├── 📄 audit.log                      ← [AKTIF] log runtime
│
├── 🌐 web/                           ← [PRIMARY] UI ChatGPT-style (vanilla JS, no build) — dilayani di /
│   ├── index.html                    ← markup chat
│   ├── app.js                        ← parser SSE, render markdown + tool chips + file cards, drag-drop, model selector
│   └── style.css
│
├── 💬 core/chat/                     ← [PRIMARY] CHAT ENGINE (fitur utama, §7 CLAUDE.md)
│   ├── __init__.py
│   ├── engine.py                     ← ChatEngine: loop tool-calling native ke Ollama /api/chat, streaming,
│   │                                    auto-read file, vision base64, resolve_path (uploads/→reports/), _fallback GIS
│   └── tool_schemas.py               ← TOOL_SCHEMAS: JSON-schema tools yang di-expose ke model (nama = registry)
│
├── 🤖 agent/                         ← AUTONOMOUS AGENT (rule-based, jalur lama /api/v1/agent/run)
│   ├── __init__.py
│   ├── core.py                       ← AIAgent: loop plan→execute→evaluate (max 8 step), _smart_plan rule-based
│   ├── memory.py                     ← agent memory
│   ├── schemas.py                    ← pydantic schemas
│   │
│   └── 🛠️  tools/                    ← TOOL REGISTRY (dishare chat engine + agent)
│       ├── __init__.py
│       ├── registry.py               ← ToolRegistry.build_registry(): daftar semua tool + auto_reader()
│       ├── readers.py                ← read_pdf/txt/docx/csv/json/image
│       ├── writers.py                ← write_pdf/docx/html/txt/json
│       ├── analyzers.py              ← analyze_text (wrap Ollama), generate_code
│       ├── gis_io.py                 ← [BARU] read/write geojson/shp, convert_geo (KML↔GeoJSON↔SHP via fiona/shapely)
│       └── images.py                 ← [BARU] image convert/resize/crop/rotate/compress, images_to_pdf (Pillow)
│
├── 🌐 api/                           ← FASTAPI APPLICATION
│   ├── __init__.py
│   ├── config.py                     ← pydantic-settings (baca .env)
│   ├── main.py                       ← app + wiring 9 router; / (web), /ui + /v3 (legacy UI)
│   ├── middleware.py                 ← request logging, rate limiting
│   │
│   └── 📡 routes/                    ← API ENDPOINTS (hanya yang di-wire di main.py yang live)
│       ├── __init__.py
│       ├── chat.py                   ← [PRIMARY] /api/v1/chat/{stream,upload,download,sessions,models} (SSE)
│       ├── dokumen.py                ← [BARU] /api/dokumen/* — generasi dokumen tambang formal (PDF/DOCX)
│       ├── agent.py                  ← /api/v1/agent/run (agent rule-based lama)
│       ├── ai.py                     ← /api/v1/ai/{chat,analyze,geological-summary}
│       ├── gis.py                    ← /api/v1/gis/{kml,area,wiup,geojson}
│       ├── pipeline.py               ← /api/v1/pipeline/{wiup-full-report,async/enqueue}
│       ├── docs.py                   ← /api/v1/docs/* upload-and-analyze
│       ├── files.py                  ← /reports/*, /upload, /uploads
│       └── health.py                 ← /health/, /health/ready (cek Ollama + Gemma)
│
├── ⚙️  core/                         ← BUSINESS LOGIC
│   ├── __init__.py
│   │
│   ├── 🧠 ai/                        ← AI INTEGRATION
│   │   ├── gemma_client.py           ← async Ollama HTTP client: retry (tenacity), streaming, cache key SHA-256
│   │   ├── prompt_templates.py       ← template prompt engineering
│   │   └── cache.py                  ← caching respons AI via Redis (TTL)
│   │
│   ├── 🗺️  gis/                      ← GIS PROCESSING
│   │   └── processor.py              ← parse KML (lxml), area/centroid/bbox (shapely + pyproj WGS-84)
│   │
│   ├── 📝 document/                  ← DOCUMENT GENERATION
│   │   └── generator.py              ← [BARU] generate_laporan_wilayah/produksi, generate_dokumen_wiup, enrich_with_ai
│   │
│   ├── 📊 report/                    ← (placeholder — hanya __init__.py)
│   │
│   └── 🔧 utils/
│       └── logger.py                 ← structlog JSON logger — get_logger(__name__)
│
├── 🧾 templates/                     ← [BARU] REPORTLAB BUILDERS (dokumen tambang Indonesia)
│   ├── dokumen_wiup.py               ← builder WIUP + KOMODITAS_INFO (metadata komoditas)
│   ├── laporan_wilayah.py            ← builder laporan wilayah
│   └── laporan_produksi.py           ← builder laporan produksi
│
├── 🗄️  db/                           ← DATABASE LAYER (PostgreSQL 16 + PostGIS, SQLAlchemy async)
│   ├── connection.py                 ← get_session() dependency, init_db() (auto-create table, no Alembic)
│   └── models.py                     ← AIJob, GISProject, Document
│
├── ⚡ worker/                        ← BACKGROUND JOBS (RQ)
│   ├── ai/       worker_ai.py + jobs_ai.py          ← ai_queue
│   ├── gis/      worker_gis.py + jobs_gis.py        ← gis_queue
│   └── pipeline/ jobs_pipeline.py                   ← pipeline_queue (tak ada service khusus di compose)
│
├── 🐳 docker/                        ← Dockerfile.api + Dockerfile.worker
├── 📜 scripts/                       ← init_db.sql + pull_model.sh
│
├── 🧪 tests/                         ← TESTING (pytest, asyncio auto)
│   ├── integration/test_api.py       ← integration (mocked)
│   └── unit/ test_gis_processor.py + test_file_tools.py  ← [test_file_tools BARU]
│
├── ⚙️  .github/workflows/ci.yml      ← [BARU] CI: pytest --cov di Python 3.12, tiap push/PR ke main
│
├── 📁 uploads/                       ← file input user (volume-mounted)
├── 📁 reports/                       ← file output hasil (volume-mounted, di-download via /api/v1/chat/download)
│
├── 🗃️  backups/                      ← [ARSIP] jangan dihapus
│   ├── archived_20260602/            ← core_enhanced, agent_enhanced, toolkit, logger_enhanced, skills/
│   └── archived_20260603/            ← *.kml.orig
│
└── 🐍 venv/                          ← Python virtual environment
```

---

## PERUBAHAN BESAR SEJAK v2 (28 Mei → 4 Juli 2026)

### 🆕 Ditambahkan
| Area | File | Fungsi |
|------|------|--------|
| Chat engine | `core/chat/engine.py`, `tool_schemas.py` | **Fitur utama** — chat streaming tool-calling native |
| UI baru | `web/index.html`, `app.js`, `style.css` | UI ChatGPT-style di `/` (vanilla JS) |
| Route chat | `api/routes/chat.py` | Endpoint SSE `/api/v1/chat/*` |
| Dokumen | `api/routes/dokumen.py`, `core/document/generator.py`, `templates/*` | Generasi dokumen tambang formal |
| GIS/Image tools | `agent/tools/gis_io.py`, `agent/tools/images.py` | Konversi geospasial + transformasi gambar |
| Test | `tests/unit/test_file_tools.py` | Unit test file tools |
| CI | `.github/workflows/ci.yml` | GitHub Actions |

### 📦 Diarsipkan (ke `backups/archived_20260602/`)
`core_enhanced.py` · `agent_enhanced.py` · `toolkit.py` · `logger_enhanced.py` · `agent/skills/`
— beserta semua file `.bak`. Jangan diresurrect tanpa alasan.

---

## DUA JALUR AGENT (penting)
- **Chat engine** (`core/chat/`) — jalur modern: LLM-driven *native tool-calling* via Ollama `/api/chat`. Gunakan untuk pekerjaan baru.
- **`agent/core.py`** (`AIAgent`) — planner *rule-based* (`_smart_plan`), dipertahankan hanya untuk `/api/v1/agent/run`.
- Keduanya berbagi `agent/tools/registry.py`. **Menambah tool baru:** implement fungsi → `registry.register(...)` di `build_registry()` → tambah schema di `core/chat/tool_schemas.py` (nama harus cocok).

---

## DEPLOYMENT (dari docker-compose.yml + CLAUDE.md)
| Mode | Port | Cara |
|------|------|------|
| Docker Compose | 8000 | `docker compose up -d` |
| systemd (WSL) | 8001 | `ai-engine.service` (auto-start boot) |

- Ollama di host: `http://172.29.239.93:11434` (WSL host IP). Model default `gemma4:e2b` (7.2 GB, cepat); `gemma4:26b` untuk laporan formal.
- Aliran file: upload → `uploads/`, output → `reports/`. `ChatEngine.resolve_path` cari arg path di `uploads/` lalu `reports/` (bikin rantai multi-step jalan).
```
