# STRUKTUR FILE AI ENGINE
## Mining Intelligence Terminal v2.0
## Status: Post-Integration — 28 Mei 2026

```
ai_engine/
│
├── 📄 .env                          ← [DIUPDATE] GEMMA_MODEL=gemma4:e2b, OLLAMA_BASE_URL=localhost
├── 📄 .env.example                  ← [LAMA] template env
├── 📄 ai_engine_ui.html             ← [DIUPDATE] UI baru — Industrial Mining Terminal v2.0
├── 📄 docker-compose.yml            ← [LAMA] Docker orchestration
├── 📄 requirements.txt              ← [LAMA] dependencies Python
├── 📄 pytest.ini                    ← [LAMA] konfigurasi testing
├── 📄 audit.log                     ← [AKTIF] log sistem berjalan
├── 📄 README.md                     ← [LAMA] dokumentasi
│
├── 🤖 agent/                        ← AUTONOMOUS AGENT
│   ├── __init__.py
│   ├── core.py                      ← [DIUPDATE] fix filename unik timestamp, judul dari task
│   ├── core.py.bak                  ← [BACKUP] core.py sebelum diupdate
│   ├── core_enhanced.py             ← [BARU] multi-step planner, intent detector, retry logic
│   ├── memory.py                    ← [LAMA] agent memory
│   ├── schemas.py                   ← [LAMA] pydantic schemas
│   ├── tools.py                     ← [LAMA] tool definitions
│   │
│   ├── 🛠️  tools/                   ← EXISTING TOOLS
│   │   ├── __init__.py
│   │   ├── analyzers.py             ← [LAMA] analyze_text, extract_entities
│   │   ├── readers.py               ← [LAMA] read_pdf, read_csv, read_json
│   │   ├── registry.py              ← [LAMA] tool registry
│   │   ├── writers.py               ← [DIUPDATE] fix duplikasi konten PDF
│   │   └── writers.py.bak           ← [BACKUP] writers.py sebelum diupdate
│   │
│   └── 🎯 skills/                   ← [BARU] SKILL SYSTEM
│       ├── __init__.py              ← [BARU] SkillRegistry + run_multi_output()
│       ├── generate_report.py       ← [BARU] skill PDF report generation
│       └── generate_dashboard.py    ← [BARU] skill HTML dashboard + convert_file
│
├── 🌐 api/                          ← FASTAPI APPLICATION
│   ├── __init__.py
│   ├── config.py                    ← [LAMA] settings & environment config
│   ├── main.py                      ← [DIUPDATE] +CORS, +/ui endpoint, +agent_enhanced router
│   ├── middleware.py                ← [LAMA] request logging, rate limiting
│   │
│   └── 📡 routes/                   ← API ENDPOINTS
│       ├── __init__.py
│       ├── agent.py                 ← [LAMA] POST /api/v1/agent/run (endpoint utama)
│       ├── agent_enhanced.py        ← [BARU] multi-output, SSE streaming, /skills endpoint
│       ├── ai.py                    ← [LAMA] /api/v1/ai/chat, /analyze, /geological-summary
│       ├── docs.py                  ← [LAMA] /api/v1/docs/upload-and-analyze
│       ├── files.py                 ← [LAMA] /reports, /upload, /uploads
│       ├── gis.py                   ← [LAMA] /api/v1/gis/kml, /area, /wiup, /geojson
│       ├── health.py                ← [LAMA] GET /health/, /health/ready
│       └── pipeline.py              ← [LAMA] /api/v1/pipeline/wiup-full-report, /async/enqueue
│
├── ⚙️  core/                        ← BUSINESS LOGIC
│   ├── __init__.py
│   │
│   ├── 🧠 ai/                       ← AI INTEGRATION
│   │   ├── __init__.py
│   │   ├── gemma_client.py          ← [LAMA] Ollama/Gemma HTTP client
│   │   ├── prompt_templates.py      ← [LAMA] prompt engineering templates
│   │   └── cache.py                 ← [LAMA] AI response caching (TTL: 3600s)
│   │
│   ├── 🗺️  gis/                     ← GIS PROCESSING
│   │   ├── __init__.py
│   │   └── processor.py             ← [LAMA] shapely, pyproj, fiona processing
│   │
│   ├── 📝 document/                 ← DOCUMENT PROCESSING
│   │   └── __init__.py
│   │
│   ├── 📊 report/                   ← REPORT GENERATION
│   │   └── __init__.py
│   │
│   └── 🔧 utils/                    ← UTILITIES
│       ├── __init__.py
│       ├── logger.py                ← [LAMA] structlog JSON logger
│       └── logger_enhanced.py       ← [BARU] step events, SSE streaming, per-task logger
│
├── 🗄️  db/                          ← DATABASE LAYER
│   ├── __init__.py
│   ├── connection.py                ← [LAMA] asyncpg PostgreSQL connection pool
│   └── models.py                    ← [LAMA] SQLAlchemy ORM models
│
├── ⚡ worker/                        ← BACKGROUND JOBS (RQ)
│   ├── __init__.py
│   │
│   ├── ai/                          ← AI WORKER
│   │   ├── __init__.py
│   │   ├── worker_ai.py             ← [LAMA] RQ worker process AI
│   │   └── jobs_ai.py               ← [LAMA] job definitions AI queue
│   │
│   ├── gis/                         ← GIS WORKER
│   │   ├── __init__.py
│   │   ├── worker_gis.py            ← [LAMA] RQ worker process GIS
│   │   └── jobs_gis.py              ← [LAMA] job definitions GIS queue
│   │
│   └── pipeline/                    ← PIPELINE WORKER
│       ├── __init__.py
│       └── jobs_pipeline.py         ← [LAMA] WIUP full report pipeline
│
├── 📁 reports/                      ← OUTPUT FILES (AKTIF)
│   ├── laporan.pdf                  ← generated PDF (akan di-overwrite)
│   ├── laporan_20260528_102324.pdf  ← generated PDF dengan timestamp unik
│   └── output.html                  ← generated HTML dashboard
│
├── 📁 uploads/                      ← INPUT FILES USER
│   └── (file upload dari UI)
│
├── 🐳 docker/                       ← DOCKER CONFIG
│   ├── Dockerfile.api               ← [LAMA] image FastAPI
│   └── Dockerfile.worker            ← [LAMA] image RQ Worker
│
├── 📜 scripts/                      ← HELPER SCRIPTS
│   ├── init_db.sql                  ← [LAMA] inisialisasi database schema
│   └── pull_model.sh                ← [LAMA] pull Ollama model (sudah fix model name)
│
├── 🧪 tests/                        ← TESTING
│   ├── __init__.py
│   ├── integration/
│   │   ├── __init__.py
│   │   └── test_api.py              ← [LAMA] integration tests
│   └── unit/
│       ├── __init__.py
│       └── test_gis_processor.py    ← [LAMA] unit tests GIS
│
└── 🐍 venv/                         ← [BARU] Python virtual environment
    └── (dependencies installed)
```

