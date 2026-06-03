# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development (local, no Docker)
```bash
# Activate venv
source venv/bin/activate

# Run API server (dev mode, port 8001)
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# Run tests
pytest tests/unit/ -v                    # Unit tests (no services needed)
pytest tests/integration/ -v             # Integration tests (mocked)
pytest tests/unit/test_gis_processor.py  # Single test file
```

### Docker (production-like, port 8000)
```bash
docker compose up -d          # Start all services
docker compose logs -f api    # Follow API logs
docker compose restart api    # Restart after code changes
```

### Pull Ollama model (one-time setup)
```bash
./scripts/pull_model.sh
```

## Architecture

The system is a **mining & GIS intelligence engine** with three layers:

### 1. API Layer (`api/`)
FastAPI app (`api/main.py`) with routers under `api/routes/`. Only the routers wired in `main.py` are live — these are:
- `/api/v1/chat/*` — **primary feature**: ChatGPT-style streaming chat with tool-calling + file upload/download (`api/routes/chat.py`, see §7). The web UI at `/` talks to this.
- `/api/v1/agent/run` — older rule-based autonomous agent (`api/routes/agent.py`)
- `/api/v1/ai/*` — direct Gemma chat/analyze via `core/ai/gemma_client.py`
- `/api/v1/gis/*` — KML parsing, area calculation, WIUP analysis
- `/api/v1/pipeline/*` — orchestrated workflows (sync + async via RQ)
- `/api/v1/docs/*` — upload-and-analyze a document (`api/routes/docs.py`)
- `/api/dokumen/*` — formal mining-document generation (`api/routes/dokumen.py`, see §6)
- `/reports/*`, `/upload`, `/uploads` — file serving + uploads (`api/routes/files.py`)
- `/` — new ChatGPT-style UI (`web/index.html`, static assets under `/web`). `/ui` and `/v3` still serve the legacy HTML UIs.

Configuration lives in `api/config.py` (pydantic-settings, reads from `.env`).

> **Two agent paths exist.** The **chat engine** (`core/chat/`, §7) is the modern path: LLM-driven *native tool-calling* via Ollama `/api/chat`. The older **`agent/core.py`** (`AIAgent`) uses a brittle *rule-based* planner (`_smart_plan`) and is kept only for `/api/v1/agent/run`. Prefer the chat engine for new work. Both share the same `agent/tools/registry.py`.
>
> Experimental "enhanced" code that was never wired up has been archived to `backups/archived_20260602/` (was `core_enhanced.py`, `toolkit.py`, `agent_enhanced.py`, `logger_enhanced.py`, `skills/`). Don't resurrect it without reason.

### 2. Autonomous Agent (`agent/`)
`agent/core.py` — `AIAgent` class runs a deterministic plan→execute→evaluate loop (max 8 steps). The planner is **rule-based** (`_smart_plan`), not LLM-driven, to avoid hallucination. LLM (`_plan`) is a fallback only.

All agent capabilities go through `agent/tools/registry.py` (`ToolRegistry`). Tools are registered with `registry.register(name, fn, description, extensions)`. The `auto_reader()` method maps file extensions to reader tools automatically.

