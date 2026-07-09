# AI Engine v4 — Enterprise Multi-Agent AI Platform

[![CI](https://github.com/kiswan-source/ai_engine/actions/workflows/ci.yml/badge.svg)](https://github.com/kiswan-source/ai_engine/actions/workflows/ci.yml)

Platform AI enterprise untuk mining & GIS intelligence: dimulai sebagai asisten file berbasis LLM lokal (Gemma via Ollama), kini berkembang jadi **orkestrator multi-agent** dengan 15 peran, multi-provider (Ollama/Claude/OpenAI/Gemini) + circuit breaker, RAG, memory bertingkat, guardrail keamanan + RBAC, telemetry/observability, Project Workspace, automation, plugin, MCP (client & server), dan manifest Kubernetes.

## ✨ Fitur Utama

### 💬 Chat Asisten File
Antarmuka chat gaya ChatGPT yang berjalan sepenuhnya dengan **LLM lokal** untuk membaca & membuat/mengonversi file: PDF · DOCX · TXT · CSV · JSON · gambar (JPG/PNG/TIFF) · GIS (KML/GeoJSON/SHP).
- Buka `http://localhost:8001/` (systemd) atau `:8000/` (Docker) → langsung chat.
- Unggah file (drag-drop), lalu minta: *"ringkas PDF ini jadi DOCX"*, *"konversi KML ke Shapefile & hitung luas"*, *"resize gambar ke 800px dan ubah ke JPG"*.
- Model bekerja via **tool-calling** (Ollama `/api/chat`), respons di-**stream**, hasil muncul sebagai kartu unduh.
- Gemma bisa *membaca* gambar (OCR/deskripsi) dan *mentransformasi* (resize/crop/convert/rotate/compress), **tidak bisa meng-generate gambar baru**.

Mesin chat: `core/chat/` · API: `api/routes/chat.py` (`/api/v1/chat/*`).

### 🧠 Orchestrator Multi-Agent
15 peran agent (planner, research, analyst, writer, reviewer, memory, guardrail, prompt_optimizer, tool, vision, reflection, critic, consensus, cost_optimizer, confidence) di-routing lewat `orchestrator/` ke provider yang tepat, dengan mode reflection/voting/consensus, human-approval gate, dan DAG task planning. API: `/api/v1/orchestrator/*`.

### 🔌 Multi-Provider + Resilience
`providers/` mendukung Ollama (lokal, default), Claude, OpenAI, Gemini di belakang `BaseProvider` yang seragam, dengan **circuit breaker** (Closed→Open→Half-Open) per provider dan fallback otomatis.

### 📚 RAG & Knowledge, 🧩 Memory
`rag/` (chunk → embed → store → retrieve → hybrid → rerank → context) di-expose lewat `/api/v1/knowledge/*` (ingest teks, cari). `memory/` 6 tier (working/conversation/summary/long_term/reflection/vector) di-expose lewat `/api/v1/memory/*`. **Gap yang diketahui:** Knowledge baru menerima teks tempel (belum upload file/OCR); Memory belum terhubung ke Chat Engine sehari-hari sehingga halamannya kosong sampai integrasi tersebut dibangun — lihat `docs/PROGRESS.md`.

### 🔐 Security & Observability
`security/` — prompt-injection guard, deteksi & redaksi PII, output validator (sinyal confidence scoring), audit log append-only, RBAC (`auth.py`/`permissions.py`). `telemetry/` — tracing, metrics, cost tracking, 8 dashboard monitoring (`/api/v1/monitoring/*`).

### 📁 Project Workspace, ⏱️ Automation, 🧰 Plugin, 🔗 MCP
- **Projects** (`/api/v1/projects/*`) — wadah kerja dengan membership & RBAC per-resource.
- **Workspace** (`/api/v1/workspace/*`, `workspace/`) — index & akses folder lokal (dokumen/gambar/GIS) untuk agent, terintegrasi RAG search.
- **Automation** (`/api/v1/automation/*`, `scheduler/`) — trigger terjadwal.
- **Plugin** (`plugins/`) — kategori tool tambahan lewat tool-calling (contoh: `weather`).
- **MCP** — `mcp_client/` (memanggil tool dari server MCP eksternal) & `mcp_server/` (mengekspos Workspace sebagai server MCP untuk Claude Desktop dkk, stdio-only).

### 🗺️ GIS & 📄 Dokumen Tambang
`core/gis/` (KML parsing, luas/centroid WGS-84 via shapely+pyproj) via `/api/v1/gis/*`. `core/document/` + `templates/` (ReportLab) generate laporan tambang formal (PDF/DOCX) via `/api/dokumen/*`.

### ☸️ Kubernetes-ready
`k8s/` (Kustomize base + overlay production) — Postgres pgvector (StatefulSet), Redis, API (2 replika), worker terpisah per queue. Diverifikasi live di `kind` lokal (lihat `docs/PROGRESS.md`).

## Frontend

`web/` — React 19 + TypeScript + Vite + TailwindCSS v4 + shadcn/ui + Zustand + React Router. 11 halaman: Chat, Workflow (Orchestrator), Approval, History, Settings, Files, Projects, Workspace, Monitoring, Memory, Knowledge. API di-build ke `web/dist` dan disajikan langsung oleh FastAPI (`api/main.py`) dengan SPA fallback.

```bash
cd web
npm install
npm run dev      # dev server dengan HMR
npm run build    # build produksi → web/dist (disajikan oleh FastAPI)
```

## Stack
| Layer | Technology |
|---|---|
| API | FastAPI 0.115 + Uvicorn |
| LLM | Ollama (`gemma4:e2b` default · `gemma4:26b` formal) + Claude/OpenAI/Gemini opsional |
| Database | PostgreSQL 16 + PostGIS 3.4 + pgvector |
| Cache/Broker | Redis 7 |
| Queue | RQ (Redis Queue) + Dashboard |
| Frontend | React 19 + TypeScript + Vite + TailwindCSS v4 + shadcn/ui |
| Container | Docker Compose · Kubernetes (Kustomize) |

## Quick Start

```bash
# 1. Clone / extract
cd ai_engine

# 2. Setup env
cp .env.example .env
# Edit .env sesuai kebutuhan

# 3. Start semua services
docker compose up -d

# 4. Pull model Ollama (SEKALI saja, ~15GB)
chmod +x scripts/pull_model.sh
./scripts/pull_model.sh

# 5. Check health
curl http://localhost:8000/health/ready
```

### Development lokal (tanpa Docker)
```bash
source venv/bin/activate
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

## API Endpoints

| Prefix | Area |
|---|---|
| `/api/v1/chat/*` | Chat asisten file (upload, stream SSE, download, sessions, models) |
| `/api/v1/orchestrator/*` | Multi-agent orchestrator (roles, modes, run, approvals) |
| `/api/v1/ai/*` | Chat/analyze langsung ke Gemma |
| `/api/v1/gis/*` | Parse KML, konversi, hitung luas, analisis WIUP |
| `/api/v1/pipeline/*` | Workflow terorkestrasi (sync + async via RQ) |
| `/api/v1/docs/*` | Upload-and-analyze dokumen |
| `/api/dokumen/*` | Generate dokumen tambang formal (PDF/DOCX) |
| `/api/v1/monitoring/*` | 8 dashboard observability |
| `/api/v1/memory/*` | Memory 6 tier (per sesi) |
| `/api/v1/knowledge/*` | RAG ingest + search |
| `/api/v1/projects/*` | Project & membership |
| `/api/v1/automation/*` | Trigger terjadwal |
| `/api/v1/plugins/*` | Kategori plugin tool |
| `/api/v1/workspace/*` | Index & akses folder lokal |
| `/reports`, `/uploads`, `/upload` | File serving |
| `/health/*` | Liveness/readiness (dicek CI & Docker healthcheck) |

Detail request/response tiap endpoint: Swagger UI / ReDoc (lihat di bawah).

## Interactive Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- RQ Dashboard: http://localhost:9181

## Testing

```bash
source venv/bin/activate
pytest                        # Full suite — 619 test (unit + integration, semua mocked, tanpa service live)
pytest tests/unit/ -v          # Unit tests
pytest tests/integration/ -v   # Integration tests (mocked)
pytest --cov --cov-report=term-missing   # Dengan coverage (sama seperti CI)
```

CI (`.github/workflows/ci.yml`) menjalankan `pytest --cov` di Python 3.12 untuk setiap push/PR ke `main`, hanya dengan `requirements.txt` — tanpa Postgres/Redis/Ollama live.

## Struktur Folder

```
ai_engine/
├── api/            FastAPI app + routes (chat, orchestrator, gis, dokumen, monitoring, memory, knowledge, projects, automation, plugins, workspace, …)
├── core/           Business logic — ai/, chat/ (mesin chat), gis/, document/
├── agent/          Tool registry + tools (readers, writers, gis_io, images) — rule-based agent lama
├── agents/         15 peran GenericLLMAgent untuk Orchestrator
├── orchestrator/   Planner, routing, dispatcher+fallback, DAG, reflection/consensus/confidence
├── providers/      BaseProvider seragam untuk Ollama/Claude/OpenAI/Gemini + circuit breaker
├── registry/       Provider registry, model registry, agent registry
├── rag/            Chunk → embed → store → retrieve → hybrid → rerank → context
├── memory/         6 tier memory (working/conversation/summary/long_term/reflection/vector)
├── messaging/      Message bus, event bus, task queue (broker InMemory|Redis)
├── security/       Prompt guard, PII redaction, output validator, audit log, RBAC
├── telemetry/      Tracing, metrics, cost tracking, monitoring dashboards
├── workflows/       Sequential/parallel/reflection/voting/consensus/approval workflow
├── workspace/       Index & scanner folder lokal untuk agent
├── mcp_client/       Klien MCP (memanggil tool server eksternal)
├── mcp_server/       Server MCP (mengekspos Workspace)
├── plugins/          Kategori plugin tool tambahan
├── scheduler/        Automation/trigger terjadwal
├── web/            Frontend React 19 + TS + Vite + Tailwind + shadcn/ui
├── templates/      Builder dokumen tambang formal (ReportLab)
├── worker/         RQ background workers (ai_queue, gis_queue, pipeline_queue)
├── db/             SQLAlchemy async models
├── k8s/            Manifest Kubernetes (Kustomize base + overlay production)
├── tests/          Unit + integration tests (619 test)
├── scripts/        DB init, model pull
├── config/         Configuration Center (versioned config/*.yaml)
├── prompts/        Prompt Management (versioned prompts/ folder)
└── backups/        Kode lama yang diarsipkan
```

## Deployment

| Mode | Port | How |
|---|---|---|
| Docker Compose | 8000 | `docker compose up -d` |
| systemd (WSL) | 8001 | `ai-engine.service` auto-start on boot |
| Kubernetes | — | `kubectl apply -k k8s/base` (+ overlay `production`) |

Ollama default berjalan di host (`OLLAMA_BASE_URL`). Model default `gemma4:e2b` (7.2 GB, cepat); `gemma4:26b` untuk laporan formal.

## Key Configuration (`.env` + `config/*.yaml`)
Sebagian besar default field `Settings` kini ada di `config/*.yaml` (Configuration Center — versioned, bertema). Sisanya tetap env-only: `.env`
- `OLLAMA_BASE_URL`, `GEMMA_MODEL` — LLM lokal
- `ANTHROPIC_API_KEY` / OpenAI / Gemini keys — provider cloud opsional (fallback + role tertentu)
- `DATABASE_URL` — koneksi asyncpg
- `REDIS_URL` — broker + cache
- `API_KEYS` — otentikasi RBAC

## Status & Gap yang Diketahui

Progres detail per tahap ada di `docs/PROGRESS.md`. Gap yang sengaja belum ditutup (bukan bug, keputusan sadar menunggu kebutuhan konkret):
- Memory page kosong sampai Chat Engine terintegrasi ke `memory/`.
- Knowledge baru ingest teks tempel (belum upload file/OCR, belum embedder produksi).
- Vision belum diverifikasi live ke provider cloud dengan gambar nyata (baru bentuk payload yang teruji).
- Workspace: sumber folder cloud (GDrive/OneDrive/SharePoint/S3) belum ada; belum ada cache count persisten.
- MCP Server: satu proses = satu Workspace + satu role tetap, transport stdio-only.