---

## RINGKASAN PERUBAHAN

### 🆕 FILE BARU (7 file)
| File | Fungsi |
|------|--------|
| `agent/skills/__init__.py` | SkillRegistry + multi-output runner |
| `agent/skills/generate_report.py` | Skill PDF report generation |
| `agent/skills/generate_dashboard.py` | Skill HTML dashboard + convert_file |
| `agent/core_enhanced.py` | Multi-step planner + intent detector |
| `api/routes/agent_enhanced.py` | SSE streaming + multi-output API |
| `core/utils/logger_enhanced.py` | Structured step logging |
| `venv/` | Python virtual environment |

### ✏️ FILE DIUPDATE (5 file)
| File | Perubahan |
|------|-----------|
| `ai_engine_ui.html` | UI baru industrial terminal, endpoint fix, port 8001 |
| `api/main.py` | +CORS middleware, +/ui endpoint, +agent_enhanced router |
| `agent/core.py` | Filename unik timestamp, judul dari task, import datetime |
| `agent/tools/writers.py` | Fix duplikasi konten PDF |
| `.env` | GEMMA_MODEL=gemma4:e2b, OLLAMA_BASE_URL=localhost:11434 |

### 💾 FILE BACKUP (2 file)
| File | Isi |
|------|-----|
| `agent/core.py.bak` | core.py sebelum diupdate |
| `agent/tools/writers.py.bak` | writers.py sebelum diupdate |

---

## INFRASTRUKTUR AKTIF

### Docker Containers (port 8000)
| Container | Port | Status |
|-----------|------|--------|
| ai_engine_api | 8000 | ✅ Up |
| ai_engine_worker_ai | — | ✅ Up |
| ai_engine_worker_gis | — | ✅ Up |
| ai_engine_rq_dashboard | 9181 | ✅ Up |
| ai_engine_redis | 6379 | ✅ Up (healthy) |
| ai_engine_postgres | 5432 | ✅ Up (healthy) |

### Systemd Service (port 8001)
| Service | Status |
|---------|--------|
| ai-engine.service | ✅ active (running) |
| Auto-start WSL boot | ✅ enabled |
| UI | http://localhost:8001/ui |

### Ollama Models
| Model | Size | Fungsi |
|-------|------|--------|
| gemma4:e2b | 7.2 GB | ✅ DEFAULT — task sehari-hari |
| gemma4:26b | 17 GB | Laporan formal (via request) |
| gemma3:27b | 17 GB | Tersedia untuk dicoba |

---

## API ENDPOINTS AKTIF

### GET Endpoints
```
GET  /ui                              ← Web UI
GET  /health/                         ← Health check
GET  /health/ready                    ← Readiness check
GET  /reports                         ← List output files
GET  /reports/{filename}              ← Download/preview file
GET  /uploads                         ← List uploaded files
GET  /api/v1/agent/tools              ← Daftar tools tersedia
GET  /api/v1/agent/reports            ← Daftar laporan agent
GET  /api/v1/ai/health                ← AI model health
```

### POST Endpoints
```
POST /api/v1/agent/run                ← Jalankan agent (UTAMA)
POST /api/v1/ai/chat                  ← Direct AI chat
POST /api/v1/ai/analyze               ← Analisa teks
POST /api/v1/ai/geological-summary    ← Ringkasan geologi
POST /api/v1/ai/jobs/enqueue          ← Queue AI job
POST /api/v1/docs/upload-and-analyze  ← Upload + analisa dokumen
POST /api/v1/gis/kml/parse            ← Parse KML
POST /api/v1/gis/kml/to-geojson       ← Konversi KML→GeoJSON
POST /api/v1/gis/area/calculate       ← Hitung luas area
POST /api/v1/gis/wiup/analyze         ← Analisa WIUP
POST /api/v1/gis/geojson/validate     ← Validasi GeoJSON
POST /api/v1/pipeline/wiup-full-report← Full WIUP report
POST /api/v1/pipeline/async/enqueue   ← Queue pipeline job
POST /upload                          ← Upload file
```