Tool categories:
- `agent/tools/readers.py` — read_pdf, read_txt, read_docx, read_csv, read_json, read_image
- `agent/tools/writers.py` — write_pdf, write_docx, write_html, write_txt, write_json
- `agent/tools/analyzers.py` — analyze_text (wraps Ollama), generate_code
- `agent/tools/gis_io.py` — read_geojson/read_shp, write_geojson/write_shp, convert_geo (KML↔GeoJSON↔SHP via `fiona`/`shapely`; reuses `core/gis/processor.py` for the math)
- `agent/tools/images.py` — image_convert/resize/crop/rotate/compress, images_to_pdf (Pillow). **Transform only — no image generation** (a local text LLM can't synthesize images)
- GIS area tools registered inline in `build_registry()` using `core/gis/processor.py`

**To add a new agent tool:** implement the function, call `registry.register(...)` in `agent/tools/registry.py:build_registry()`, and — if the chat engine should be able to call it — add its JSON schema to `core/chat/tool_schemas.py:TOOL_SCHEMAS` (names must match).

### 3. Core Business Logic (`core/`)
- `core/ai/gemma_client.py` — async Ollama HTTP client with retry (tenacity), streaming, SHA-256 cache key, and Redis caching via `core/ai/cache.py`
- `core/gis/processor.py` — KML parsing (lxml), polygon area/centroid/bbox (shapely + pyproj WGS-84)
- `core/utils/logger.py` — structlog JSON logger; use `get_logger(__name__)` everywhere

### 4. Background Workers (`worker/`)
RQ workers consume separate queues (names in `api/config.py`: `ai_queue`, `gis_queue`, `pipeline_queue`):
- `worker/ai/worker_ai.py` → `ai_queue`
- `worker/gis/worker_gis.py` → `gis_queue`
- `worker/pipeline/jobs_pipeline.py` → `pipeline_queue` job functions

Job functions live in `jobs_*.py` files and are enqueued via `api/routes/pipeline.py`. **Note:** `docker-compose.yml` only starts `worker_ai` and `worker_gis` — there is no dedicated `worker_pipeline` service, so pipeline jobs are processed by whatever worker is run against `pipeline_queue`.

### 5. Database (`db/`)
PostgreSQL 16 + PostGIS via SQLAlchemy async (`asyncpg`). `db/connection.py` exposes `get_session()` as a FastAPI dependency. `db/models.py` defines `AIJob`, `GISProject`, `Document`. Tables are auto-created on startup via `init_db()`. No Alembic migrations are currently in use — schema changes require manual migration or `init_db()` re-run.

### 6. Document Generation (`core/document/` + `templates/`)
Generates formal Indonesian mining documents (PDF/DOCX) served under `/api/dokumen/*`. The route handler (`api/routes/dokumen.py`) calls factory functions in `core/document/generator.py` (`generate_laporan_wilayah`, `generate_laporan_produksi`, `generate_dokumen_wiup`), which in turn render via the ReportLab-based builders in `templates/` (`laporan_wilayah.py`, `laporan_produksi.py`, `dokumen_wiup.py`). `enrich_with_ai()` in the generator adds LLM-written narrative. Commodity metadata is keyed off `templates/dokumen_wiup.py:KOMODITAS_INFO`.

**To add a new document type:** add a builder in `templates/`, a `generate_*` factory in `core/document/generator.py`, and a route in `api/routes/dokumen.py`.

### 7. Chat Engine (`core/chat/`) — the primary feature
A ChatGPT-style conversational layer that lets the user read/create/convert files by chatting with the local Gemma model.
- `core/chat/engine.py` — `ChatEngine` runs a streaming tool-calling loop against Ollama `/api/chat` (native function calling). Per turn it: auto-reads uploaded text files into context, attaches uploaded images as vision input (base64 `images`), streams assistant tokens, and when the model emits `tool_calls` it executes them via the shared `ToolRegistry`, feeds results back, and loops (`MAX_TOOL_ROUNDS`). Tools that produce a file (`result["file"]`) surface as downloadable cards. A small deterministic `_fallback` handles GIS conversions if a tiny model ignores tools. Sessions are in-memory (`chat_engine.sessions`); swap to Redis later if persistence is needed.
- `core/chat/tool_schemas.py` — `TOOL_SCHEMAS`: the curated JSON-schema list of tools exposed to the model. **Names must match registry names.** This is the file to edit when you want the chat to call a new tool.
- `api/routes/chat.py` — `/api/v1/chat/{stream,upload,download,sessions,models}`. `stream` returns Server-Sent Events; each `data:` line is one engine event (`token`/`tool_start`/`tool_result`/`file`/`error`/`done`).
- `web/` — vanilla-JS UI (no build step): `index.html`, `app.js` (parses the SSE stream, renders markdown + tool chips + file cards, handles drag-drop upload + model selector), `style.css`. Served at `/`.

Files flow: uploads → `uploads/`, generated outputs → `reports/` (downloaded via `/api/v1/chat/download/{filename}`). Path arguments from the model are resolved against `uploads/` then `reports/` by `ChatEngine.resolve_path`, which is what makes multi-step chains (e.g. resize → convert) work.

## Deployment

Two active deployment modes:
| Mode | Port | How |
|---|---|---|
| Docker Compose | 8000 | `docker compose up -d` |
| systemd (WSL) | 8001 | `ai-engine.service` auto-starts on boot |

Ollama runs on the host at `http://172.29.239.93:11434` (WSL host IP). The default model is `gemma4:e2b` (7.2 GB, fast). `gemma4:26b` is available for formal reports.

Output files go to `reports/`, uploaded files land in `uploads/`. Both are volume-mounted in Docker.

## Key Configuration (`.env`)
- `OLLAMA_BASE_URL` — point to Ollama instance (host or Azure VM)
- `GEMMA_MODEL` — active model (`gemma4:e2b` default)
- `DATABASE_URL` — asyncpg connection string
- `REDIS_URL` — broker + cache
- `AI_CACHE_TTL` / `GIS_CACHE_TTL` — Redis TTLs for AI and GIS responses
