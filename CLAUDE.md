# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development (local, no Docker)
```bash
# Activate venv
source venv/bin/activate

# Run API server (dev mode, port 8001)
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload

# Run tests (pytest.ini sets asyncio_mode=auto + testpaths=tests, so bare `pytest` works from root)
pytest                                   # Full suite (async tests auto-detected)
pytest tests/unit/ -v                    # Unit tests (no services needed)
pytest tests/integration/ -v             # Integration tests (mocked)
pytest tests/unit/test_gis_processor.py  # Single test file
pytest --cov --cov-report=term-missing   # With coverage (matches CI)
```

> CI (`.github/workflows/ci.yml`) runs `pytest --cov` on Python 3.12 for every push/PR to `main`. It installs only `requirements.txt` and does **not** stand up Postgres/Redis/Ollama, so tests must pass without live services (unit + mocked integration only).

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

The system is a **multi-agent AI platform**, first applied to mining & GIS intelligence but not hard-wired to that domain at the architecture level (see `docs/PROGRESS.md` and the v5 evolution blueprint for the domain-generalization plan). This section was rewritten 2026-07-16 after an audit found it had drifted — it previously described only 9 of 17 live routers and omitted entire subsystems (`orchestrator/`, `agents/`, `memory/`, `rag/`, `workspace/`, `telemetry/`, `messaging/`, `mcp_client/`/`mcp_server/`, `plugins/`, `scheduler/`) that are real, tested, and load-bearing. **Verify against actual code before trusting any doc, including this one** — that same audit also found and corrected a stale docstring in `security/auth.py` making an incorrect claim about its own file.

### 1. API Layer (`api/`)
FastAPI app (`api/main.py`) with routers under `api/routes/`. All 17 are live (check `api/main.py`'s `include_router` calls, not this table, if the two ever disagree):

| Prefix | Router file | Auth |
|---|---|---|
| `/health/*` | `health.py` | none |
| `/api/v1/ai/*` | `ai.py` | router-level |
| `/api/v1/gis/*` | `gis.py` | router-level |
| `/api/v1/pipeline/*` | `pipeline.py` | router-level |
| `/api/v1/docs/*` | `docs.py` | router-level |
| `/api/dokumen/*` | `dokumen.py` | router-level |
| `/api/v1/agent/*` | `agent.py` | per-route |
| `/reports`, `/upload`, `/uploads` | `files.py` | per-route |
| `/api/v1/chat/*` | `chat.py` | per-route |
| `/api/v1/orchestrator/*` | `orchestrator.py` | per-route |
| `/api/v1/monitoring/*` | `monitoring.py` | `require_role` |
| `/api/v1/memory/*` | `memory.py` | per-route |
| `/api/v1/knowledge/*` | `knowledge.py` | per-route |
| `/api/v1/projects/*` | `projects.py` | per-route |
| `/api/v1/automation/*` | `automation.py` | per-route |
| `/api/v1/plugins/*` | `plugins.py` | per-route |
| `/api/v1/workspace/*` | `workspace.py` | per-route |
| `/` | `web/dist` static bundle | n/a |

"router-level" = `dependencies=[Depends(get_current_principal)]` on the `app.include_router(...)` call itself, so a future endpoint added under that prefix can't ship unauthenticated by omission (added Fase 1, after these 5 routers were found to have no auth dependency at all). Everywhere else, auth is opt-in per-route inside the router file — grep for `Depends(get_current_principal)` before assuming a route is protected. `API_KEYS` being blank (current dev default) makes every checked route treat the caller as admin; this deployment relies on loopback-only network binding (`docker-compose.yml`, `ai-engine.service`) as its actual isolation, not API keys — a documented trade-off, not an oversight.

Configuration lives in `api/config.py` (pydantic-settings); most defaults have moved to `config/*.yaml` (Configuration Center, versioned), with `.env` for secrets and per-deployment overrides.

> **Three agent execution paths exist side by side — know which one you're touching:**
> - `core/chat/` (§9) — **primary user-facing feature**. LLM-driven native tool-calling via Ollama `/api/chat`, backs the `/` web UI.
> - `orchestrator/` + `agents/` + `registry/` (§2) — **15-role multi-agent system**, backs `/api/v1/orchestrator/*` and the Workflow UI page.
> - `agent/` singular (§3) — **older rule-based planner**, kept only for `/api/v1/agent/run`. Don't extend it without a specific reason to.
>
> All three call into the same `agent/tools/registry.py` (`ToolRegistry`) for actual tool execution. **Fase 6 (Cowork Experience) bridges the first two**: the chat tool `run_orchestrated_workflow` (`agent/tools/orchestrator_tools.py`) lets a Chat Engine turn trigger a real Orchestrator run — see §9's Fase 6 note. The rule-based `agent/` path (§3) is not bridged.
>
> Experimental "enhanced" code that was never wired up is archived at `backups/archived_20260602/` (`core_enhanced.py`, `toolkit.py`, `agent_enhanced.py`, `logger_enhanced.py`, `skills/`). Don't resurrect it without reason.

### 2. Orchestrator & Multi-Agent System (`orchestrator/`, `agents/`, `registry/`, `workflows/`)
- `orchestrator/planner.py` + `execution_graph.py` — builds a DAG-based plan from a goal; does not execute it.
- `orchestrator/dispatcher.py` + `task_manager.py` — executes the DAG. State machine has real transitions beyond the happy path: `PENDING→PLANNING→RESEARCH→EXECUTING→REVIEWING→APPROVED→COMPLETED`, plus `CANCELLED`/`FAILED`/`RETRY`/`ROLLBACK` (including a retry loop back to `PENDING`); illegal transitions raise `IllegalTransitionError` rather than silently corrupting state.
- `orchestrator/routing_engine.py` — picks provider/model per step.
- `agents/generic_agent.py` — **all 15 roles (planner/research/analyst/writer/reviewer/memory/guardrail/prompt_optimizer/tool/vision/reflection/critic/consensus/cost_optimizer/confidence) are still one class, `GenericLLMAgent`, configured with a different prompt per instance** — Fase 2 deliberately did not split this into subclasses (regression risk against 685+ tests for a benefit the guard below already delivers). `agents/capabilities.py` classifies each role into `AgentCapability.{SPECIALIST,EXECUTOR,VALIDATOR}` (every `BaseAgent` subclass gets `.capability` for free, derived from `.role` — no override needed) and `agents/validation_guard.py::assert_independent_validator` enforces "builder ≠ validator" wherever a `Task.metadata["validates_agent_ids"]` marks it as judging another agent's output — checked in `orchestrator/dispatcher.py::dispatch()`, the shared chokepoint. **Scope of what's actually closed**: only `orchestrator/consensus.py::ConsensusEngine.arbitrate()` sets that metadata today (confirmed by grep — the only real code path that dispatches an agent to judge another's output), so the guard currently protects consensus arbitration only. `orchestrator/reflection.py`'s self-evaluate/revise loop is untouched by design — it re-dispatches the *same* role, scored algorithmically (`ConfidenceScorer`), not judged by another agent, and already escalates to Human Approval on low confidence; that's a separate, larger design question, not bundled into this pass. Don't assume every "reviewer"/"critic" task is independence-checked — only ones that explicitly set `validates_agent_ids`.
- `registry/agent_registry.py` — the 15-role registry (Agent Manager equivalent). `registry/` also holds the provider registry and plugin registry.
- `workflows/` — five orchestration patterns: `sequential.py`, `parallel.py`, `reflection.py` (self-critique), `voting.py`, `consensus.py`, `approval.py`. `HumanApprovalGate` in `approval.py` never auto-decides and audit-logs every decision with approver identity + reason, but by design has no notion of *who* the caller is — RBAC-gating who may call `decide()` is the caller's job (`Orchestrator.finalize_approval`), not enforced inside the gate itself.
- `orchestrator/orchestrator.py::get_shared_orchestrator()` — process-wide `Orchestrator` singleton (Fase 6). `api/routes/orchestrator.py` (Workflow/Approval UI pages) **and** `agent/tools/orchestrator_tools.py` (the chat bridge, §9) both use this ONE instance — otherwise a Human Approval request opened by a chat-triggered run would live in a `TaskManager`/`HumanApprovalGate` the Approval page's own instance never sees, for the in-memory (dev/CI default) state backends. Lives here, not in `api/routes/`, specifically so `agent/tools/` never has to import from `api/` (the dependency direction it avoids everywhere else — see `agent/tools/workspace_reader.py`).

### 3. Legacy Rule-Based Agent (`agent/`)
`agent/core.py` — `AIAgent` runs a deterministic plan→execute→evaluate loop (max 8 steps). The planner is **rule-based** (`_smart_plan`), not LLM-driven, to avoid hallucination; LLM planning (`_plan`) is a fallback only. As of Fase 1, input runs through `security.prompt_guard` (can block outright, unlike the streaming chat path) and PII redaction, and output is validated/redacted before returning — added alongside the equivalent wiring in `core/chat/engine.py` (§9); see §8 for how these differ between the two paths.

All agent capabilities (from all three paths in §1) go through `agent/tools/registry.py` (`ToolRegistry`). Tools are registered with `registry.register(name, fn, description, extensions)`. The `auto_reader()` method maps file extensions to reader tools automatically.

Tool categories:
- `agent/tools/readers.py` — read_pdf, read_txt, read_docx, read_csv, read_json, read_image
- `agent/tools/writers.py` — write_pdf, write_docx, write_html, write_txt, write_json
- `agent/tools/analyzers.py` — analyze_text (wraps Ollama), generate_code
- `agent/tools/gis_io.py` — read_geojson/read_shp, write_geojson/write_shp, convert_geo (KML↔GeoJSON↔SHP via `fiona`/`shapely`; reuses `core/gis/processor.py` for the math)
- `agent/tools/images.py` — image_convert/resize/crop/rotate/compress, images_to_pdf (Pillow). **Transform only — no image generation** (a local text LLM can't synthesize images)
- `agent/tools/workspace_reader.py` — reads from `workspace/`-registered folders (§7)
- `agent/tools/memory_tools.py` — `remember_fact`/`recall_facts`, cross-session memory namespaced by owner (Fase 3, §5)
- GIS area tools registered inline in `build_registry()` using `core/gis/processor.py`

**To add a new agent tool:** implement the function, call `registry.register(...)` in `agent/tools/registry.py:build_registry()`, and — if the chat engine should be able to call it — add its JSON schema to `core/chat/tool_schemas.py:TOOL_SCHEMAS` (names must match). **If the tool is risky** (writes, deletes, external calls), add it to `security/permissions.py`'s `TOOL_RISK_ACTIONS` (§8) — one line per tool, the established pattern for every risky tool added so far.

### 4. Providers (`providers/`)
`BaseProvider` — uniform interface over Ollama (local, default), Claude, OpenAI, Gemini. Each exposes a `base_url` property, used by `security/endpoint_policy.py` (§8) to classify internal vs. external for PII redaction — **classify by the provider's actual configured endpoint, not by name**; `OLLAMA_BASE_URL` is not automatically internal (it points at a WSL virtual-network IP in Docker Compose, or an arbitrary k8s hostname) so "provider is ollama" was a real bug fixed in Fase 1, not a hypothetical. Circuit breaker (Closed→Open→Half-Open) per provider with automatic fallback.

### 5. Memory System (`memory/`)
6 tiers coordinated by `memory_manager.py`: `working_memory.py`, `conversation_memory.py`, `summary_memory.py`, `long_term_memory.py`, `reflection_memory.py`, `vector_memory.py` (pgvector-backed). Exposed via `/api/v1/memory/*`.

**Fase 3 (DCF v5 mandate) wired this up — session-scoped tiers are automatic, cross-session is explicit-opt-in only, never automatic promotion:**
- `memory.memory_manager.get_shared_memory_manager()` is the process-wide singleton — `core/chat/engine.py`, `api/routes/memory.py`, and anything else touching memory MUST use this, not a private `build_memory_manager()` call, or the in-memory (dev/CI) backends end up as disconnected islands that never see each other's writes.
- Every `ChatEngine.stream_run()` turn writes `working` (last files/timestamp) and `conversation` (user + assistant messages) per `session_id`; `summary` refreshes every `MEMORY_SUMMARY_EVERY_N_TURNS` (5) turns. All three are inherently session-scoped — no cross-session/cross-user risk here, and a memory-tier failure only logs a warning, never breaks the chat turn (see `ChatEngine._remember_turn_start`/`_remember_turn_end`).
- Cross-session memory ("mengingat lintas sesi") is two new tools, `remember_fact`/`recall_facts` (`agent/tools/memory_tools.py`), namespaced by **`owner`** (the caller's identity) — deliberately NOT `workspace_id`, since Project Workspaces have multi-user membership and namespacing by workspace would leak one member's remembered facts to every other member. The model calls these only when the user explicitly asks to be remembered — this is intentional, not automatic per-turn promotion (the "promosi memori eksplisit" principle the v5 roadmap required before any cross-session integration). `owner` is injected by `ChatEngine._run_tool` from the session's authenticated caller, same rule already established for `workspace_id` — never trust a model-supplied value for either.
- `vector`/`reflection` tiers are untouched by this pass — `vector` is RAG's concern (§6), `reflection` is the orchestrator's self-improvement mechanism (§2), neither is part of Chat Engine's memory integration.
- **Known limitation**: `remember_fact`/`recall_facts` build a fresh Postgres engine per call when `MEMORY_PERSISTENT_BACKEND=postgres` (same asyncpg-event-loop-affinity constraint `agent/tools/workspace_reader.py` already has) — exercised by hand against a real database, not covered by the unit tests (which only run the in-memory default).

### 6. RAG & Knowledge (`rag/`)
Chunk → embed → store → retrieve → hybrid → rerank → context, exposed via `/api/v1/knowledge/*`. Ingest today is **paste-text only** — no file upload or OCR yet — and the embedder is `hashed_bow_embedder` (offline hash-based, not a production embedding model).

### 7. Workspace (`workspace/`)
Index & scan local folders for agent/RAG use, exposed via `/api/v1/workspace/*`; reading is also available via `agent/tools/workspace_reader.py`.

**Fase 4 (DCF v5 mandate, "Workspace Autonomous Capability") added controlled writes with automatic versioning:**
- `agent/tools/workspace_reader.py::workspace_write_file` (the chat tool) creates/overwrites/appends text files (txt/md/log/csv/json/html) and real PDF/DOCX (mode="overwrite" only for those two). Root Restriction (writing outside the registered folder) is structurally rejected via `tools/tool_validator.resolve_within_root`/`PathEscapesRootError` — this was already true before Fase 4, not new.
- **What Fase 4 actually added**: before any overwrite of a file that already exists, `_write_file` snapshots its current bytes to a new `WorkspaceFileVersion` row (`workspace/versioning.py`) — closes the "silent, unrecoverable overwrite" gap that existed since Tahap 30. The tool result's `action` field is `"created"` / `"overwritten"` / `"appended"` (not a generic echo of `mode`) so the model/user can tell which happened. Every write is also recorded to `security.audit_log` (`workspace.file_written`).
- **Restoring a version is deliberately an HTTP endpoint, not a chat tool** — `GET /api/v1/workspace/{id}/files/{folder_id}/versions` (read, same `_require_member` access as any Workspace content) and `POST .../restore` (mutation, gated on `write_output` same as the write tool). Recovery is a human action via the Workspace UI, not something the model decides mid-conversation. Restoring is itself an overwrite, so it snapshots the current content first too — recoverable recursively, not just the original write.
- **Known, accepted limitation**: this is automatic-snapshot-then-write, not a live pause-and-confirm approval before the overwrite happens. A full in-chat approval flow (new SSE event type, pending-write state, frontend diff UI) was considered and explicitly deferred — Owner chose the smaller slice for this pass. Don't assume a Human Approval gate exists in the chat write path; it doesn't yet.
- Delete/rename capability still doesn't exist at all (safe — nothing to fix — and out of scope per the mandate's own WRITE wording, which only asked for create/update).

### 8. Security (`security/`)
- `auth.py` — `get_current_principal`, API-key principal lookup (`API_KEYS`: comma-separated `key` or `key:role`).
- `permissions.py` — static role→permission RBAC matrix + `TOOL_RISK_ACTIONS` (per-tool risk classification; extend this — one line — when adding a risky tool, see §3).
- `endpoint_policy.py` — `is_internal_endpoint(url)`: loopback / RFC1918 / `.local` / `.internal` / `.svc.cluster.local` = internal, everything else (including blank) = external, fail-closed.
- `prompt_guard.py` / `output_validator.py` / `pii_detector.py` — wired into all three agent paths from §1 as of Fase 1. Behavior differs by path because of streaming: `agents/generic_agent.py` and `agent/core.py` (§3) can block outright on suspicious input and redact PII from output before it's ever returned, since nothing has reached the caller yet. `core/chat/engine.py` (§9) neutralizes-and-continues on input instead of blocking — a live conversation must not go silent on a false positive — and can only detect-and-flag the output after the fact (SSE has already streamed every token by the time the full response is checked), surfaced as a `warning` SSE event, not silently swallowed.
- `audit_log.py` — append-only, hash-chained (`prev_hash`/`entry_hash`, SHA-256, survives rotation via a synthetic marker entry) with size-based rotation (`AUDIT_LOG_MAX_BYTES`/`AUDIT_LOG_BACKUP_COUNT`). Verify integrity independently with `python3 scripts/verify_audit_log.py` — don't trust the log's own contents as proof of its own integrity.
- `startup_validation.py` — `enforce_production_config()`, called from `api/main.py`'s `lifespan`; refuses to start with blank/example/weak credentials when `APP_ENV=production` (no-op otherwise — this deployment currently runs `APP_ENV=development` with loopback-only network binding as the actual isolation mechanism, a deliberate choice, not a gap).
- **Not verified to exist**: a dedicated sandbox for tool-calling/code execution. File-operation risk matrix is partially closed as of Fase 4 — overwrite of an existing Workspace file is versioned + audit-logged (§7), but there's still no live approval pause before it happens (accepted limitation, not an oversight), and delete/rename capability doesn't exist at all (nothing to fix there). Don't enable free-form code execution without checking/building a sandbox first.

### 9. Chat Engine (`core/chat/`) — the primary feature
A ChatGPT-style conversational layer that lets the user read/create/convert files by chatting with the local Gemma model.
- `core/chat/engine.py` — `ChatEngine` runs a streaming tool-calling loop against Ollama `/api/chat` (native function calling). Per turn it: runs `security.prompt_guard`/PII redaction on the input (§8), auto-reads uploaded text files into context, attaches uploaded images as vision input (base64 `images`), streams assistant tokens, and when the model emits `tool_calls` executes them via the shared `ToolRegistry`, feeds results back, and loops (`MAX_TOOL_ROUNDS`). Tools that produce a file (`result["file"]`) surface as downloadable cards. Runs `security.output_validator` on the full accumulated response just before the terminal event (§8). A small deterministic `_fallback` handles GIS conversions if a tiny model ignores tools. Sessions are in-memory (`chat_engine.sessions`, plain dict — no `TaskStore`/`RedisTaskStore`-style abstraction like `task_manager.py` has); swap to Redis later if persistence or horizontal scaling is needed.
- `core/chat/tool_schemas.py` — `TOOL_SCHEMAS`: the curated JSON-schema list of tools exposed to the model. **Names must match registry names.** This is the file to edit when you want the chat to call a new tool.
- `api/routes/chat.py` — `/api/v1/chat/{stream,upload,download,sessions,models}`. `stream` returns Server-Sent Events; each `data:` line is one engine event (`token`/`tool_start`/`tool_result`/`file`/`warning`/`error`/`done`).
- `web/src/pages/chat/` — React chat page (part of the full `web/src/` SPA, §12), parses the SSE stream, renders markdown + tool chips + file cards + warning toasts, handles drag-drop upload + model selector.

Files flow: uploads → `uploads/`, generated outputs → `reports/` (downloaded via `/api/v1/chat/download/{filename}`). Path arguments from the model are resolved against `uploads/` then `reports/` by `ChatEngine.resolve_path`, which is what makes multi-step chains (e.g. resize → convert) work.

**Fase 6 (DCF v5 mandate, "Cowork Experience") — chat can trigger a real Orchestrator run.** The mandate's example ("Analisa dokumen ini dan buat laporan" → plan → pick agent(s) → workflow → validate → escalate-if-needed → output) was, before this Fase, only true on the `/api/v1/orchestrator/*` Workflow page — `ChatPage.tsx` had zero awareness of the orchestrator (verified by grep, not assumed). Closed via a new tool, **not** a new SSE protocol:
- `run_orchestrated_workflow(goal, roles, mode)` (`agent/tools/orchestrator_tools.py`) — the model calls this itself (existing tool-calling loop) when it judges a request needs real multi-agent planning rather than one tool call. Runs the real `Orchestrator.run()` via `get_shared_orchestrator()` (§2), returns a structured summary (`final_output`, per-step results, `escalate`, `trace_id`, `state`).
- `ChatEngine._summarize_result()` has a duck-typed branch for this tool's result shape (`"final_output" in result and "escalate" in result`): if `escalate` is true, the summary is the human-readable "needs approval" message, **never** the partial/unvalidated output — the existing `tool_result` SSE event/card renders it exactly like any other tool, no frontend changes needed.
- **If the run escalates**, the chat turn does NOT wait inline — it tells the user to use the **existing** Approval page (`ApprovalPage.tsx`, `/api/v1/orchestrator/approvals/*`) to decide, which works because both paths share `get_shared_orchestrator()`. A live pause-and-confirm inside a chat turn was considered and explicitly rejected (Fase 6 design decision — see `agent/tools/orchestrator_tools.py`'s docstring) in favor of reusing infrastructure that already existed and already worked.
- **Verified live** (not just unit-tested): a real chat message against `gemma4:e2b` correctly called this tool on the first attempt with sensible `roles`/`mode`, and the underlying `research`→`analyst`→`writer` sequential workflow produced a real, substantive report — see the Fase 6 session's verification notes if reproducing.
- **Known limitation**: only `core/chat/` is bridged this way — `agent/core.py` (§3, the older rule-based path) is not, and wasn't asked for.

### 10. Telemetry (`telemetry/`) & Messaging (`messaging/`)
`telemetry/` — tracing, metrics, cost tracking; 8 dashboards via `/api/v1/monitoring/*`. Read-only observability by design — must not influence execution decisions. `messaging/` — message bus / event bus / task queue abstraction (`InMemory` or Redis broker); `security/audit_log.record()` also publishes a `security.<event_type>` event here, which `telemetry.tracing.Tracer` folds into a request's Execution Timeline.

### 11. MCP (`mcp_client/`, `mcp_server/`), Plugins (`plugins/`) & Automation (`scheduler/`)
`mcp_client/` calls tools on external MCP servers. `mcp_server/` exposes this repo's Workspace as an MCP server (stdio-only) for external clients like Claude Desktop — one process serves one Workspace + one fixed role today. `plugins/` + `registry/plugin_registry.py` — additional tool categories via the same tool-calling path (one real example so far: `weather`); state is in-memory, not persisted. `scheduler/` — scheduled triggers, exposed via `/api/v1/automation/*`.

### 12. Core Business Logic (`core/`)
- `core/ai/gemma_client.py` — async Ollama HTTP client with retry (tenacity), streaming, SHA-256 cache key, and Redis caching via `core/ai/cache.py`
- `core/gis/processor.py` — KML parsing (lxml), polygon area/centroid/bbox (shapely + pyproj WGS-84)
- `core/utils/logger.py` — structlog JSON logger; use `get_logger(__name__)` everywhere

### 13. Background Workers (`worker/`)
RQ workers consume separate queues (names in `api/config.py`: `ai_queue`, `gis_queue`, `pipeline_queue`):
- `worker/ai/worker_ai.py` → `ai_queue`
- `worker/gis/worker_gis.py` → `gis_queue`
- `worker/pipeline/jobs_pipeline.py` → `pipeline_queue` job functions

Job functions live in `jobs_*.py` files and are enqueued via `api/routes/pipeline.py`. **Note:** `docker-compose.yml` only starts `worker_ai` and `worker_gis` — there is no dedicated `worker_pipeline` service, so pipeline jobs are processed by whatever worker is run against `pipeline_queue`.

### 14. Database (`db/`)
PostgreSQL 16 + PostGIS via SQLAlchemy async (`asyncpg`). `db/connection.py` exposes `get_session()` as a FastAPI dependency. `db/models.py` defines `AIJob`, `GISProject`, `Document`, `Project`, `ScheduledJob`, and others. `Project`/`ScheduledJob` carry a nullable, indexed `tenant_id` (v5 forward-compatibility groundwork — unused by any current code path, always `NULL` today, not a live multi-tenant feature). Tables are auto-created on startup via `init_db()`. No Alembic migrations are currently in use — schema changes require manual migration or `init_db()` re-run.

### 15. Document Generation (`core/document/` + `templates/`)
Generates formal Indonesian mining documents (PDF/DOCX) served under `/api/dokumen/*`. The route handler (`api/routes/dokumen.py`) calls factory functions in `core/document/generator.py` (`generate_laporan_wilayah`, `generate_laporan_produksi`, `generate_dokumen_wiup`), which in turn render via the ReportLab-based builders in `templates/` (`laporan_wilayah.py`, `laporan_produksi.py`, `dokumen_wiup.py`). `enrich_with_ai()` in the generator adds LLM-written narrative. Commodity metadata is keyed off `templates/dokumen_wiup.py:KOMODITAS_INFO`.

**To add a new document type:** add a builder in `templates/`, a `generate_*` factory in `core/document/generator.py`, and a route in `api/routes/dokumen.py`.

### 16. Domain Skills (Fase 5, DCF v5 mandate "Domain Generalization")
Mining/GIS is the platform's **first domain skill**, not a core-engine assumption — verified structurally, not just documented. `orchestrator/`, `agents/`, `workflows/`, `core/chat/` have zero mining/GIS references (confirmed by grep before this Fase, not assumed). The actual coupling points, now gated as one unit behind `settings.ENABLE_MINING_GIS_SKILL` (default `True` — no behavior change for this deployment):
- `api/main.py` — `gis.router`/`dokumen_router.router`/`pipeline.router` only registered when the flag is on. (`pipeline.py`'s only sync route, `wiup-full-report`, is 100% mining content — the "Pipeline" API isn't a generic workflow mechanism today, it's mining-only.)
- `agent/tools/registry.py` — split into `build_core_registry()` (domain-agnostic: readers/writers/images/analyzer/code-gen/plugins/mcp/workspace/memory tools) and `register_mining_gis_tools()` (`read_kml`/`read_geojson`/`read_shp`/`calculate_area`/`write_geojson`/`write_shp`/`convert_geo`). `build_registry()` (the function every caller — `core/chat/engine.py`, `agent/core.py`, `mcp_server/server.py` — already used) composes the two based on the flag; no caller had to change.

**Verified, not claimed**: `tests/unit/test_domain_skill_toggle.py` builds the registry and (via `importlib.reload`) the FastAPI app with the flag off and asserts every mining/GIS tool/route is absent while chat/orchestrator/memory/workspace/projects/automation/plugins/knowledge/monitoring/agent/docs stay present. Fixing this test surfaced a real bug: `build_core_registry()` used to mutate a shared module-level `ToolRegistry` singleton, so a tool registered once never disappeared on a later call with the flag off — fixed by constructing a fresh registry per call (same pattern `registry/agent_registry.py::build_default_agent_registry()` already used).

**To add a second real domain skill**: follow the same shape — a dedicated `ENABLE_<DOMAIN>_SKILL` flag, a `register_<domain>_tools()` function, and conditional router registration in `api/main.py`. Don't invent one speculatively; this pass deliberately didn't fabricate a second domain just to prove the pattern generalizes — the toggle test already proves that without one.

## Deployment

Three active deployment modes:
| Mode | Port | How |
|---|---|---|
| Docker Compose | 8000 | `docker compose up -d` |
| systemd (WSL) | 8001 | `ai-engine.service` auto-starts on boot |
| Kubernetes | — | `kubectl apply -k k8s/base` (+ overlay `production`); Kustomize base + overlay, verified live in local `kind` |

Postgres/Redis/API/RQ-dashboard ports are bound to `127.0.0.1` only in `docker-compose.yml` (loopback-only network isolation, not to be removed casually — see §8 Security).

Ollama runs on the host at `http://172.29.239.93:11434` (WSL host IP). The default model is `gemma4:e2b` (7.2 GB, fast). `gemma4:26b` is available for formal reports.

Output files go to `reports/`, uploaded files land in `uploads/`. Both are volume-mounted in Docker.

## Key Configuration (`.env` + `config/*.yaml`)
Most `Settings` field defaults now live in `config/*.yaml` (Configuration Center, versioned); `.env` stays for secrets and per-deployment overrides.
- `OLLAMA_BASE_URL` — point to Ollama instance (host or Azure VM)
- `GEMMA_MODEL` — active model (`gemma4:e2b` default)
- `DATABASE_URL` — asyncpg connection string
- `REDIS_URL` / `REDIS_PASSWORD` — broker + cache; `REDIS_PASSWORD` is required by `docker-compose.yml` (`redis --requirepass`), generate a real value, don't leave it as the placeholder
- `API_KEYS` — comma-separated `key` or `key:role` for `security.auth.get_current_principal`; blank (dev default) means every checked route treats the caller as admin — see CLAUDE.md Architecture §1/§8
- `AI_CACHE_TTL` / `GIS_CACHE_TTL` — Redis TTLs for AI and GIS responses
