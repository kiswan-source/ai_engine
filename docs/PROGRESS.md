# AI_ENGINE v4 — Catatan Progres & Resume

> Catatan lanjutan pembangunan enterprise multi-agent per `MASTER_INSTRUCTION.md`
> (tersimpan di `D:\01_Project\AI ENGINE` = `/mnt/d/01_Project/AI ENGINE`,
> **bukan** di `docs/` repo git ini — dua lokasi berbeda).
> Sumber kebenaran = MASTER_INSTRUCTION.md (v1.4, 69 Bab — naik dari v1.3/68 Bab
> per 6 Juli 2026, Bab 69 Project Workspace & Folder Access/ADR-0005) + 16
> dokumen pendamping (9 backend, 2 product-facing, 5 implementation-facing dari
> FINAL ARCHITECTURE DECISION 5 Juli 2026).

## Status per 2026-07-05

| Tahap | Fokus | Status |
|---|---|---|
| 1 | Provider Layer + Registry | ✅ SELESAI |
| 2 | Orchestrator + Workflow (sequential, parallel) | ✅ SELESAI |
| 3 | Shared Memory + Message Bus (Redis/Postgres) | ✅ SELESAI |
| 4 | Reflection / Consensus / Confidence / Human Approval | ✅ SELESAI |
| 5 | RAG penuh (chunker→embed→store→retrieve→hybrid→rerank→context) | ✅ SELESAI |
| 6 | Observability + Cost (tracing, metrics, cost_tracker, dashboards) | ✅ SELESAI |
| 7 | Security hardening (guardrails, output validation, audit log, RBAC) | ✅ SELESAI |
| 8 | Kubernetes ready (manifest siap + diverifikasi live di kind) | ✅ SELESAI |
| 9* | Circuit Breaker (Bab 55) — pasca-roadmap, prioritas #1 gap kumulatif | ✅ SELESAI |
| 10* | RBAC ke `agent/tools/` — pilot 1 tool (`write_pdf`), Bab 30 rule 2 | ✅ SELESAI |
| 11* | UI Multi-Agent — expose `orchestrator/`+`agents/`+`workflows/` ke web UI | ✅ SELESAI |
| 12* | Frontend AI Workspace (React) Phase 1 + Monitoring/Memory/Knowledge (Phase 2) | ✅ SELESAI |
| 13* | Projects — entity Phase 3 pertama (PROJECT_SPECIFICATION.md) | ✅ SELESAI |
| 14* | Vision — gambar sungguhan lewat Orchestrator (Bab 17.1 role), extend `BaseProvider` | ✅ SELESAI |
| 15* | Automation — scheduler in-process untuk workflow terjadwal (Bab 68 Prioritas 5) | ✅ SELESAI |
| 16* | Plugin — `PluginInterface` + plugin Weather nyata via Chat tool-calling (Bab 59) | ✅ SELESAI |
| 17* | MCP Client — konsumsi MCP server nyata via SDK resmi, bridge ke Chat tool-calling (Bab 60) | ✅ SELESAI |
| 18* | Selesaikan migrasi RBAC ke `write_*`/`convert_geo`/`generate_code` (janji ADR-0013) | ✅ SELESAI |
| 19* | Project Workspace & Folder Access — registrasi folder lokal sebagai sumber kerja Agent (Bab 69, ADR-0005) | ✅ SELESAI |
| 20* | Sambungkan RBAC ke ChatEngine — tutup gap yang diakui sejak Tahap 10/16/17/18 | ✅ SELESAI |
| 21* | Dockerfile multi-stage (Bab 37 rule 2) — `docker/Dockerfile.api`/`Dockerfile.worker` + `.dockerignore` baru | ✅ SELESAI |
| 22* | Kepemilikan sesi Chat — tutup gap yang sengaja ditinggalkan Tahap 20 | ✅ SELESAI |
| 23* | Agent Workspace Context ke ChatEngine (Bab 69.5) — Chat bisa baca Project Workspace, bukan cuma Uploaded Files | ✅ SELESAI |
| 24* | Kepemilikan file download Chat — tutup gap yang sengaja ditinggalkan Tahap 22/23 | ✅ SELESAI |
| 25* | Autentikasi + fix path traversal `api/routes/files.py` — tutup bypass nyata yang ditemukan Tahap 24 | ✅ SELESAI |
| 26* | Autentikasi `memory.py`/`monitoring.py`/`knowledge.py` — pola gap sama seperti `files.py` sebelum Tahap 25 | ✅ SELESAI |
| 27* | Loose ends Docker — `tesseract-ocr`/`tesseract-ocr-ind` + `HEALTHCHECK` di `Dockerfile.api`/`Dockerfile.worker` (gap dicatat Tahap 21) | ✅ SELESAI |
| 28* | MCP Server (Bab 60) — ekspos tool registry AI_ENGINE ke client MCP eksternal, arah sebaliknya dari Client Tahap 17 | ✅ SELESAI |
| 29* | Gambar/GIS Workspace via Chat (Bab 69.5 Vision) — `workspace_read_file` kini bisa gambar (vision sungguhan) & GIS (ringkasan luas), bukan cuma dokumen | ✅ SELESAI |

**Roadmap 8-tahap dari `MASTER_INSTRUCTION.md`/`DEVELOPMENT_ROADMAP.md` selesai seluruhnya per 2026-07-05.** Lihat "Gap kumulatif" di bawah untuk daftar hal yang diakui belum sempurna di setiap tahap — peta kerja realistis untuk sesi-sesi berikutnya, bukan checklist yang harus diselesaikan sebelum sistem bisa dipakai.

## Yang sudah dibangun

**Tahap 1 — `providers/` + `registry/`**
- `providers/`: `base_provider.py` (BaseProvider + GenerationParams/ProviderResponse/Chunk),
  `exceptions.py` (AIEngineError→ProviderError…), `ollama_provider.py` (NYATA, reuse
  `core/ai/gemma_client.py`), `openai/claude/gemini_provider.py` (adapter REST httpx,
  aktif saat API key ada), `provider_factory.py`.
- `registry/provider_registry.py` (Bab 19), `registry/model_registry.py` (Bab 20).
- Config di `api/config.py` + `.env.example`. ADR: `docs/adr/ADR-0001-*.md`.

**Tahap 2 — `agents/` + `orchestrator/` + `workflows/`**
- `agents/base_agent.py` (Task, AgentResult, BaseAgent), `agents/generic_agent.py`.
- `registry/agent_registry.py` (Bab 19, 15 peran).
- `orchestrator/`: planner, routing_engine (Bab 53), dispatcher (fallback Bab 54),
  execution_graph (DAG), task_manager (state machine Bab 49), orchestrator (entry).
- `workflows/`: base, sequential (chaining), parallel (gather). ADR: `ADR-0005-*.md`.

**Tahap 3 — `memory/` + `messaging/` (Bab 22–23)** — ADR: `ADR-0006-*.md`
- `messaging/`: `schemas.py` (AgentMessage per Bab 17.3, Event, QueuedTask),
  `events.py` (event = cermin state Bab 48.1/49.1), `broker.py` (InMemoryBroker
  dev/CI + RedisBroker Pub/Sub & list, dipilih `MESSAGE_BROKER`), `message_bus.py`
  (p2p/broadcast per agent), `event_bus.py` (publish best-effort, subscribe glob
  `agent.*`), `task_queue.py` (FIFO worker hand-off).
- `memory/`: `stores.py` (HashStore/ListStore in-memory|Redis) + 6 tier:
  working (Redis TTL), conversation (PostgreSQL `conversation_messages`),
  summary (summarizer injektabel, default provider peran `memory`), long_term
  (PostgreSQL `memory_entries`, upsert), vector (Tahap 3: hashed-BOW placeholder;
  Tahap 5: embedding + pgvector nyata, lihat di bawah), reflection (jurnal per
  peran, capped) + `memory_manager.py` (facade/factory).
- Integrasi: Orchestrator publish `workflow.<state>` di tiap transisi; Dispatcher
  publish `agent.assigned/running/retry/completed/failed` (exit criteria Tahap 3).
  `TaskManager` dapat seam `TaskStore` → `RedisTaskStore` (klien sync, TTL) via
  `TASK_STATE_BACKEND=redis`, kontrak tidak berubah.
- **Bugfix fondasi:** `init_db()` tidak pernah membuat tabel (db.models tak pernah
  di-import siapa pun) — kini `init_db()` meng-import `db.models` sebelum `create_all`.

**Tahap 4 — Reflection / Consensus / Confidence / Human Approval (Bab 25, 26, 28, 61)** — ADR: `ADR-0007-*.md`
- `orchestrator/confidence.py`: `ConfidenceScorer` membaurkan self-reported +
  historical accuracy (`ReflectionMemory`) + agreement rate (opsional, dari
  Consensus/Voting) jadi satu skor `[0.0, 1.0]`; `threshold_for("default"|"high")`
  baca `CONFIDENCE_THRESHOLD_DEFAULT`/`CONFIDENCE_THRESHOLD_HIGH_RISK`.
- `orchestrator/reflection.py`: `ReflectionEngine` — generate→self-evaluate→revise
  hingga `REFLECTION_MAX_ITERATIONS` (default 3), tiap iterasi dicatat ke
  `ReflectionMemory`; ambang tak tercapai → `ReflectionOutcome.escalate=True`
  (tidak dipaksa lolos, Bab 25 rule 3).
- `orchestrator/consensus.py`: `ConsensusEngine` — Majority Voting, Weighted
  Voting, Arbitrator Model (role `consensus`); tiap keputusan menerbitkan
  `consensus.decided` (event yang sudah ada sejak Tahap 3).
- Tiga workflow baru di `workflows.WORKFLOWS`: `reflection` (chaining seperti
  sequential, tiap step lewat ReflectionEngine), `voting` (dispatch independen →
  majority vote), `consensus` (`CONSENSUS_DEBATE_ROUNDS` ronde structured debate →
  arbitrase). Semua mengembalikan `WorkflowResult.escalate=True` saat
  confidence/agreement di bawah ambang.
- `workflows/approval.py`: `HumanApprovalGate` — **bukan** `BaseWorkflow` (ia
  menggerbang hasil, bukan memproduksinya dari graf). `Orchestrator.run()`
  berhenti di `State.REVIEWING` + `approval.request()` saat `result.escalate`
  (dan `ENABLE_HUMAN_APPROVAL=true`); `Orchestrator.finalize_approval()` dipanggil
  manusia untuk lanjut ke `APPROVED→COMPLETED` atau `CANCELLED` — transisi state
  machine ini sudah ada sejak Tahap 2, tak berubah.
- `Planner.plan()` menerima 5 mode sekarang (`sequential`, `parallel`,
  `reflection`, `voting`, `consensus`); mode chained vs independen diatur satu
  set konstanta (`_CHAINED_MODES`).
- **Bugfix laten:** siklus impor `orchestrator` ↔ `workflows` (ada sejak Tahap 2,
  baru kepegang saat `workflows/__init__.py` jadi lebih berat) — diperbaiki
  dengan impor lokal di dalam method, bukan level modul. Lihat ADR-0007.

**Antara Tahap 4 dan 5 — API key cloud diaktifkan**
- OpenAI, Anthropic, Google API key live di `.env` lokal (gitignored; sumber
  `D:\01_Project\AI ENGINE\engine-k.txt`). Diverifikasi dengan `generate()`
  sungguhan, bukan cuma `health_check()`.
- **3 bug provider ditemukan & diperbaiki** (sebelumnya masking karena tak
  pernah dites live): (1) `claude-sonnet-5` menolak `temperature`/`top_p`
  ("deprecated for this model") — `ClaudeProvider` retry otomatis tanpa
  sampling param; (2) `GEMINI_MODEL` default (`gemini-1.5-pro`) sudah 404 —
  diganti `gemini-pro-latest`; (3) ketiga provider salah menangani
  `api_key=""` eksplisit (`"" or settings.X` jatuh ke key asli) — diganti
  `is not None`. Model aktual: `gpt-4o`, `claude-sonnet-5`, `gemini-pro-latest`.

**Tahap 5 — RAG penuh (Bab 29)** — ADR: `ADR-0008-*.md`
- **Infra pgvector**: `docker/Dockerfile.postgres` (postgis/postgis:16-3.4-alpine
  + `apk add postgresql-pgvector`, file extension di-copy manual ke path yang
  dibaca server sungguhan — base image punya build Postgres sendiri di
  `/usr/local`, terpisah dari paket Alpine di `/usr/share/postgresql16`).
  `docker-compose.yml`: service `postgres` dari `image:` jadi `build:`.
  Container sudah direbuild+direstart (volume data utuh), `CREATE EXTENSION
  vector` sudah dijalankan di DB yang hidup. `scripts/init_db.sql` diupdate
  untuk volume baru di masa depan.
- `db.models.VectorEmbedding` — satu tabel `vector_embeddings`
  (`namespace`, `text`, `meta`, `embedding Vector(RAG_EMBEDDING_DIM)`) dipakai
  BAIK oleh Vector Memory (namespace `"memory"`) MAUPUN korpus RAG (namespace
  `"rag:documents"` dst) — bukan dua skema terpisah.
- `rag/` (7 modul Bab 29): `chunker.py` (chunking karakter+overlap, snap ke
  spasi), `embeddings.py` (`default_embedder()` pilih provider dari
  `RAG_EMBEDDING_PROVIDER`, jatuh ke hashed-BOW deterministik jika provider
  nonaktif — TIDAK fallback ke provider cloud lain karena dimensi vektor beda),
  `knowledge_store.py` (`KnowledgeStore` ABC: `InMemoryKnowledgeStore` dev/CI +
  `PgVectorKnowledgeStore` produksi, `cosine_distance` via `<=>`),
  `retriever.py` (`Retriever.index_document()` — satu-satunya jalur resmi
  index dokumen, memaksa lewat chunker + tag `chunk_index` untuk sitasi),
  `hybrid_search.py` (BM25 manual di atas kandidat semantic, tanpa dependency
  baru, blend via `RAG_HYBRID_ALPHA`), `reranker.py` (`rerank()` heuristik
  boost token mirip-kode selalu aktif via `RAG_RERANK_ENABLED`; `llm_rerank()`
  opsional pakai role `consensus`/`critic`, tak otomatis di pipeline default),
  `context_builder.py` (`build_context()` — blok bersitasi di bawah budget
  `RAG_MAX_CONTEXT_CHARS`).
- `memory/vector_memory.py` diupdate memenuhi janji ADR-0006: `VectorMemory`
  kini terima `store`/`embedder` pluggable (default tetap hashed-BOW +
  in-memory, Bab 12); `memory_manager.build_memory_manager()` yang membaca
  `VECTOR_BACKEND`/`RAG_EMBEDDING_PROVIDER` untuk memasang yang nyata.
  **Satu perubahan kontrak:** `VectorMemory.count()`/`.clear()` jadi async
  (perlu untuk delegasi ke store async) — `add`/`search` tak berubah.
- **Diverifikasi live end-to-end**: embedding OpenAI nyata (`text-embedding-3-small`,
  1536 dim) + pgvector nyata — dokumen dengan nomor sertifikat spesifik
  (`IUP-2024-0087`) naik dari peringkat semantic #1 (score 0.627) tetap #1
  setelah hybrid+rerank (score 1.0), sementara dokumen tak relevan turun.
  `memory_manager.build_memory_manager()` juga diverifikasi memasang
  `PgVectorKnowledgeStore` + embedder OpenAI otomatis dari `.env`.
- **Ditemukan, di luar cakupan Tahap 5** (diperbaiki 2026-07-05, lihat
  catatan susulan di bawah tabel Tahap 5 — commit `67ec6f0`): tabel
  `documents`/`gis_projects`/`ai_jobs` (dibuat `scripts/init_db.sql` lama
  dengan tipe/kolom tak sinkron dengan model SQLAlchemy). Sudah diperbaiki.

**Tahap 6 — Observability + Cost (Bab 27, 33-35, 56, 62)** — ADR: `ADR-0009-*.md`
- `telemetry/` 5 modul Bab 34: `tracing.py` (`Tracer` — subscribe
  `agent.*`/`workflow.*`/`consensus.decided`, rekonstruksi Execution Timeline
  penuh per trace_id, reuse `memory.stores.ListStore`), `metrics.py`
  (`MetricsCollector` — counts, error/success rate per role/provider, latensi
  p50/p95/p99 per agent + end-to-end per workflow mode), `cost_tracker.py`
  (`CostTracker` — subscribe `agent.completed`, tabel harga USD/1K token per
  provider+model, `cost_for_trace`/`cost_by_provider`/`cost_by_role`/
  `cost_for_day`), `logging.py` (re-export `core.utils.logger`, Bab 11 sudah
  terpenuhi, bukan config baru), `monitoring.py` (8 dashboard Bab 62 +
  `check_alerts()` + `check_readiness()` yang kini juga cek tiap provider
  cloud aktif, dipakai bersama oleh `/health/ready`).
- **Dispatcher diperkaya, bukan dipasangi tracker** — event `agent.completed`
  kini membawa `model`/`prompt_tokens`/`completion_tokens`/`confidence`;
  semua telemetry murni subscriber Event Bus, nol pemanggilan langsung dari
  Dispatcher/Orchestrator (menepati janji desain Tahap 3).
- **Cost budget → eskalasi Human Approval** — `Orchestrator.run()` hitung
  `cost_for_trace()` setelah workflow selesai; melebihi
  `COST_BUDGET_PER_TASK` pakai jalur `REVIEWING`+`HumanApprovalGate` yang
  SAMA dengan `result.escalate` (Tahap 4), reason `"cost_budget_exceeded"`
  (sudah didefinisikan sejak Tahap 4, baru dipakai sekarang).
- `Orchestrator` punya `self.costs`/`self.metrics`/`self.tracer`, di-subscribe
  lazy di awal `run()`/`run_single()` (constructor tak bisa `await`).
- **Diverifikasi live end-to-end**: panggilan Claude sungguhan lewat
  `Orchestrator()` — cost tercatat benar ($0.000423 untuk 1 kalimat jawaban),
  metrics snapshot benar, timeline lengkap 7 event. `check_readiness()` live
  melaporkan DB/Redis/Ollama/OpenAI/Claude/Gemini semua "ok". Cost-budget
  escalation diverifikasi dengan agent token tinggi buatan → benar berhenti
  di REVIEWING → `finalize_approval()` → COMPLETED.
- **Ditemukan & diperbaiki (regresi dari Tahap 5, bukan Tahap 6 sendiri):**
  container Docker `ai_engine_api` sudah gagal start ~2 jam sejak
  `pgvector` ditambah ke `requirements.txt` tapi image `api`/`worker_ai`/
  `worker_gis` tak pernah di-rebuild (Tahap 5 cuma rebuild `postgres`).
  `uvicorn --reload` bikin container tetap tampak "Up" walau `init_db()`
  gagal berulang — tak kelihatan dari `docker ps`, baru ketahuan saat
  `curl /health/ready` dicoba live. Diperbaiki: rebuild + recreate ketiga
  service; DNS error worker→redis yang ikut ketemu ternyata transient,
  hilang sendiri setelah recreate.
- **Gap yang diakui**: Workflow Dashboard tak bisa tampilkan "workflow aktif
  sekarang" (TaskManager tak punya enumerasi); Provider Dashboard tanpa
  status Circuit Breaker (Bab 55 belum diimplementasikan sama sekali);
  Memory Dashboard cuma lapor `vector.count()` (tier lain tak punya metode
  ukuran). Tak ada route API/frontend untuk dashboard — murni lapisan data.

**Tahap 7 — Security hardening (Bab 30, 31, 45, 58)** — ADR: `ADR-0010-*.md`
- `security/` 6 modul: `prompt_guard.py` (heuristik pattern-based, dua
  ambang — di atas `PROMPT_GUARD_SUSPICIOUS_THRESHOLD` menetralisir span
  mencurigakan jadi `[neutralized]`, di atas `PROMPT_GUARD_BLOCK_THRESHOLD`
  memblokir total, persis kata Bab 30 "mendeteksi dan menetralisir"),
  `pii_detector.py` (regex email/telepon ID/NIK/kartu kredit/IPv4, redaksi
  hanya untuk provider eksternal — bukan Ollama), `output_validator.py`
  (skor kebijakan output: kosong/truncated/artefak template/kebocoran PII —
  **mengisi sinyal ke-4 Confidence Scoring yang ditinggalkan kosong sejak
  ADR-0007**), `audit_log.py` (JSON append-only ke `AUDIT_LOG_PATH` —
  file terpisah dari `audit.log` yang sudah dipakai systemd — + terbitkan
  event `security.*`), `auth.py` (Principal + API-key lookup, `API_KEYS`
  kosong = nonaktif), `permissions.py` (RBAC role→permission, `has_permission`/
  `require_permission`/`require_role`).
- **Satu choke point**: `agents/generic_agent.py`'s `GenericLLMAgent.execute()`
  (dipakai semua 15 peran, BUKAN folder `agent/tools/` yang FONDASI
  terlindungi) — prompt_guard + redaksi PII sebelum `generate()`,
  output_validator sesudahnya. `AgentResult` dapat 2 field baru:
  `guardrail_blocked`, `guardrail_score`.
- **Eskalasi otomatis di SEMUA mode workflow** — `BaseWorkflow._aggregate()`
  kini menghitung `guardrail_blocked = any(...)` dan meng-OR-kannya ke
  `escalate`, bukan cuma reflection/voting/consensus yang sudah py escalate
  sendiri (Bab 31 rule 4 — blokir wajib eskalasi, bukan gagal diam-diam).
  `Orchestrator.run()` pilih reason `"guardrail_blocked"` saat itu penyebabnya.
- **`ConfidenceScorer.score()`** dapat param `guardrail_score` yang **default
  ke `result.guardrail_score`** bila tak diberi — `ReflectionEngine`
  otomatis dapat sinyal ini TANPA perubahan kode di `reflection.py` sama
  sekali (opt-out, bukan opt-in). Bobot dirombak 3→4 sinyal (self-reported
  0.4, history 0.2, agreement 0.15, guardrail 0.25).
- **RBAC nyata satu titik**: `Orchestrator.finalize_approval(..., role=None)`
  — beri `role` untuk memaksa cek `approve_workflow`; tanpa `role` (default)
  = perilaku persis sebelum Tahap 7. `HumanApprovalGate.decide()` sekarang
  benar-benar menulis audit log (memenuhi Bab 61.3 rule 2 yang belum
  terpenuhi sejak Tahap 4).
- `telemetry.tracing.Tracer` tambah pola subscribe `security.*` — Execution
  Timeline ikut memuat aksi keamanan.
- **`tests/conftest.py` baru** (autouse, isolasi `AUDIT_LOG_PATH` ke temp
  file per test) — perlu karena `HumanApprovalGate.decide()` yang dipakai
  luas sejak Tahap 4 kini menulis file sungguhan; tanpa ini seluruh suite
  akan mengotori `security_audit.log` di root repo setiap dijalankan.
- **Diverifikasi live end-to-end**: prompt berisi PII nyata → redacted
  sebelum ke Claude, jawaban normal; prompt injection nyata ("ignore all
  previous instructions...") → diblokir total, eskalasi ke REVIEWING
  dengan reason `guardrail_blocked`; RBAC menolak role `user` lalu menerima
  role `approver`; audit trail berisi kedua kejadian dengan trace_id yang
  benar.
- **Gap yang diakui**: RBAC tidak dipasang ke `agent/tools/` (Bab 30 rule 2's
  sasaran asli) — folder itu FONDASI terlindungi (Bab 45.1), butuh migrasi
  bertahap di luar cakupan satu sesi. `auth.py`/`permissions.py` tidak
  dipasang ke route API manapun — semua endpoint tetap terbuka persis
  seperti sebelumnya.

**Tahap 8 — Kubernetes ready (Bab 37, 38, 58.1, 64)** — ADR: `ADR-0011-*.md`
- **Bugfix statelessness (Bab 38 rule 1)**: `workflows/approval.py`'s
  `HumanApprovalGate` pindah dari `dict` in-memory ke `HashStore` pluggable
  (pola sama dengan setiap tier lain sejak Tahap 3) — config baru
  `APPROVAL_STATE_BACKEND` (memory|redis). `get()`/`pending()`/`overdue()`
  jadi async (breaking change sejenis `VectorMemory` Tahap 5).
  `Orchestrator.pending_approvals()` ikut jadi async. Diverifikasi live: dua
  instance `HumanApprovalGate` di atas `RedisHashStore` yang sama
  benar-benar saling melihat request & keputusan — simulasi dua pod.
- **`k8s/` manifest set (Kustomize, bukan Helm — Bab 45.3)**: `base/`
  (Namespace, ConfigMap persis mengikuti `api/config.py`, Secret template
  ber-placeholder eksplisit, StatefulSet Postgres+headless Service+PVC
  pakai image pgvector dari `docker/Dockerfile.postgres`, Deployment
  Redis+Service+PVC, Deployment API 2 replika + Service dengan liveness
  `/health/` & readiness `/health/ready`, dua Deployment worker terpisah —
  Bab 38 rule 4). `overlays/production/` mendemonstrasikan Bab 64
  "build once, promote everywhere" (image sama, tag registry + replica
  count beda). `scripts/init_db.sql` di-generate via kustomize
  `configMapGenerator` langsung dari file asli — cegah drift yang sama
  seperti insiden Tahap 5 (ADR-0008).
- **Verifikasi RQ graceful shutdown** — dicek langsung di source `rq==1.16.2`
  terpasang: `Worker.request_stop()` sudah warm-shutdown (tunggu job
  selesai) built-in di SIGTERM pertama. Bab 38 rule 5 terpenuhi untuk
  worker tanpa kode tambahan; tidak ada liveness/readiness probe untuk
  worker (RQ tanpa HTTP surface, exec probe berarti butuh tooling yang
  belum ada di image — dicatat sebagai gap, bukan probe palsu).
- **Diverifikasi live di `kind`** (2026-07-05, susulan ke sesi awal Tahap 8,
  lihat addendum ADR-0011): cluster lokal, image di-push ke registry lokal,
  `kubectl apply -k` → 6 pod `1/1 Running` (Postgres, Redis, API, 2×
  worker-ai, worker-gis); `/health/`+`/health/ready` 200 lewat pod maupun
  Service; RQ worker subscribe queue; API `init_db()` sukses ke Postgres
  in-cluster. **Satu bug nyata ditemukan & diperbaiki**: probe
  `pg_isready` di `postgres-statefulset.yaml` pakai `$(POSTGRES_USER)` yang
  TIDAK di-ekspansi Kubernetes untuk `exec.command` probe (beda dari
  `command`/`args` container biasa) — akibatnya autentikasi sebagai `root`
  dan membanjiri log `FATAL: role root does not exist` tiap 10 detik
  selamanya (silent karena pod tetap `Ready`); diperbaiki bungkus `sh -c`
  + tambah `-d "$POSTGRES_DB"` eksplisit.
- **Gap yang diakui**: Dockerfile belum multi-stage (Bab 37 rule 2) —
  ditolak dikerjakan sesi ini karena image yang sama baru diperbaiki dari
  insiden gagal-start Tahap 6 (ADR-0009); PVC uploads/reports asumsi
  `ReadWriteMany` — **dikonfirmasi nyata gagal di kind**
  (`ProvisioningFailed: NodePath only supports ReadWriteOnce`, StorageClass
  `standard` bawaan kind cuma RWO); Postgres/Redis single-instance, bukan HA;
  CI belum build/push image container.

**Tahap 9 (pasca-roadmap) — Circuit Breaker (Bab 55)** — ADR: `ADR-0012-*.md`
- `providers/circuit_breaker.py`: `CircuitBreaker` state machine persis Bab
  55.2 (Closed→Open→Half-Open; `failure_threshold`/`recovery_timeout`/
  `trial_requests` per Bab 55.3), state di `HashStore` pluggable
  (`CIRCUIT_STATE_BACKEND=memory|redis` — pola Tahap 3/8, Bab 38 rule 1:
  trip di satu pod terlihat semua pod; timestamp wall-clock). Parameter per
  provider via `CIRCUIT_PROVIDER_OVERRIDES="openai:3/60/1,…"` (aturan
  penutup Bab 55 — tidak disamaratakan); entri malformed → ValueError keras.
- **Integrasi satu titik di `Dispatcher`**: breaker primer Open → langsung
  switch-provider tanpa menyentuh provider; setiap hasil panggilan mengumpan
  breaker; trip di tengah retry menghentikan sisa retry; breaker fallback
  ikut dicek (keduanya Open → fail fast via `AgentResult.error`, Bab 10.4).
  `ENABLE_CIRCUIT_BREAKER=false` = perilaku lama persis.
- Satu registry default (`providers.circuit_breaker.breakers`) dipakai
  bersama Dispatcher + Provider Dashboard (`monitoring.provider_dashboard`
  kini menampilkan status breaker — **menutup gap Provider Dashboard yang
  dicatat sejak Tahap 6**). Event `circuit.opened/half_open/closed` di Event
  Bus; `Tracer` subscribe `circuit.*`. Config di `api/config.py` +
  `.env.example` + `k8s/base/configmap.yaml` (redis).
- `tests/conftest.py`: fixture autouse baru mereset registry breaker default
  per test (Dispatcher tanpa registry eksplisit memakai singleton modul).
- **Diverifikasi live end-to-end**: `ANTHROPIC_BASE_URL` → port mati → 2
  kegagalan nyata membuka breaker (dispatch pertama ~17 dtk); dispatch
  berikutnya dilayani fallback Ollama ~1 dtk tanpa menyentuh Claude;
  dashboard `claude: open`; setelah recovery timeout panggilan Claude
  sungguhan (jawab "PULIH") menutup breaker. Dua registry di atas
  `RedisHashStore` yang sama saling melihat OPEN — simulasi dua pod.

**Tahap 10 (pasca-roadmap) — RBAC ke `agent/tools/`, pilot `write_pdf` (Bab 30 rule 2)** — ADR: `ADR-0013-*.md`
- `security/permissions.py`: `TOOL_RISK_ACTIONS = {"write_pdf": "tool:write_pdf"}`
  (sengaja satu entri — pilot, bukan migrasi penuh) + `check_tool_permission(role, tool_name)`
  (no-op untuk tool di luar peta ini). Role baru `operator` (`tool:write_pdf`, `view_dashboard`).
- **Gerbang aditif di choke point yang sudah ada**: `ToolRegistry.execute()`
  (`agent/tools/registry.py`, folder fondasi Bab 45.1) dapat parameter
  opsional `role: str | None = None` — `None` (default) = perilaku identik
  sebelum ADR ini, strangler pattern murni tanpa hapus/tulis-ulang baris lama.
  `core/chat/engine.py` (folder fondasi lain) tidak disentuh dan tidak
  pernah mengirim `role`, jadi tidak terpengaruh sama sekali.
- `agent/core.py` (bukan folder fondasi): `AIAgent(role=...)` diteruskan ke
  `registry.execute(..., role=self.role)`; `_execute()` jadi `async def`
  (pola breaking-change yang sama seperti Tahap 5/8) supaya bisa
  `await audit_log.record("tool_access.denied", ...)` saat `PermissionError`
  tertangkap.
- **Route API pertama yang benar-benar memasang RBAC**: `/api/v1/agent/run`
  (`api/routes/agent.py`) dapat `Depends(get_current_principal)` →
  `AIAgent(role=principal.role)`. `API_KEYS` kosong (default dev) tetap
  `role="admin"` → nol perubahan perilaku untuk siapa pun yang belum
  mengonfigurasi API key.
- **Diverifikasi live end-to-end**: panggilan langsung ke `AIAgent(role=...)
  ._execute()` dengan tool `write_pdf` SUNGGUHAN — `role="user"` ditolak +
  entri `tool_access.denied` nyata di `security_audit.log`;
  `role="operator"`/`"admin"`/`None` menghasilkan PDF sungguhan di `reports/`.
  Lapisan HTTP diverifikasi terpisah via `TestClient` + `API_KEYS` live
  (`userkey:user,opkey:operator`): key valid diterima 200, key tak dikenal
  ditolak 401.

**Tahap 11 (pasca-roadmap) — UI Multi-Agent, expose `orchestrator/` ke web** (permintaan Boss: "sesuaikan UI-nya agar terintegrasi dengan sistem yang sudah dikembangkan sekarang")
- **Gap yang ditutup**: sejak Tahap 1-10, `orchestrator/`+`agents/`+`workflows/`
  (planner, routing, dispatcher+circuit breaker, 5 mode workflow, RAG,
  telemetry, RBAC approval) 100% backend — nol route API, nol UI. `web/`
  cuma bicara ke `core/chat/engine.py` (single-agent tool-calling sederhana,
  sistem yang berbeda). Ditanya eksplisit ke Boss dulu (pakai
  `AskUserQuestion`) sebelum memilih cakupan: dashboard observability vs.
  chat beralih ke Orchestrator vs. form RBAC — Boss pilih **chat UI beralih
  ke Orchestrator multi-agent**.
- **Router baru `api/routes/orchestrator.py`** (bukan folder fondasi —
  tidak perlu strangler pattern): `GET /roles` (15 peran Bab 17.1),
  `GET /modes` (5 `WORKFLOWS`), `POST /run` (`Orchestrator.run()`,
  `dataclasses.asdict(WorkflowResult)` + `state` dari `TaskManager`),
  `GET /approvals` (`pending_approvals()`), `POST /approvals/{trace_id}/decide`
  (`finalize_approval(role=principal.role)` — RBAC `approve_workflow` yang
  sudah ada sejak ADR-0007 akhirnya kepakai dari HTTP, bukan cuma test).
  Satu `Orchestrator()` singleton per proses (pola sama dengan
  `providers.circuit_breaker.breakers`) supaya approval yang dibuka satu
  `/run` masih ada untuk `/approvals/*` berikutnya di proses yang sama.
- **`web/` (bukan folder fondasi) dapat panel baru, aditif murni** — tab
  switcher "💬 Chat" / "🕸️ Multi-Agent" di header; `core/chat/`'s
  streaming loop di `app.js` tidak disentuh sama sekali. File baru
  `web/orchestrator.js` (roles jadi checkbox berurutan, mode select, jalankan
  workflow, render tiap `AgentResult` per-agent dengan confidence/cost/
  provider, badge escalate/guardrail/degraded, form Approve/Reject inline
  saat `state="reviewing"`, daftar pending approvals) — reuse
  `escapeHtml()`/`mdToHtml()`/`$()` dari `app.js` (script klasik, scope
  global bersama), tidak duplikasi.
- **Diverifikasi live end-to-end**: restart `ai-engine.service` (port 8001,
  butuh restart manual — bukan `--reload`) → `GET /roles`/`modes` benar;
  `POST /run` role `tool` (Ollama lokal, hindari biaya cloud OpenAI/Claude/
  Gemini yang live di `.env`) jalan lewat Dispatcher+telemetry sungguhan,
  balas `state=completed` (output kosong — kuirk `gemma4:e2b` yang sudah
  dicatat sebelumnya, bukan bug baru). Screenshot headless Chrome kedua tab:
  Chat tampil seperti semula, panel Multi-Agent tampil dengan 15 role chip
  ter-load dari API sungguhan.

**Tahap 12 — Frontend AI Workspace (React), Phase 1 penuh + Phase 2 parsial (Monitoring)**

Bukan permintaan langsung dari roadmap backend — dipicu 19 dokumen blueprint
produk/arsitektur frontend (`MASTER_INSTRUCTION.md` §67, tersimpan di
`/mnt/d/01_Project/AI ENGINE/docs/`, **bukan** `docs/` repo ini) yang
menetapkan `AI_ENGINE` sebagai **AI Workspace** (bukan sekadar chat), dengan
stack final React + TypeScript + Vite + TailwindCSS v4 + shadcn/ui + React
Router + Zustand + Lucide + ESLint + Prettier + Vitest + RTL
(`FRONTEND_ARCHITECTURE.md`/`DESIGN_SYSTEM.md`).

- **`API_CONTRACT.md` blueprint sudah basi terhadap kode nyata** saat dibaca —
  kontrak `chat.py` di dokumen itu (`POST /chat/messages`) beda total dari
  `chat.py` sungguhan (`/stream` SSE, `/upload`, `/sessions`, `/models`), dan
  `orchestrator.py` didokumentasikan "Perlu Baru" padahal sudah wired sejak
  Tahap 11. Seluruh frontend dibangun dari kontrak API **nyata**, diverifikasi
  langsung dari source, bukan dari blueprint yang basi.
- **`web/` dibangun ulang dari nol** (FINAL ARCHITECTURE DECISION: no gradual
  migration) — frontend lama (`app.js`, `index.html`, `style.css`,
  `orchestrator.js` dari Tahap 11) di-backup ke `backups/web_legacy_20260705/`
  sebelum dihapus, tidak hilang. Struktur folder persis
  `FRONTEND_ARCHITECTURE.md` §1: 11 Zustand store (ui/chat/workflow/agent/
  approval/history/settings/notification/attachment/session/project),
  `services/{apiClient,chatService,workflowService,fileService,
  monitoringService,eventStream}.ts`, `types/`, `hooks/`.
- **Chat, Workflow (Timeline minimal via polling `/run` sinkron), Approval
  minimal, History, Settings, Files sungguhan jalan** — bukan mock. Files
  awalnya placeholder Phase 2 lalu diwire sungguhan begitu ketahuan
  `files.py` (`GET /reports`, `GET /uploads`, `POST /upload`, prefix root)
  sudah READY. `services/eventStream.ts` ditulis mengikuti `EVENT_CATALOG.md`
  (event kanonis PascalCase) tapi belum dipakai — endpoint SSE canonical
  belum ada di backend.
- **`api/routes/monitoring.py` baru** (bukan folder fondasi): `GET
  /dashboard` (7 dari 8 dashboard Bab 62 — Agent/Workflow/Provider/Cost/
  Latency/Health/Queue; Memory Dashboard sengaja dilewati, lihat gap di
  bawah), `GET /alerts`. Reuse `_orchestrator` singleton dari
  `api/routes/orchestrator.py`, panggil `_ensure_telemetry_started()` karena
  telemetry cuma `.start()` lazy dari `Orchestrator.run()`, bukan app
  startup.
- **`api/main.py` diubah**: serve `web/dist` (build output) + SPA fallback
  `/{full_path:path}` untuk client-side routing React Router; mount lama
  `/web` (raw source) dihapus.
- **Riset sebelum bangun (Phase 2 Memory/Knowledge)**: dicek dulu apakah
  `memory/`/`rag/` (Tahap 3/5) siap diekspos — ternyata **belum**: `memory/`
  6 tier tidak punya method enumerasi sesi/scope di tier manapun, dan
  `core/chat/engine.py` (fondasi terlindungi) tidak pernah menulis ke
  `memory/` sama sekali (dua sistem terpisah total); `rag/` nol wiring ke
  endpoint manapun, tidak ada ingest/list method. Ditanyakan ke Boss —
  Memory & Knowledge tetap placeholder (alasan diperbarui: gap integrasi
  backend, bukan "API belum dibangun").
- **Diverifikasi live end-to-end** (headless Chromium via Playwright — tidak
  ada `chromium-cli` di lingkungan ini, dipakai REPL driver custom sekali
  pakai): Chat streaming token Gemma sungguhan, Workflow run role `tool`
  sungguhan lewat `/run`, Approval poll endpoint asli, History dari sesi
  chat asli, Settings dari `/models` asli, Files dari `reports/`/`uploads/`
  asli, dan **Monitoring numbers berubah live** setelah workflow run
  (latensi 0→16.73s, workflow selesai 0→1) — bukti telemetry pipeline
  genuinely live. 0 console error di seluruh halaman.

**Tahap 12 lanjutan — Memory & Knowledge diwire sungguhan (bukan lagi placeholder)**

Boss diberi pilihan eksplisit lewat `AskUserQuestion` untuk kedua area ini
(karena masing-masing punya beberapa pendekatan dengan trade-off beda), dan
memilih: Memory diwire apa adanya (bukan integrasi ChatEngine dulu),
Knowledge diwire dengan ingest teks tempel (bukan upload file).

- **`api/routes/memory.py` baru**: `GET /{session_id}` (agregasi
  `working.get_all`/`conversation.get_history`/`summary.get_summary`/
  `long_term.recall_all`, keempatnya scoped ke `session_id`), `DELETE
  /{session_id}/working/{key}`, `DELETE /{session_id}/long-term/{key}`,
  `DELETE /{session_id}/conversation`, `DELETE /{session_id}/summary`.
  Reflection memory (scoped per **role** agent, bukan sesi — mekanisme
  self-improvement internal) dan Vector memory (search-only, tak ada
  listing polos) sengaja dikecualikan, alasan sama seperti Memory Dashboard
  di `telemetry/monitoring.py`. `MemoryPage.tsx` menampilkan keempat tier +
  banner kuning eksplisit ("gap backend yang diketahui, bukan halaman yang
  rusak") karena `core/chat/engine.py` memang belum menulis ke sini —
  diverifikasi live: input session_id apa pun menampilkan keempat section
  kosong dengan benar, 0 console error.
- **`api/routes/knowledge.py` baru** — pemakaian HTTP pertama untuk `rag/`
  (Tahap 5) sama sekali. Reuse tabel `db.models.Document` yang sudah ada
  tapi sebelumnya tak pernah ditulis siapa pun, sebagai manifest ("closest
  fit", bukan mengambil-alih fitur `dokumen.py` yang tak berkaitan). `POST
  /documents` (`Retriever.index_document()`), `GET /documents`, `DELETE
  /documents/{id}` (hapus baris manifest saja — `KnowledgeStore` tak punya
  delete-by-dokumen, chunk tetap ada di vector store, dicatat sebagai
  keterbatasan bukan disembunyikan), `GET /search`. **Bug nyata ketemu di
  test, bukan di pemakaian manual**: rute awalnya bikin `Retriever(...)`
  baru di setiap request — tak masalah di dev lokal ini (pgvector +
  Postgres sungguhan, persisten lepas dari objek Python mana pun yang
  menyentuhnya) tapi berarti backend in-memory (default, dan yang dipakai
  CI tanpa `.env`) melupakan segalanya antar-request. Diperbaiki jadi satu
  `_retriever` singleton level-modul (pola sama seperti `_orchestrator`/
  `_memory`). `KnowledgePage.tsx`: form ingest teks, pencarian semantik,
  daftar sumber — diverifikasi live lewat browser (ingest form sungguhan →
  toast sukses → tampil di daftar → dicari lewat kata kunci tak-persis →
  hasil paling relevan skor tertinggi benar), 0 console error.
- **`aiosqlite` ditambahkan ke `requirements.txt`** (dependency test-only) —
  `api/routes/knowledge.py` adalah rute pertama yang sungguhan memakai
  `db.connection.get_session()`; test-nya butuh DB tanpa Postgres nyata
  (Bab 12.3, CI tak punya live service). SQLite in-memory, hanya
  tabel `documents` yang dibuat (`VectorEmbedding` pakai tipe kolom
  `pgvector` yang gagal di-`create_all()` di SQLite kalau ikut disertakan).

**Tahap 13 — Projects, entity Phase 3 pertama**

Boss minta "Phase selanjutnya" lagi setelah Tahap 12. Dicek dulu (bukan
diasumsikan dari blueprint) status riil kelima area Phase 3
(Projects/Plugin/Automation/Vision/MCP): **nol kode di kelimanya** — tak
ada tabel `Project`, tak ada folder `plugins/`/`scheduler/`, tak ada
apa-apa terkait MCP di manapun; "Vision" cuma nama role yang lewat satu
implementasi generik (`agents/generic_agent.py`), `/run` sama sekali tak
menerima upload gambar. Beda jauh dari Tahap 12 yang tinggal expose modul
yang sudah ada. Ditanya ke Boss lewat `AskUserQuestion`, dipilih **Projects
duluan** — paling siap secara desain (`PROJECT_SPECIFICATION.md` sudah
punya skema).

- **`db.models.Project`/`ProjectMember` baru** — skema diadaptasi dari
  `PROJECT_SPECIFICATION.md` §3, dengan satu penyesuaian sadar: spek
  menyebut `owner_id (FK → User)`, tapi **tidak ada tabel `User` di
  manapun di sistem ini** — identitas nyata yang ada cuma string API key
  (`security.auth.Principal`). `owner_key`/`ProjectMember.principal_key`
  jadi string API key, bukan FK ke user yang tak eksis. §6 spek sengaja
  membiarkan soft-delete vs hard-delete belum diputuskan — dipilih
  **soft-delete** (`status="archived"`), selaras prinsip Preserve Existing
  Code (Bab 3) diterapkan ke data pengguna.
- **`api/routes/projects.py` baru**: `GET/POST /projects`, `GET/PATCH/DELETE
  /projects/{id}` (DELETE = arsipkan, bukan hapus baris), `POST/DELETE
  /projects/{id}/members[/{principal_key}]`. RBAC per-resource sungguhan
  (bukan cuma per-endpoint seperti rute lain) — `owner`/`editor`/`viewer`
  dicek dari `ProjectMember` atau `owner_key`, bukan cuma
  `get_current_principal`'s role global. Saat `API_KEYS` kosong (default
  dev), semua principal punya `api_key=""` — jadi semua proyek "dimiliki"
  identitas yang sama, konsisten dengan bagaimana rute lain berperilaku
  saat auth dimatikan, bukan bug baru.
- **Scope sengaja sempit**: `ConversationMessage`/`Document` (files/RAG)
  tidak disentuh sama sekali — Project murni wadah berdiri sendiri untuk
  saat ini, belum terhubung ke chat/file sungguhan (§2/§6 spek memang
  menyisakan ini untuk keputusan lanjutan, bukan kelalaian).
  `ProjectsPage.tsx`: daftar + buat proyek, halaman detail (`/projects/:id`)
  dengan kelola anggota (tambah/hapus, badge role), tombol arsipkan
  (owner-only). Diverifikasi live: buat proyek sungguhan lewat form →
  masuk detail → tambah anggota sungguhan → badge role & tombol hapus
  muncul benar, 0 console error.

**Tahap 14 — Vision, area Phase 3 kedua**

Ditanya lagi ke Boss lewat `AskUserQuestion` (4 area tersisa: Plugin/
Automation/Vision/MCP, semuanya nol kode) — dipilih **Vision**, paling bisa
dibuktikan hidup end-to-end dibanding Automation (butuh desain trigger
dulu), MCP (butuh server eksternal buat verifikasi live), atau Plugin
(murni arsitektur tanpa use-case nyata).

- **`providers.base_provider.GenerationParams` dapat field baru
  `images: tuple[ImageInput, ...] = ()`** (`ImageInput = {data, mime_type}`,
  base64 mentah tanpa prefix `data:`). Field baru dengan default kosong —
  signature `generate()`/`stream()` semua 4 provider **tidak berubah sama
  sekali**, konsisten dengan alasan `GenerationParams` sendiri ada (Bab 7 —
  "single typed object keeps signature stable as new knobs are added").
- **Keempat provider diberi payload gambar sesuai kontrak vendor
  masing-masing** (beda-beda formatnya, semua diverifikasi lewat unit
  test langsung ke method pembangun payload, bukan cuma mock HTTP): Gemini
  → `inline_data` part sejajar `text` part; OpenAI → `content` jadi array
  `[{type:text},{type:image_url}]` (kontrak GPT-4o); Claude → `content`
  array dengan blok `image` SEBELUM blok `text` (konvensi Anthropic);
  Ollama → field `images` (base64 list) diteruskan ke
  `core/ai/gemma_client.py`'s `/api/generate` (pola sama yang sudah dipakai
  `core/chat/engine.py` untuk upload vision-nya sendiri, ditiru bukan
  diduplikasi ulang) — **cache di-skip otomatis saat ada gambar** (gambar
  tak ikut masuk cache key, dan vision jarang jadi cache-hit case yang
  berharga).
- **Jalur gambar dari HTTP sampai provider**: `WorkflowRunRequest.images:
  list[str]` (data: URI, persis output `FileReader.readAsDataURL()` biar
  frontend tak perlu proses ekstra) → `_parse_data_uri()` di route →
  `Orchestrator.run(images=...)` → `Planner.plan(images=...)` **menempel
  ke SEMUA langkah**, bukan cuma role "vision" (semua role provider-agnostic
  by design, Bab 17) → `Task.payload["images"]` (extension point yang
  sudah ada, bukan field baru di `Task`) → `agents/generic_agent.py`
  membongkarnya jadi `GenerationParams.images`.
- **13 test baru** mencakup seluruh rantai: 7 unit test payload per
  provider (`test_providers.py`), 2 unit test agent (Task.payload → params,
  `test_generic_agent.py`), 2 unit test planner (`test_orchestrator.py`),
  2 test integrasi endpoint penuh termasuk parsing data URI rusak
  (`test_orchestrator_api.py`) — satu regresi kena di test provider Ollama
  lama (stub `fake_generate` belum terima kwarg `images` baru), diperbaiki
  di tempat.
- **Diverifikasi live lewat browser** — sengaja pakai role `tool` (Ollama
  lokal, GRATIS) bukan role `vision` (default Gemini, cloud, berbayar) untuk
  pembuktian end-to-end, karena bentuk payload tiap provider cloud sudah
  dibuktikan benar lewat unit test di atas — tak perlu keluar biaya nyata
  cuma untuk mengulang pembuktian yang sama. Upload PNG 1×1 piksel hitam
  sungguhan lewat UI (driver Playwright dapat command `upload` baru) →
  jalankan → **model lokal `gemma4:e2b` benar-benar menjawab "Warna
  dominan pada gambar terlampir adalah hitam"** — bukti pemahaman semantik
  gambar sungguhan, bukan cuma pipa yang jalan tanpa error. 0 console error.

**Tahap 15 — Automation, area Phase 3 ketiga**

Ditanya lagi ke Boss lewat `AskUserQuestion` (3 area tersisa: Plugin/
Automation/MCP) — dipilih **Automation**, karena setelah Vision-nya
Tahap 14 selesai, Automation jadi yang paling murah dibuktikan hidup
end-to-end lewat browser dibanding MCP (butuh server eksternal) atau
Plugin (arsitektur murni tanpa use-case nyata).

- **Entity baru `db.models.ScheduledJob`** — workflow yang dijalankan
  berulang tiap `interval_seconds`, bukan sekali jalan. Trigger sengaja
  interval polos ("tiap N detik"), **bukan sintaks cron** — keputusan
  skop yang didokumentasikan langsung di docstring model, konsisten
  dengan pola "keputusan sadar, bukan keterbatasan" yang sudah dipakai
  di Tahap-tahap sebelumnya. Hard-delete (bukan soft-delete seperti
  `Project`) — alasannya: ini lebih dekat ke "pengaturan" ketimbang data
  organisasi, dan `enabled=False` sudah menutupi kebutuhan "hentikan
  tanpa menghapus".
- **`scheduler/scheduler.py`: `Scheduler` — tick loop in-process**,
  dijalankan langsung lewat `Orchestrator.run()` yang sama dipakai
  `api/routes/orchestrator.py`, **bukan lewat `messaging.TaskQueue`**
  (Bab 23) — keputusan skop, karena belum ada yang mengonsumsi
  `TaskQueue` sama sekali (dikonfirmasi lewat docstring
  `telemetry/monitoring.py`'s `queue_dashboard`: "nothing has started
  publishing to it yet"). `tick()` query `ScheduledJob` yang
  `enabled AND (next_run_at IS NULL OR next_run_at <= now)`, jalankan
  tiap satu lewat `_run_job` (exception di satu job tak menghentikan
  job lain yang due), `run_now(job_id)` untuk trigger manual yang
  **mengabaikan** `next_run_at` (dibuktikan live — lihat di bawah).
  Clock injektabel (`clock: Callable[[], datetime] = datetime.utcnow`),
  pola sama dengan `providers/circuit_breaker.py`.
- **`api/routes/automation.py`** — `_scheduler = Scheduler(_orchestrator)`
  singleton modul, dipasang di `api/main.py` lifespan (`start()`/`stop()`
  mengikuti `ENABLE_SCHEDULER`+`SCHEDULER_TICK_SECONDS` di
  `api/config.py`). CRUD `GET/POST/PATCH/DELETE /api/v1/automation/jobs`
  + `POST .../run-now`, semua discope ke `principal.api_key` sebagai
  `owner_key` (sistem ini tak punya tabel `User` — identitas cuma
  string API key, pola yang sama dipakai `Project.owner_key` di Tahap
  13). `interval_seconds` divalidasi Pydantic `ge=30` (menolak jadwal
  di bawah 30 detik).
- **UI: tab "Terjadwal" di dalam `WorkflowPage.tsx` yang sudah ada**,
  bukan item sidebar baru — `AI_WORKSPACE_ARCHITECTURE.md` §8 eksplisit
  bilang kapabilitas backend baru harus masuk ke salah satu dari 11 area
  tetap, tak boleh menumbuhkan nav baru tiap ada fitur baru. Form jadwal
  memakai peran/pola/prompt yang sama dari tab "Jalankan Sekarang" (state
  dibagi lewat props, bukan store baru). `ScheduledJobList.tsx` murni
  presentational (semua aksi lewat callback), `automationService.ts`
  bicara ke endpoint di atas.
- **15 test baru** (356/356 total): 7 unit `test_scheduler.py`
  (tick jalankan job due, skip job belum due, skip job nonaktif, catat
  gagal tanpa menghentikan job lain, run_now abaikan next_run_at, 404
  job tak dikenal, start/stop idempoten — pakai `FakeClock` + SQLite
  in-memory dengan `AsyncSessionFactory` di-monkeypatch langsung karena
  `Scheduler` tak lewat dependency FastAPI), 8 integrasi
  `test_automation_api.py` (CRUD penuh, job tak terlihat orang lain,
  update menonaktifkan, delete beneran hard-delete, run-now eksekusi
  langsung dan catat hasil, run-now ditolak untuk bukan pemilik, tolak
  interval di bawah minimum).
- **Diverifikasi live lewat browser** (driver Playwright, role `tool`/
  Ollama lokal gratis) — dibuat jadwal "Cek Gamping Otomatis" interval 1
  menit. Log `audit.log` (destinasi stdout/stderr systemd unit ini,
  bukan journalctl) membuktikan **scheduler menjalankan job tiga kali
  tanpa diminta**: sekali otomatis ~20 detik setelah dibuat (tick
  pertama menangkap `next_run_at IS NULL`), sekali lewat klik manual
  "Jalankan Sekarang" (yang terbukti mengabaikan `next_run_at` yang
  belum jatuh tempo — bukti nyata bukan cuma baca kode), dan sekali lagi
  otomatis ~80 detik kemudian tanpa interaksi apa pun — bukti loop
  background benar-benar berjalan sendiri, bukan cuma trigger manual
  yang jalan. Toggle nonaktif/aktif dan hapus job juga diverifikasi,
  semua lewat UI sungguhan dengan Postgres nyata (bukan mock), **0
  console error** di seluruh alur. Job uji dihapus setelah verifikasi
  supaya tidak terus berjalan di server live.

**Tahap 16 — Plugin, area Phase 3 keempat**

Ditanya lagi ke Boss lewat `AskUserQuestion` (2 area tersisa: Plugin/MCP,
keduanya nol kode) — dipilih **Plugin**, karena bisa dibuktikan hidup
end-to-end tanpa dependency Python baru maupun sistem eksternal, sementara
MCP butuh `tools/adapters/mcp.py`+`tool_router.py` yang keduanya belum ada
foldernya sama sekali, dan idealnya butuh MCP server sungguhan untuk
pembuktian live (lebih besar & lebih berisiko untuk pass pertama).

- **Ditemukan lewat riset dulu (bukan diasumsikan)**: dua jalur agent di
  sistem ini berbeda total soal tool-calling. Jalur `orchestrator/`+
  `agents/generic_agent.py` (dipakai Workflow/Vision/Automation) murni LLM
  generation per role — **tidak pernah** mengeksekusi fungsi apa pun,
  "role tool" cuma nama role lewat Model Registry, kebetulan sama namanya
  dengan konsep "tool". Satu-satunya jalur yang benar-benar mengeksekusi
  fungsi selama percakapan LLM adalah **ChatEngine** (`core/chat/`) via
  native tool-calling Ollama, lewat `agent/tools/registry.py` +
  `core/chat/tool_schemas.py`. Jadi Plugin diintegrasikan ke jalur itu —
  ini juga persis pola yang sudah didokumentasikan CLAUDE.md untuk "cara
  menambah tool baru", bukan jalur baru yang diciptakan sendiri.
- **`plugins/base.py`: `PluginInterface`** (Bab 59.1) — kontrak abstrak
  (`execute()`, `manifest()`) yang dilihat Orchestrator/tool registry;
  tak pernah tahu kelas plugin konkret (Dependency Inversion, Bab 4.3).
  **`plugins/weather/`** — plugin nyata pertama, kategori "Weather" (Bab
  59.2: "Data cuaca untuk perencanaan operasi lapangan/tambang/GIS" — cocok
  dengan domain mining/GIS proyek ini): `plugin.py` (WeatherPlugin, panggil
  Open-Meteo — gratis, tanpa API key, jadi Secrets Management Bab 58 tak
  relevan), `config.py` (base URL), `manifest.json` (metadata: nama, versi,
  kapabilitas, `permission_action` — persis struktur Bab 59.3). Panggilan
  HTTP sinkron lewat `urllib` stdlib (bukan `httpx`/`requests` baru) —
  meniru gaya `agent/tools/analyzers.py` di folder yang sama, nol
  dependency baru (Bab 45.3).
- **`registry/plugin_registry.py`** — katalog plugin eksplisit (dict
  statis `{"weather": WeatherPlugin()}`), **bukan** filesystem auto-scan
  (Bab 45.3 — dict eksplisit sama mudahnya ditambah, jauh lebih auditable).
  Status enabled/disabled **in-memory saja** untuk pass pertama ini (pola
  sama dengan HashStore-pluggable-default-in-memory sebelum Tahap 9
  mengaitkan Redis untuk Circuit Breaker) — restart proses mengembalikan
  semua plugin ke enabled, gap yang diakui bukan disembunyikan.
- **Tool baru `plugin_weather`** didaftarkan di `agent/tools/registry.py`
  (strangler pattern, satu baris registrasi tambahan — pola sama dengan
  RBAC pilot Tahap 10) + skema JSON-nya di `core/chat/tool_schemas.py`
  (nama harus cocok, persis aturan yang sudah tertulis di CLAUDE.md).
  Fungsi tool-nya sendiri cek `plugin_registry.get("weather")` dulu — kalau
  dinonaktifkan lewat Settings, tool mengembalikan pesan error alih-alih
  memanggil API, TANPA perlu mengubah `core/chat/engine.py` (fondasi
  terlindungi) sama sekali.
- **`security/permissions.py`** dapat entri baru `TOOL_RISK_ACTIONS["plugin_weather"]
  = "plugin:weather"` (persis pola `write_pdf`, gap yang sama pula: RBAC ini
  cuma aktif kalau caller mengirim role — `/api/v1/agent/run` mengirim,
  `core/chat/` tidak, jadi gate ini inert untuk panggilan dari Chat, sama
  seperti `write_pdf` sejak Tahap 10). Role `operator` diberi izin
  `plugin:weather`. **`manage_plugins`** (dipakai `api/routes/plugins.py`
  untuk gerbang toggle Settings) jadi **pemakai pertama** `require_role()`
  — fungsi dependency FastAPI yang sudah ada sejak Tahap 7 tapi belum
  pernah benar-benar dipasang ke rute manapun.
- **`api/routes/plugins.py`** — `GET /api/v1/plugins` (list, terbuka —
  sama seperti `monitoring.py`/`knowledge.py`), `PATCH /api/v1/plugins/{name}`
  (toggle, digerbang `require_role("manage_plugins")` — hanya role `admin`
  yang punya akses lewat wildcard `"*"`). Tidak ada tabel DB — state
  in-memory di `plugin_registry` cukup untuk pilot pertama ini.
- **UI: section "Plugin" DI DALAM `SettingsPage.tsx` yang sudah ada**,
  bukan area sidebar baru — `AI_WORKSPACE_ARCHITECTURE.md` §8 eksplisit:
  "Area Settings harus memiliki ruang untuk mengaktifkan/menonaktifkan
  kapabilitas tambahan (integrasi baru) tanpa perubahan navigasi inti."
  Card per plugin (nama, badge Aktif/Nonaktif, deskripsi, tombol
  Aktifkan/Nonaktifkan) — pola tombol yang sama dengan `ScheduledJobList`
  Tahap 15, bukan komponen switch baru.
- **16 test baru** (372/372 total): 5 unit `test_plugin_registry.py`
  (list/get/set_enabled/plugin tak dikenal), 3 unit `test_weather_plugin.py`
  (manifest, sukses, gagal jaringan — `_fetch` di-monkeypatch, bukan
  memanggil Open-Meteo sungguhan di CI), 4 unit baru di
  `test_auth_permissions.py` (izin `plugin:weather` per role +
  `require_role("manage_plugins")`), 4 integrasi `test_plugins_api.py`
  (list, toggle ditolak non-admin, toggle diterima admin, 404 plugin tak
  dikenal — tanpa DB sama sekali, murni ASGI client + state in-memory).
- **Diverifikasi live lewat browser DAN panggilan langsung Python** —
  panggilan langsung `WeatherPlugin().execute(latitude=-6.2, longitude=106.8)`
  mengembalikan data cuaca Jakarta sungguhan (25.6°C, 0.0mm hujan,
  2.9 km/jam angin) dari Open-Meteo hidup. **Settings page**: toggle
  Aktifkan/Nonaktifkan plugin weather live, badge berubah benar. **Chat**:
  dikirim "Gunakan tool yang tersedia untuk cek cuaca... lintang -6.2 bujur
  106.8" → model `gemma4:e2b` benar-benar memanggil tool `plugin_weather`
  lewat native tool-calling Ollama → jawaban akhir memuat **angka yang
  identik persis** dengan panggilan Python langsung di atas (25.6°C, 0.0mm,
  2.9 km/jam, kode cuaca 0, sumber open-meteo.com) — bukti tool call
  sungguhan memanggil API eksternal nyata, bukan halusinasi model. 0
  console error di seluruh alur (Settings toggle + Chat tool-call).
  **Gotcha driver Playwright (terulang)**: `type` lalu `press Enter` yang
  dikirim terlalu cepat berturut-turut menyebabkan Enter ter-submit di
  tengah pengetikan (readline driver tidak menunggu promise `type` selesai
  sebelum memproses baris berikutnya) — pesan pertama terpotong jadi
  "Gunakan tool yang tersedia untuk cek cuaca" tanpa koordinat; perbaikan:
  beri jeda ~3 detik antara `type` dan `press Enter` untuk string panjang.

**Tahap 17 — MCP Client, area Phase 3 kelima (terakhir)**

Ditanya lagi ke Boss lewat `AskUserQuestion` — satu-satunya area Phase 3
tersisa. Ditanya juga soal scope: **Client saja** (Recommended, dipilih)
vs **Client + Server**. Client dipilih karena itu use-case utama per Bab 60
sendiri ("client" ditulis duluan, "server" ditulis sebagai "berpotensi"),
dan scope-nya jauh lebih kecil/lebih cepat dibuktikan hidup.

- **Dependency baru: `mcp==1.28.1`** (SDK resmi) — dengan alasan eksplisit
  (Bab 45.3 mengizinkan kalau beralasan): hand-roll protokol JSON-RPC MCP
  dari nol (handshake, session lifecycle, Tool Discovery) berisiko tinggi
  salah dan tak ada manfaatnya dibanding pakai implementasi referensi.
  **Konflik dependency nyata ditemukan+diperbaiki**: `mcp` butuh
  `pydantic>=2.11` (requirements.txt sebelumnya mengunci `2.10.3`) dan
  tidak membatasi versi atas `starlette` (resolver pip menarik starlette
  1.3.1 yang melanggar batas atas FastAPI `<0.42`). Diperbaiki dengan
  menaikkan `pydantic` ke `2.13.4` dan mengunci eksplisit `starlette==0.41.3`
  di requirements.txt — **372 test lama tetap lulus semua** setelah bump,
  dan service live di-restart+dicek `/health/ready` untuk memastikan
  FastAPI/SQLAlchemy/dsb tidak diam-diam rusak oleh transitive upgrade ini.
- **Ditemukan lewat riset dulu (sama seperti Tahap 16)**: karena MCP tools
  cuma bisa benar-benar dieksekusi lewat jalur ChatEngine (bukan
  Orchestrator, lihat temuan Tahap 16), MCP Client dipasang di jalur yang
  sama persis dengan Plugin.
- **`mcp_client/client.py`: `MCPClient`** — pembungkus tipis di atas SDK
  resmi (`stdio_client`+`ClientSession`): `list_tools()` (Tool Discovery,
  Bab 60.1), `call_tool(name, arguments)` (eksekusi, hasil dinormalisasi ke
  dict polos — Bab 60.2: "Hasil dinormalisasi ke ToolResult"). Session
  Management sengaja simpel untuk pass pertama ini: **satu koneksi
  berumur pendek per panggilan** (spawn subprocess → initialize → satu
  aksi → tutup), bukan sesi persisten yang dipertahankan lintas panggilan
  — lebih aman untuk pilot, tapi berarti tiap panggilan membayar biaya
  spawn subprocess baru, gap yang diakui bukan disembunyikan.
- **`mcp_client/config.py`: `MCP_SERVERS`** — dict eksplisit nama server →
  command line yang menjalankannya (bentuk yang sama dengan kebanyakan MCP
  server nyata: `npx @modelcontextprotocol/server-*`, `python -m
  some_server`, dst). Satu entri terkonfigurasi: `"demo"`.
- **`mcp_client/demo_server.py`** — server MCP minimal (`FastMCP`, 2 tool:
  `add`, `reverse_text`) **khusus untuk membuktikan Client bekerja**,
  ditandai eksplisit di docstring sebagai fixture dev/test, BUKAN
  kapabilitas AI_ENGINE yang dikirim ke produksi — dijalankan sebagai
  subprocess lokal (`python -m mcp_client.demo_server`), bukan layanan
  eksternal sungguhan (jadi aman & deterministik dijalankan di CI, sekelas
  dengan test subprocess CLI tool biasa, bukan "live service" yang
  dilarang Bab 12.3).
- **Tool baru `mcp_list_tools`/`mcp_call_tool`** didaftarkan di
  `agent/tools/registry.py` (strangler, pola sama Plugin) + skema di
  `core/chat/tool_schemas.py`. Digerbang **`ENABLE_MCP`** (Bab 57.1 — flag
  standar yang sudah disebut namanya di dokumen sejak awal, baru sekarang
  benar-benar ada kodenya) dicek di dalam fungsi tool saat dipanggil, bukan
  saat registrasi — pola sama dengan cek enabled Plugin.
- **`security/permissions.py`**: `TOOL_RISK_ACTIONS["mcp_call_tool"] =
  "mcp:call"` — Bab 60.1 eksplisit: "Setiap tool yang diekspos via MCP
  tunduk pada validasi... MCP tidak memiliki jalur pintas keamanan." Satu
  action generik menutupi semua server/tool yang mungkin dijangkau lewat
  `mcp_call_tool` — permission granular per-server-per-tool akan prematur
  untuk client yang baru bicara ke satu server (demo) hari ini.
  `mcp_list_tools` (baca-saja, discovery) sengaja tidak digerbang, sama
  seperti `ToolRegistry.list_tools()` internal. Role `operator` diberi
  `mcp:call`.
- **Tidak ada perubahan UI sama sekali** — `AI_WORKSPACE_ARCHITECTURE.md`
  §8 eksplisit: "Kapabilitas baru yang masuk lewat MCP harus tampil
  melalui mekanisme event dan tool generik yang sama (Bab 5), bukan jalur
  UI khusus." MCP muncul secara alami lewat chip tool-call generik Chat
  yang sudah ada, sama seperti tool lain — beda dari Plugin (Tahap 16)
  yang memang butuh toggle di Settings.
- **12 test baru** (384/384 total): 4 unit `test_mcp_client.py` (list
  tools dari demo server sungguhan, call `add`/`reverse_text` dapat hasil
  benar, tool tak dikenal → error), 5 unit `test_mcp_tools_registry.py`
  (round-trip lewat `build_registry()` sungguhan, server tak dikonfigurasi
  → error, `ENABLE_MCP=False` memblokir baik list maupun call), 3 unit baru
  di `test_auth_permissions.py` (izin `mcp:call` per role, `mcp_list_tools`
  tak digerbang).
- **Diverifikasi live lewat Chat sungguhan** — dikirim "Panggil tool add
  di MCP server bernama demo untuk menjumlahkan 42 dan 58" → model
  `gemma4:e2b` benar-benar memanggil `mcp_call_tool(server="demo",
  tool_name="add", arguments={"a":42,"b":58})` lewat native tool-calling →
  Client MCP genuinely melakukan handshake protokol (spawn subprocess,
  `initialize`, `tools/call`) ke server demo → jawaban akhir: **"Hasil
  penjumlahan dari 42 dan 58 adalah 100.0"** — 42+58=100, angka yang
  BENAR secara matematis dan TIDAK mungkin dihasilkan model kecil ini
  sendiri secara andal tanpa benar-benar memanggil tool (model kecil lokal
  terkenal tidak reliable untuk aritmatika) — bukti kuat bahwa protokol
  MCP sungguhan dieksekusi ujung-ke-ujung, bukan halusinasi. 0 console
  error. Service live di-restart dan `/health/ready` dicek dulu sebelum
  verifikasi ini untuk memastikan bump dependency `pydantic`/`starlette`
  di atas tidak diam-diam merusak API yang sedang berjalan.

**Tahap 18 — selesaikan migrasi RBAC (janji ADR-0013)**

Roadmap 8-tahap + Phase 3 sudah tuntas semua; ditanya `AskUserQuestion`
prioritas berikutnya (4 opsi: lanjut RBAC / MCP Server / Dockerfile
multi-stage / pilih dari Bab 68 Backlog) — **lanjut migrasi RBAC**
dipilih, item termurah & risikonya paling rendah karena menggunakan
mekanisme yang sudah terbukti hidup sejak Tahap 10, tinggal menambah
entri.

- **`security/permissions.py`**: `TOOL_RISK_ACTIONS` bertambah dari 1
  entri (`write_pdf`, Tahap 10) jadi 9 — `write_docx`, `write_html`,
  `write_txt`, `write_json`, `write_geojson`, `write_shp`, `convert_geo`,
  `generate_code` semua dapat action `tool:<nama>` sendiri-sendiri, pola
  identik `tool:write_pdf`. Role `operator` diberi akses ke semuanya.
  **Sengaja TIDAK memasukkan tool image** (`image_convert`/`image_resize`/
  dst./`images_to_pdf`) — alasan didokumentasikan di docstring: tool
  gambar mentransformasi file yang sudah ada di disk, bukan menulis
  konten baru dari prompt bebas, profil risiko yang berbeda dari "write
  filesystem" (Bab 30 rule 2). Tool baca (`read_*`, `calculate_area`)
  tetap tak digerbang untuk alasan yang sama seperti `mcp_list_tools`.
  **Nol perubahan** di `agent/tools/registry.py`/`agent/core.py`/
  `core/chat/engine.py` — mekanisme gate (`ToolRegistry.execute(...,
  role=...)`) sudah generik sejak Tahap 10, migrasi ini murni menambah
  baris di dict permission.
- **25 test baru** (409/409 total): parametrized di
  `test_auth_permissions.py` atas 8 tool yang dimigrasi (denied untuk
  `user`, allowed untuk `operator`/`admin` — 24 test) + 1 test yang
  mengonfirmasi tool gambar sengaja tetap ungated.
- **Diverifikasi live** (bukan cuma unit test) — panggilan langsung ke
  `ToolRegistry.execute("write_docx", ..., role=...)` via `build_registry()`
  sungguhan: `role="user"` → `PermissionError` sungguhan; `role="operator"`
  dan `role="admin"` → **file `.docx` sungguhan benar-benar tertulis ke
  `reports/`** (hasil eksekusi punya `filename`/`size`/`type` nyata, bukan
  mock), dihapus setelah verifikasi. Service live di-restart +
  `/health/ready` dicek untuk memastikan tak ada regresi.

**Tahap 19 — Project Workspace & Folder Access (Bab 69, ADR-0005)**

Hand-off satu-kali dari Cowork (`CLAUDE_CODE_PROMPT_WORKSPACE_IMPLEMENTATION.md`,
ditulis di root `D:\01_Project\AI ENGINE`, bukan `docs/`/`audit/`) meminta
implementasi Bab 69 — desain Boss-approved per 6 Juli 2026, belum ada kode
sama sekali. Dikerjakan sebagai kapabilitas aditif murni (Strangler Pattern):
`core/chat/`, `core/document/`, `core/gis/`, `agent/tools/`,
`api/routes/chat.py` tidak disentuh.

**Temuan penting sebelum coding**: Bab 69.11 bilang adapter filesystem
Workspace "memperluas `tools/adapters/filesystem.py` yang sudah ada" — tapi
package `tools/` tidak ada sama sekali di repo ini sebelum Tahap ini
(dikonfirmasi lewat pencarian penuh). Dibuat baru, sejajar
`registry/`/`rag/`/`memory/`/`agent/` (Bab 5) — bukan pelanggaran Bab 45.1
(yang menyebut `agent/tools/` secara spesifik, folder yang sudah sungguh
ada dan tetap tak disentuh). Persis pola drift dokumentasi-vs-kode yang
sudah diperingatkan audit 6 Juli 2026 (F-001/F-003/F-004) — dicatat
eksplisit, bukan ditutupi dengan menafsirkan ulang Bab 69.11 secara paksa.
Detail lengkap keputusan ini ada di `docs/adr/ADR-0014-workspace-implementation.md`
(termasuk catatan disambiguasi: repo kode ini kebetulan **sudah punya**
`ADR-0005-orchestrator-workflow-engine.md`, topik sama sekali berbeda dari
ADR-0005 produk di `ARCHITECTURE_DECISIONS.md` — persis contoh nyata
tabrakan nomor dua seri ADR yang diperingatkan hand-off doc §2).

- **`tools/` (baru)** — `tool_validator.py` (`resolve_within_root`, Root
  Restriction Bab 69.6: menolak `../` dan symlink yang keluar root) +
  `adapters/filesystem.py` (`FilesystemAdapter`: `scan()`/`list_tree()`/
  `read_bytes()`/`read_text()`, Local-only pass ini, klasifikasi file
  document/image/gis/other memakai grup ekstensi yang sama persis dengan
  `agent/tools/registry.py`).
- **`workspace/` (baru, domain module)** — `scanner.py` (agregasi hasil
  scan lintas `WorkspaceFolder`) dan `indexer.py` (membaca file
  document-classified lewat `agent/tools/readers.py` yang sudah ada — bukan
  parser baru — lalu mengindeks ke pipeline RAG yang sama dengan
  `api/routes/knowledge.py`). `workspace/` bergantung ke `tools/`+`rag/`,
  tak pernah ke `api/` (Hexagonal Architecture, Bab 4.2).
- **DB (`db/models.py`)**: `Workspace`/`WorkspaceFolder` persis skema
  `PROJECT_SPECIFICATION.md` §7.1, dengan satu deviasi terdokumentasi:
  soft-delete lewat `deleted_at` terpisah (bukan memperluas enum `status`
  yang eksplisit 4-nilai tertutup — Active/Scanning/Indexing/Error — di
  spesifikasi), beda dari pola `Project.status="archived"`.
- **RBAC (`security/permissions.py`)**: Workspace Permission (Bab 69.7)
  **resource-scoped lewat Project role**, bukan entri global baru di
  `_ROLE_PERMISSIONS`/`TOOL_RISK_ACTIONS` — `WORKSPACE_PERMISSIONS_BY_PROJECT_ROLE`
  memetakan owner/editor → akses penuh, viewer → read-only, karena Workspace
  selalu bagian dari satu Project (Bab 69.11), bukan aksi sistem-lebar.
  Setiap route mutasi (`create`/`patch`/`delete`/`mount`/`scan`/`index`)
  digerbang lewat satu action `"admin"` — keputusan disengaja, didokumentasikan
  di `api/routes/workspace.py` docstring (Bab 69.7 tidak merinci pemetaan
  8 action ke masing-masing endpoint; 7 action granular lain disiapkan
  untuk lapisan Agent-content-access masa depan, Bab 69.5).
- **API (`api/routes/workspace.py`, baru)** — memformalkan rancangan Bab
  69.13 jadi bentuk RESTful `/workspace/{id}/mount|scan|index|files|tree|status`
  (id eksplisit di path, bukan sketsa datar Bab 69.13 yang cuma valid untuk
  1 Workspace sistem-lebar). `POST .../mount` menolak eksplisit
  `source_type` selain `Local` (pesan "roadmap", Bab 69.16) dan path yang
  tidak ada di disk. Root Restriction ditegakkan **per-`WorkspaceFolder`**,
  bukan satu "Workspace Root" tunggal — `Workspace.root_path` murni field
  tampilan (Bab 69.14 "Workspace Path"), diisi otomatis dari folder pertama
  yang di-mount.
- **RAG (Bab 69.10)** — `POST .../index` memakai ulang **instance**
  `_retriever` singleton `api/routes/knowledge.py` (bukan cuma nama
  namespace yang sama). Ini bug nyata yang ditemukan lewat test, bukan
  cuma isu hermetisitas: dengan `VECTOR_BACKEND=memory` (default dev/CI),
  dua `Retriever` yang dibangun terpisah membungkus `InMemoryKnowledgeStore`
  berbeda dan tidak saling melihat data — berbagi instance yang sama
  membuat "Workspace Folder adalah Source RAG resmi" benar-benar berlaku
  ujung-ke-ujung, bukan cuma kebetulan berfungsi saat pakai pgvector.
- **F-003 diselesaikan** (bukan edit `docs/`/`audit/`, murni keputusan
  implementasi): Uploaded Files tetap mekanisme `Document`/upload yang
  sudah ada, tidak berubah sama sekali; Workspace Files (`GET .../files`)
  adalah konsep aditif baru dari `WorkspaceFolder`, bukan tabel gabungan.
- **F-004**: `Workspace`/`WorkspaceFolder` kini punya skema nyata — rujukan
  konkret untuk Boss saat memperbarui `MASTER_INSTRUCTION.md` Bab 4.4.
- **Frontend (`web/`)** — `types/workspace.ts`, `services/workspaceService.ts`,
  `stores/workspaceStore.ts` (thin, pola sama seperti `projectStore.ts`),
  `pages/projects/WorkspacePage.tsx` (field persis Bab 69.14: Workspace
  Path, Folder List, Status, Last Scan, Document/Image/GIS Count, Vector
  Status, Knowledge Status, Storage Used, Index Status). Rute baru
  `/projects/:projectId/workspace`, tombol "Workspace" ditambahkan di
  `ProjectDetailView` — **tidak** ada item sidebar baru berdiri sendiri
  (Bab 69.14/`AI_WORKSPACE_ARCHITECTURE.md` §8, pola yang sama sejak Tahap
  15/16). `npm run lint`/`npm run build` hijau.
- **Monitoring (`telemetry/monitoring.py` + `api/routes/monitoring.py`)** —
  `workspace_dashboard()` baru: jumlah Workspace, Workspace aktif per
  status, agregat Document/Image/GIS Count, total storage. Berbeda dari
  dashboard lain di modul ini (baca state in-memory `Orchestrator`),
  dashboard ini DB-backed dan **live re-scan** filesystem tiap dipanggil —
  tidak ada cache counts persisten di `Workspace`/`WorkspaceFolder` (gap
  yang diakui, kandidat Bab 68 Prioritas 23 Incremental Index masa depan).
  Folder yang tak terakses (mis. NAS mati) dilaporkan di `errors`, tidak
  menggagalkan seluruh dashboard.
- **65 test baru** (474/474 total, naik dari 409): 17
  `test_filesystem_adapter.py` (Root Restriction termasuk symlink escape),
  2 `test_workspace_scanner.py`, 3 `test_workspace_indexer.py`, 16 integrasi
  `test_workspace_api.py` (CRUD, RBAC per role, mount/scan/index/files/
  tree/status, soft-delete), 23 Workspace Permission di
  `test_auth_permissions.py`, 4 `workspace_dashboard` di
  `test_monitoring.py`.
- **Diverifikasi live sungguhan** (bukan cuma unit test) — service systemd
  (`ai-engine.service`, port 8001) di-restart untuk memuat kode baru +
  tabel DB baru (auto-created via `init_db()` ke Postgres sungguhan);
  folder scratch nyata dibuat berisi 1 dokumen (`.txt`), 1 gambar (`.png`),
  1 file GIS (`.geojson`) → `POST /workspace` → `POST /mount` folder
  sungguhan → `POST /scan` (hasil: document=1/image=1/gis=1, persis jumlah
  file asli) → `POST /index` (1 chunk) → `GET /api/v1/knowledge/search`
  **sungguhan menemukan** isi file (skor 0.70, metadata `source=workspace`
  + `workspace_id` yang benar) lewat backend pgvector sungguhan, bukan
  mock. Root Restriction diverifikasi: mount path yang tidak ada di disk →
  400; `source_type=Network` → 400 pesan roadmap. Workspace+Project test
  di-soft-delete setelah verifikasi, folder scratch dihapus. **Tidak** ada
  interactive browser drive (tidak ada Playwright/Cypress di repo ini) —
  gap yang diakui eksplisit, bukan disamarkan, posisi sama seperti Tahap 14
  (Vision) mengakui belum diverifikasi ke provider cloud sungguhan.
- **Gap yang diakui** (Bab 69.16, scope-sempit-sadar): Network/Server/
  Cloud/SharePoint/OneDrive/GDrive/S3 folder source belum ada adapternya —
  `mount` menolak eksplisit, bukan diam-diam menerima. `core/chat/engine.py`
  (folder fondasi) belum workspace-aware — Agent Workspace Context (Bab
  69.5) baru ada di sisi backend/API, belum ada tool Chat yang membaca dari
  Workspace. Tidak ada cache counts persisten (tiap panggilan dashboard/
  status re-scan filesystem). Auto Sync/Live File Watcher/Incremental
  Index/Versioning/Snapshot/Multi Workspace/Remote Workspace/Collaboration/
  Workspace Permission Management UI granular — semua Backlog Prioritas
  21-29, tidak disentuh sama sekali.

**Tahap 20 — Sambungkan RBAC ke ChatEngine**

Ditanya `AskUserQuestion` prioritas berikutnya (MCP Server vs sambungkan
RBAC ke ChatEngine) — **RBAC ke ChatEngine** dipilih: lebih murah, menutup
gap yang diakui berulang sejak Tahap 10/16/17/18 ("`core/chat/engine.py`
sama sekali belum tersambung ke RBAC... satu-satunya jalur yang benar
eksekusi tool untuk plugin/MCP"), tanpa dependency baru.

**Temuan sebelum coding**: frontend sudah mengirim yang dibutuhkan —
`web/src/services/apiClient.ts`'s `raw()` (dipakai `chatService.ts`) sudah
melampirkan `X-API-Key` dari `settingsStore` ke setiap request chat,
mekanisme yang sama dipakai `projectService`/`workspaceService`.
`security/auth.py::get_current_principal` (Tahap 7, ADR-0010) sudah siap
pakai, cuma belum pernah di-opt-in `api/routes/chat.py`. **Perubahan ini
murni backend** — nol perubahan frontend.

- **`core/chat/engine.py` (folder fondasi, perubahan aditif murni)**:
  `stream_run()` dapat parameter opsional `role: str | None = None`,
  diteruskan ke `_run_tool()` (loop tool-calling utama) dan `_fallback()` —
  yang pada gilirannya memanggil `registry.execute(name, args, role)`,
  gerbang generik yang sama persis dipakai `agent/core.py` sejak Tahap 10.
  **Nol perubahan** ke `agent/tools/registry.py`/`security/permissions.py`.
  `role=None` (setiap pemanggil yang belum opt-in) berperilaku identik
  sebelum Tahap ini — `ToolRegistry.execute()` cuma memeriksa izin kalau
  `role is not None`.
- **Penolakan izin jadi hasil tool biasa, bukan stream yang crash** —
  sebelumnya `PermissionError` dari `registry.execute()` akan lolos dari
  `_run_tool()` tanpa ditangkap dan kena `except Exception` di
  `stream_run()`, mengakhiri SELURUH stream SSE dengan event `error`
  generik (bukan cuma satu panggilan tool itu). Sekarang `_run_tool()`
  menangkap `PermissionError` dan mengembalikan
  `{"error": f"Akses ditolak: {e}", "success": False}` — memakai ulang
  bentuk hasil error yang SUDAH ADA (`_summarize_result`/perhitungan `ok`
  sudah menangani `"error"` di dict), jadi model melihatnya sebagai
  kegagalan tool biasa dan bisa menyampaikan ke pengguna, percakapan tetap
  lanjut. Nol event baru, nol perubahan protokol untuk `web/app.js`/React UI.
- **`api/routes/chat.py`**: `stream()` opt-in `Depends(get_current_principal)`,
  meneruskan `role=principal.role` ke `chat_engine.stream_run()`. Endpoint
  lain (`/upload`, `/download`, `/sessions*`, `/models`) tidak disentuh —
  tidak mengeksekusi tool, konsisten pola RBAC-hanya-di-titik-yang-berubah-
  perilaku yang sudah dipakai di seluruh app.
- **Keputusan sadar di luar cakupan**: kepemilikan sesi (`session_id`) tetap
  tidak terikat identitas — siapa pun yang tahu `session_id` orang lain
  masih bisa mengaksesnya, sama seperti sebelum Tahap ini. Tahap ini HANYA
  menutup gerbang panggilan-tool, bukan kontrol akses sesi — dicatat
  eksplisit sebagai gap terpisah yang tetap terbuka, bukan tak sengaja
  terlewat.
- **7 test baru** (481/481 total, naik dari 474; `core/chat/` sebelumnya nol test sama
  sekali): 4 unit `test_chat_engine_rbac.py` (mock `httpx.AsyncClient.stream`
  + fake `ToolRegistry` minimal — pola sama `test_tool_registry_rbac.py`,
  bukan `build_registry()` sungguhan supaya tak menyeret GIS/image/Ollama
  analyzer nyata) — ditolak untuk `user`, diizinkan untuk `operator`/`admin`,
  tak berubah untuk `role=None`; 3 integrasi `test_chat_api_rbac.py` (HTTP
  penuh lewat `api.main.app`, `X-API-Key` sungguhan → role → gerbang, plus
  401 saat `API_KEYS` diset tapi key tak dikirim).
- **Bug pra-ada ditemukan+diperbaiki saat menulis test, bukan regresi baru**:
  `tests/integration/test_workspace_api.py`'s isolasi RAG (`_hermetic_rag`)
  cuma memonkeypatch `settings`, bukan singleton `_retriever` — cukup
  waktu ditulis (Tahap 19) karena `workspace/indexer.py` saat itu membangun
  `Retriever` baru tiap panggilan. Sejak `api/routes/workspace.py` diubah
  Tahap 19 untuk memakai ulang instance `_retriever` milik
  `api/routes/knowledge.py` (perbaikan bug lain), isolasi lama jadi rapuh
  tergantung urutan koleksi test se-sesi penuh (`api.routes.knowledge`
  cuma diimpor SEKALI per proses, `_retriever` dibangun saat itu dengan
  backend apa pun yang aktif — persis pola pra-ada yang sudah didiagnosis
  `test_knowledge_api.py`, satu tingkat lebih dalam karena
  `api.routes.workspace` mengimpor `_retriever` via `from ... import ... as ...`,
  *binding nama* yang tak ikut berubah kalau `api.routes.knowledge._retriever`
  di-monkeypatch belakangan). **Fix**: monkeypatch KEDUA binding
  (`api.routes.knowledge._retriever` DAN `api.routes.workspace._knowledge_retriever`)
  ke instance `Retriever`+`InMemoryKnowledgeStore` yang SAMA. Diverifikasi:
  suite penuh lulus 3x berturut-turut (sebelumnya intermiten gagal
  tergantung urutan file test).
- **Diverifikasi live sungguhan lewat model asli** (bukan cuma unit test):
  `API_KEYS` sementara diisi di `.env` (`userkey:user,opkey:operator`),
  service di-restart. `role=user` → `gemma4:e2b` BENAR memanggil
  `write_txt` lewat tool-calling asli → `PermissionError` sungguhan
  (`role 'user' lacks permission 'tool:write_txt'`) → model sendiri
  menyusun penjelasan Bahasa Indonesia ke pengguna bahwa permintaan
  ditolak karena izin, stream selesai normal (`done`), **tidak ada file
  tertulis**. `role=operator` (prompt identik) → tool sukses, **file
  `.txt` sungguhan tertulis ke `reports/`** dengan isi persis diminta.
  Tanpa header `X-API-Key` sama sekali setelah `.env` dikembalikan ke
  kondisi semula (tanpa `API_KEYS`) → perilaku default admin-bypass tetap
  identik seperti sebelum Tahap ini (nol regresi ke alur dev normal).
  `.env` dikembalikan persis (diff kosong terhadap backup), service
  di-restart lagi.

**Tahap 21 — Dockerfile multi-stage (Bab 37 rule 2, ADR-0009 follow-up)**

Dipilih lewat `AskUserQuestion` dari 3 kandidat (MCP Server / kepemilikan
sesi Chat / Dockerfile multi-stage). Gap ini dicatat sejak ADR-0011:
`docker/Dockerfile.api`/`Dockerfile.worker` menginstal `gcc`/`libpq-dev`/
`libgdal-dev` (compiler + dev headers, cuma perlu untuk build wheel
asyncpg/psycopg2/fiona/shapely/pyproj) langsung ke image final, single-stage.

- **Kedua Dockerfile dipecah jadi 2 stage**: `builder` (apt build-tools
  lengkap + `python -m venv /opt/venv` + `pip install`) dan runtime
  (`COPY --from=builder /opt/venv /opt/venv` saja, tanpa compiler/dev
  headers sama sekali).
- **Temuan tak terduga saat verifikasi, bukan bagian rencana awal**:
  dicek `du` dulu sebelum ubah apa pun — **tidak ada `.dockerignore` sama
  sekali di repo ini**. `COPY . .` diam-diam membawa `venv/` host (338MB,
  sepenuhnya redundan — image build venv sendiri), `web/node_modules/`
  (277MB, tak relevan buat backend Python), DAN **`.env` sungguhan berisi
  API key OpenAI/Anthropic/Google asli** langsung ke filesystem image —
  dikonfirmasi nyata lewat `docker run --rm ai_engine-api python3 -c
  "open('/app/.env').read()"` sebelum diperbaiki, bukan cuma dugaan.
  **Ini temuan keamanan nyata** (siapa pun dengan akses image/registry bisa
  ekstrak `.env` dan dapat kredensial produksi), bukan cuma soal ukuran
  image — `.dockerignore` baru dibuat, mengecualikan `.env`/`.env.*`,
  `venv/`, `web/node_modules/`/`web/src/`/`web/tests/` (BUKAN `web/dist/` —
  itu yang benar-benar disajikan `api/main.py` saat runtime, diverifikasi
  masih ada di image setelah exclude), `.git/`, `docs/`, `k8s/`,
  `backups/`, `audit.log`/`*.log`, `uploads/`/`reports/` (sudah
  volume-mounted di compose, baking salinan basi cuma buang tempat).
- **Bug nyata ketemu lewat verifikasi live, persis pola insiden ADR-0009
  yang jadi alasan tugas ini diminta** — setelah `libgdal-dev` dibuang dari
  stage runtime, `import fiona` gagal:
  `ImportError: libexpat.so.1: cannot open shared object file`.
  `libgdal-dev` dulu menarik `libexpat1` secara transitif lewat apt
  (dependency tersembunyi), dan wheel fiona (walau membundel
  GDAL/GEOS/PROJ sendiri lewat auditwheel) TERNYATA tidak membundel
  `libexpat`. **Fix**: tambah `libexpat1` (paket runtime, bukan `-dev`) ke
  kedua Dockerfile. Diverifikasi ulang setelah fix: `fiona`/`shapely`/
  `pyproj` impor + baca file GeoJSON sungguhan berhasil di dalam container.
- **Hasil ukuran image**: `ai_engine-api`/`worker_ai`/`worker_gis` turun
  dari **2.83GB → 699MB** (~75%, gabungan multi-stage + `.dockerignore` —
  mayoritas justru dari `.dockerignore` menyingkirkan `venv`/`node_modules`
  yang sebelumnya ikut ter-copy, bukan cuma dari memisah compiler).
- **Diverifikasi live penuh** (bukan cuma review kode, sesuai permintaan
  eksplisit mengingat riwayat ADR-0009): `docker compose build --no-cache`
  ketiga image → `docker compose up -d` → `docker compose ps` ketiganya
  `Up`, nol crash-loop di log `worker_ai`/`worker_gis` → `GET
  /health/ready` sungguhan 200 (database/redis/ollama/openai/claude/gemini
  semua `ok`) → **`POST /api/v1/gis/area/calculate` sungguhan lewat HTTP**
  menghitung luas poligon nyata (123.19 Ha, centroid, bbox benar) →
  **`pytest -q tests/unit` dijalankan DI DALAM container** sungguhan,
  412/412 lulus → dikonfirmasi `.env`/`venv`/`web/node_modules` sudah
  GONE dari image sementara `web/dist/index.html` (dibutuhkan runtime)
  tetap PRESENT.
- **Gap yang diakui**: `docker/Dockerfile.postgres` tidak disentuh (sudah
  berbasis image `postgis/postgis` yang cuma menambah satu paket apk +
  copy file, bukan pola build-lalu-strip yang sama relevan). Belum ada
  `HEALTHCHECK` instruction eksplisit di `Dockerfile.api`/`Dockerfile.worker`
  sendiri (docker-compose.yml cuma mendefinisikannya untuk
  postgres/redis) — di luar cakupan tugas ini, dicatat sebagai kandidat
  terpisah. `pytesseract` (OCR) di `requirements.txt` menyebut butuh
  binary `tesseract` di host, tapi `tesseract-ocr` TIDAK PERNAH diinstal
  di Dockerfile manapun (gap pra-ada, ditemukan tak sengaja saat audit
  dependency runtime, bukan regresi Tahap ini — OCR lewat `read_image`
  kemungkinan sudah gagal senyap di Docker sejak awal, di luar cakupan
  untuk diperbaiki sekarang).

**Tahap 22 — Kepemilikan sesi Chat**

Dipilih lewat `AskUserQuestion` dari 4 kandidat (MCP Server / loose ends
Docker / kepemilikan sesi Chat / Agent Workspace Context). Menutup gap
yang Tahap 20 catat eksplisit sebagai di luar cakupan: `session_id`
ChatEngine tidak pernah terikat identitas — siapa pun yang tahu ID sesi
orang lain bisa membaca riwayatnya, melanjutkannya, atau menghapusnya.

- **`core/chat/engine.py` (folder fondasi, aditif murni)**: `Session` dapat
  atribut `owner` (string `Principal.api_key`, diisi sekali saat sesi
  pertama dibuat, tidak pernah berubah setelahnya — first-touch-owns,
  bukan re-assignable). `get_session()`/`stream_run()` dapat parameter
  opsional `owner=None`; `list_sessions()` dapat parameter opsional
  `owner=None` yang jika diisi memfilter cuma sesi milik pemanggil itu.
  **Nol pengecekan otorisasi di dalam `engine.py` sendiri** — sama seperti
  pola `api/routes/workspace.py` (domain/engine tetap agnostik terhadap
  HTTP, rute yang memutuskan boleh/tidak).
- **`api/routes/chat.py`**: helper `_require_session_owner()` dipanggil di
  awal setiap rute yang menyentuh `session_id` (`/upload`, `/stream`,
  `GET`/`DELETE /sessions/{id}`) — 403 sebelum kerja apa pun dimulai,
  BUKAN di dalam `event_source()` (raise di situ setelah
  `StreamingResponse` mulai jalan cuma akan jadi body 200 yang rusak
  separuh jalan, bukan 403 bersih). `GET /sessions` (list) kini memfilter
  ke `owner=principal.api_key` — dulu mengembalikan SEMUA sesi ke SIAPA
  PUN yang memanggil.
- **Perilaku default dev (`API_KEYS` kosong) tidak berubah sama sekali** —
  setiap pemanggil berbagi `Principal(api_key="", role="admin")` yang
  identik, jadi setiap sesi ber-owner `""` yang sama, pengecekan
  kepemilikan jadi no-op total. Pola yang sama persis dipakai setiap fitur
  RBAC lain di app ini (Tahap 10/16/17/18/20).
- **`/download/{filename}` sengaja TIDAK disentuh** — endpoint itu tidak
  punya `session_id` dalam request sama sekali (file diambil lewat nama
  file langsung dari `reports/`), jadi ini gap terpisah (file mana milik
  sesi mana), bukan bagian dari kepemilikan sesi. Dicatat eksplisit, tidak
  digabung diam-diam ke lingkup Tahap ini.
- **8 test baru** (489/489 total): integrasi `test_chat_session_ownership.py`
  — pemilik bisa baca/hapus sesi sendiri, orang lain ditolak baca/lanjut/
  hapus (403 di ketiganya), upload ke sesi orang lain ditolak, daftar sesi
  cuma tampilkan milik sendiri, dan perilaku tanpa `API_KEYS` sama sekali
  tak berubah.
- **Diverifikasi live sungguhan** (`API_KEYS` sementara di `.env`, service
  di-restart, model asli): User A kirim pesan sungguhan lewat `gemma4:e2b`,
  dapat `session_id` nyata. User A baca sesi sendiri → 200 riwayat lengkap.
  **User B (`X-API-Key` berbeda) coba baca sesi User A → 403 sungguhan**
  (`"Sesi ini milik pengguna lain"`); coba hapus → 403, dikonfirmasi sesi
  User A TETAP UTUH (2 entri riwayat, tak terhapus); coba lanjutkan lewat
  `/stream` dengan `session_id` User A → 403 (ditolak sebelum model
  sempat dipanggil sama sekali); `GET /sessions` sebagai User B → daftar
  kosong, tak melihat sesi User A. Setelah `.env` dikembalikan (tanpa
  `API_KEYS`) dan service di-restart: kirim pesan tanpa header `X-API-Key`
  sama sekali → sesi bisa dibaca tanpa auth, persis perilaku sebelum
  Tahap ini (nol regresi ke alur dev normal).

**Tahap 23 — Agent Workspace Context ke ChatEngine (Bab 69.5)**

Dipilih lewat `AskUserQuestion` dari 4 kandidat (MCP Server / kepemilikan
file download / Agent Workspace Context / loose ends Docker). Menutup gap
yang dicatat sejak Tahap 19: Project Workspace dibangun penuh di
backend/API tapi `core/chat/engine.py` tak pernah punya cara membacanya —
Chat cuma tahu Uploaded Files.

- **RBAC dicek SEKALI per HTTP request di rute, bukan per panggilan tool**
  — `ChatRequest.workspace_id` baru; kalau diisi, `api/routes/chat.py`
  meresolusi role Project pemanggil (pakai ulang `_role_for` milik
  `projects.py`, helper yang sama dipakai `workspace.py`) dan mewajibkan
  `require_workspace_permission(role, "read")` — 403 SEBELUM
  `StreamingResponse` dikembalikan (alasan sama seperti Tahap 22: raise di
  dalam generator SSE cuma jadi body 200 rusak). Pendekatan cek-di-tiap-
  panggilan-tool dipertimbangkan lalu ditolak: itu berarti `agent/tools/`
  harus mengimpor dari `api/routes/`, arah dependensi yang salah (lihat
  aturan yang sama di docstring `workspace/indexer.py`). Trade-off yang
  diterima & didokumentasikan: kalau frontend terus mengirim ulang
  `workspace_id` tiap pesan (hal wajar untuk UI yang menampilkan "terhubung
  ke Project X"), cek berjalan ulang tiap pesan; kalau tidak, nilai yang
  sudah terikat di sesi dipercaya untuk sisa sesi itu — pola kepercayaan
  yang sama dipakai kepemilikan sesi (Tahap 22). Tidak ada
  `Depends(get_session)` di rute ini — sesi DB dibuka manual, cuma di
  dalam cabang `if req.workspace_id`, supaya chat biasa yang tak pakai
  Workspace tidak menanggung round-trip DB tambahan.
- **`core/chat/engine.py` (folder fondasi, aditif murni)**: `Session` dapat
  `workspace_id`, pola first-non-null-wins sama seperti `owner`. Model
  TIDAK PERNAH boleh memberi `workspace_id` sendiri — `_run_tool`
  menyuntikkan `session.workspace_id`, menimpa apa pun yang disodorkan
  model. Inilah batas keamanan sesungguhnya (mencegah ID yang dihalusinasi
  atau hasil prompt injection menjangkau Workspace yang tak diotorisasi
  untuk sesi ini) — pola yang sama seperti `_run_tool` sudah menormalkan
  `file_path`/`path`/`source` lewat `resolve_path`, cuma satu kasus
  sanitasi argumen lagi. `SYSTEM_PROMPT` + `_build_user_message` dapat
  catatan singkat saat `workspace_id` terikat, supaya model tak lupa
  sepanjang percakapan.
- **Dua tool baru, sync wrapper di atas kerja DB/file async** — pola PERSIS
  `mcp_list_tools`/`mcp_call_tool` (Tahap 17): `workspace_list_files()`
  (nol argumen dari model) dan `workspace_read_file(folder_id,
  relative_path)` (baca teks dokumen — pdf/txt/docx/csv/json, kategori
  yang sama dipakai indexer Tahap 19; gambar/GIS di Workspace sengaja
  BELUM disentuh, itu baris "Vision" Bab 69.5, integrasi terpisah karena
  hasil tool hari ini teks JSON bukan input vision). File baru
  `agent/tools/workspace_reader.py` (sejajar `readers.py`/`writers.py`/
  `gis_io.py`/`images.py`) — `agent/tools/registry.py` sendiri cuma dapat
  satu import + dua `registry.register(...)`, pola yang sama dipakai
  Plugin/MCP Tahap 16/17. `extract_text` di `workspace/indexer.py`
  dipromosikan dari privat (`_extract_text`) jadi publik supaya dipakai
  ulang, bukan diimplementasi ulang ketiga kalinya. Ungated di
  `TOOL_RISK_ACTIONS` — read-only, postur sama seperti `read_*`/
  `mcp_list_tools`; gerbang sungguhan sudah terjadi sekali di rute.
- **Bug nyata ketemu lewat verifikasi live sungguhan, bukan asumsi
  dari desain** — percobaan live PERTAMA gagal dengan
  `Future ... attached to a different loop` dari Postgres asli.
  Akar masalah: `db.connection.AsyncSessionFactory` (engine global,
  dibangun sekali di event loop utama uvicorn) TIDAK BISA dipakai ulang
  dari dalam `asyncio.run()` yang dijalankan `_run_tool`'s
  `asyncio.to_thread` — thread baru itu bikin event loop BARU, dan koneksi
  asyncpg terikat ke loop tempat ia dibuat. Pola `asyncio.run()`-di-dalam-
  `asyncio.to_thread` yang sama dipakai `mcp_list_tools` AMAN untuk MCP
  (semua state dibuat baru tiap panggilan) tapi TIDAK aman untuk resource
  async yang sudah ada sebelumnya seperti connection pool global. **Fix**:
  `workspace_list_files`/`workspace_read_file` membangun engine BARU dari
  `settings.DATABASE_URL` tiap panggilan (dibuang setelah), bukan memakai
  ulang factory global — `_list_files`/`_read_file` sendiri tetap punya
  default ke factory global untuk pemanggil di loop yang sama (mis. test).
- **Sengaja TIDAK disentuh**: `/api/v1/chat/download/{filename}` (gap
  terpisah dari Tahap 22, belum ditutup); Workspace gambar/GIS lewat Chat
  (baris Vision Bab 69.5, integrasi lebih besar, follow-up terpisah).
- **15 test baru** (504/504 total, stabil 2x berturut-turut): 8 unit
  `test_workspace_reader.py` (baca sungguhan, workspace/folder tak
  ditemukan, ekstensi tak didukung, source_type non-Local, plumbing
  sync-wrapper via `asyncio.run`), 5 unit
  `test_chat_engine_workspace_context.py` (`_run_tool` menimpa
  `workspace_id` palsu dari model, error "belum terhubung" tanpa
  `workspace_id`, `stream_run` mempertahankan ikatan lintas pesan), 2
  integrasi `test_chat_workspace_context_api.py` — REGISTRY SUNGGUHAN
  (bukan fake), Project+Workspace+folder sungguhan (sqlite berbasis file,
  bukan `:memory:`, persis alasan yang sama dengan bug cross-loop di
  atas), model palsu memanggil `workspace_list_files` lalu
  `workspace_read_file` dengan `workspace_id` PALSU sengaja disisipkan di
  argumen tool call → dikonfirmasi tetap berhasil (bukti penimpaan
  bekerja), plus non-anggota Project ditolak 403 sebelum streaming mulai.
- **Diverifikasi live sungguhan lewat model asli** (dua putaran, putaran
  pertama menemukan bug cross-loop di atas, putaran kedua setelah fix):
  Project+Workspace+folder sungguhan dibuat via API, folder berisi file
  `.txt` dengan fakta unik (kadar Cu 1.85%, Ag 45 g/t). Ditanya lewat
  `/api/v1/chat/stream` dengan `workspace_id` terikat — `gemma4:e2b` BENAR
  memanggil `workspace_list_files` lalu `workspace_read_file` dengan
  `folder_id`/`relative_path` yang diambil TEPAT dari hasil panggilan
  pertama, jawaban akhir mengutip **1.85% dan 45 g/t PERSIS** dari isi
  file sungguhan (bukan halusinasi). RBAC live: `API_KEYS` sementara
  diisi, pemilik Project baru → chat dengan `workspace_id` itu sukses
  (200); "stranger" (bukan anggota Project) → 403 sungguhan
  (`"project role None lacks workspace permission 'read'"`) SEBELUM
  streaming dimulai. `.env` dikembalikan persis, service di-restart,
  folder scratch + Project/Workspace test dihapus (satu baris tersisa
  soft-deleted+yatim dari sesi RBAC sementara — tak berbahaya, konsisten
  dengan pola pembersihan Tahap-Tahap sebelumnya).

**Tahap 24 — Kepemilikan file download Chat**

Dipilih lewat `AskUserQuestion` dari 4 kandidat (kepemilikan file
download / loose ends Docker / MCP Server / Bab 68 Backlog). Menutup gap
yang dicatat eksplisit sejak Tahap 22/23: `/api/v1/chat/download/{filename}`
tak punya konsep sesi sama sekali — siapa pun yang tahu nama file bisa
mengunduh apa pun di `reports/`.

- **Temuan penting SEBELUM coding, mengubah cakupan**: `GET
  /reports/{filename}` (`api/routes/files.py`, rute lain, lebih lama,
  menyajikan folder yang SAMA PERSIS) sudah terbuka penuh tanpa autentikasi
  apa pun sejak awal — mengunci `chat.py` saja TIDAK menutup celah
  sesungguhnya, siapa pun tetap bisa ambil file yang sama lewat rute itu.
  Ditanya `AskUserQuestion`: perluas cakupan ke `files.py` sekalian, atau
  tetap sempit + catat gap lebih luas sebagai prioritas terpisah — **tetap
  sempit** dipilih (konsisten pola Tahap demi Tahap yang sudah dipakai
  sesi ini: satu gap tertutup, bukti hidup, bukan mencoba menutup semuanya
  sekaligus). Dicatat eksplisit sebagai prioritas baru di bawah, BUKAN
  disembunyikan.
- **`core/chat/engine.py` (folder fondasi, aditif murni)**: `Session` dapat
  `produced_files: set[str]` — basename tiap file yang BENAR-BENAR
  dihasilkan tool di sesi itu (diisi di loop tool-calling utama maupun
  `_fallback`, dua tempat yang sama sebelumnya cuma isi `session.history`
  tanpa menyimpan daftar terpisah untuk dicek kepemilikan).
- **`api/routes/chat.py`**: `/download/{filename}` sekarang wajib
  `session_id` (query param) — perubahan kontrak API yang disengaja (dulu
  `filename` saja sudah cukup). Memakai ulang `_require_session_owner`
  (Tahap 22) PLUS cek baru: `filename` harus ada di
  `session.produced_files` milik `session_id` itu — bukan cuma "kamu
  pemilik sesi ini", tapi juga "file ini memang lahir dari sesi ini", jadi
  pemilik sesi A tidak bisa menebak nama file dari sesi B miliknya sendiri
  yang lain dan mengunduhnya lewat sesi A.
- **6 test baru** (510/510 total, stabil 2x berturut-turut):
  `test_chat_download_ownership.py` — pemilik unduh sukses, orang lain
  ditolak 403 walau tahu `session_id` yang benar, nama file yang tak
  pernah dihasilkan di sesi itu → 404, sesi tak dikenal → 404, `session_id`
  hilang → 422 validasi FastAPI, dan perilaku tanpa `API_KEYS` tak berubah.
- **Diverifikasi live sungguhan**: `API_KEYS` sementara diisi, User A minta
  `gemma4:e2b` membuat file sungguhan lewat `write_txt` (role `operator`,
  bukan `user` — `write_txt` digerbang RBAC Tahap 20, dipilih role yang
  benar-benar bisa menulis). User A unduh file sendiri → 200 isi persis.
  **User B pakai `session_id` User A → 403 sungguhan**
  (`"Sesi ini milik pengguna lain"`). User A minta nama file yang tak
  pernah dibuat di sesi itu → 404. Tanpa `session_id` sama sekali → 422.
  **Dikonfirmasi hidup (bukan diasumsikan)**: file yang SAMA lewat `GET
  /reports/{filename}` tetap bisa diambil TANPA hambatan apa pun — bukti
  nyata bahwa celah `files.py` yang dicatat di atas benar-benar masih
  terbuka, bukan cuma teori. `.env` dikembalikan, service di-restart,
  file test dihapus.

**Tahap 25 — Autentikasi + fix path traversal `api/routes/files.py`**

Dipilih lewat `AskUserQuestion` sebagai kelanjutan LANGSUNG dari temuan
Tahap 24: `GET /reports/{filename}` (rute lain, folder sama dengan
`/api/v1/chat/download`) terbuka penuh tanpa autentikasi, bypass nyata
terhadap perlindungan yang baru dibangun.

- **Ditanya lagi sebelum coding, mengubah cakupan lebih jauh**: `FileList.tsx`
  (halaman Files) punya tombol unduh berupa `<a href download>` BIASA —
  TIDAK lewat `apiClient` (yang otomatis lampirkan `X-API-Key`), jadi kalau
  cuma backend dikunci, tombol itu akan 401 begitu `API_KEYS` aktif di
  produksi. Ditanya `AskUserQuestion`: kunci saja + catat gap frontend
  terpisah (pola sama seperti Tahap 24 terhadap `/api/v1/chat/download`,
  yang memang belum ada pemanggil frontend sama sekali), atau perbaiki
  sekalian — **perbaiki sekalian** dipilih, beda dari Tahap 24 karena di
  sini SUDAH ADA fitur frontend yang bekerja hari ini dan akan benar-benar
  rusak, bukan cuma gap yang belum pernah diisi.
- **`api/routes/files.py`**: `Depends(get_current_principal)` ditambah ke
  keempat endpoint (`GET /reports/{filename}`, `GET /reports`,
  `POST /upload`, `GET /uploads`) — autentikasi, BUKAN kepemilikan
  per-pengguna seperti `/api/v1/chat/download` (Tahap 24): tak ada konsep
  sesi di rute ini sama sekali, jadi siapa pun yang terautentikasi tetap
  bisa lihat file siapa pun — jaminan lebih sempit dari Chat, tapi jauh
  lebih baik dari "siapa pun di jaringan, tanpa kunci apa pun".
- **Bug keamanan KEDUA ditemukan di file yang sama, tak direncanakan**:
  `filename`/`file.filename` di-`os.path.join()` ke `REPORTS_DIR`/
  `UPLOADS_DIR` TANPA `os.path.basename()` sama sekali — path traversal
  asli, bukan cuma "tanpa auth". `agent/tools/writers.py`/
  `core/chat/engine.py` sudah menganggap `os.path.basename()` sebagai
  pertahanan standar untuk pola ini; rute ini saja yang belum pernah
  memakainya. Ditambahkan ke `download_report` (baca) DAN `upload_file`
  (tulis — lebih parah, potensi tulis file sembarang ke luar `uploads/`).
- **Frontend**: `fileService.ts`'s `reportDownloadUrl()` (string URL untuk
  `<a href>`) diganti `downloadReport()` — `async` function yang fetch
  lewat `apiClient.raw()` (melampirkan `X-API-Key`), lalu trigger unduhan
  dari blob hasil lewat elemen `<a>` sementara + `.click()` terprogram —
  pola standar "unduhan terautentikasi" untuk SPA tanpa sesi berbasis
  cookie. `FileList.tsx`: prop `hrefFor` (string) diganti `onDownload`
  (callback) — `<a href>` jadi `<button onClick>`, notifikasi error kalau
  gagal ditangani di `FilesPage.tsx` (pola sama seperti `onFileChosen` di
  file yang sama). `npm run lint`/`npm run build` hijau.
- **11 test baru** (521/521 total, stabil 2x berturut-turut):
  `test_files_api.py` — keempat endpoint butuh auth, akses dengan kunci
  valid berhasil, perilaku tanpa `API_KEYS` tak berubah, DAN untuk
  traversal: satu test langsung memanggil fungsi handler `download_report()`
  (bukan lewat HTTP — request HTTP ke `/reports/..%2Fsecret.txt` ternyata
  dinormalisasi router ASGI SEBELUM sampai ke handler, jatuh ke SPA
  catch-all yang menyajikan `index.html`, bukan membuktikan apa pun
  tentang sanitasi fungsi ini — dicatat jujur sebagai temuan, bukan
  dipaksa lolos) memverifikasi `os.path.basename()` benar-benar memangkas
  `../` apa pun; satu test HTTP terpisah memverifikasi invarian yang
  sebenarnya penting terlepas dari perilaku routing: isi file rahasia
  TIDAK PERNAH muncul di respons.
- **Diverifikasi live sungguhan**: `API_KEYS` sementara diisi, service
  di-restart (frontend di-`npm run build` ulang dulu). File test
  sungguhan ditaruh di `reports/` asli. **`GET /reports/{filename}` TANPA
  header sama sekali → 401 sungguhan** (persis bypass yang dikonfirmasi
  hidup di Tahap 24, sekarang tertutup); dengan kunci valid → 200 isi
  benar; `GET /reports` (list) tanpa auth → 401. `.env` dikembalikan,
  service di-restart, dikonfirmasi perilaku dev normal (tanpa `API_KEYS`)
  tak berubah sama sekali.

**Tahap 26 — Autentikasi `memory.py`/`monitoring.py`/`knowledge.py`**

Dipilih lewat `AskUserQuestion` sebagai lanjutan pola yang sama persis
dengan `files.py` sebelum Tahap 25: tiga rute ini terbuka tanpa
autentikasi sama sekali, `memory.py` khususnya sudah lama dicatat berisiko
(`docs/PROGRESS.md` sejak Tahap 12: "siapa pun yang tahu `session_id`
orang lain bisa membaca/menghapus memori sesi itu tanpa otorisasi apa
pun"). Tak ada perubahan frontend dibutuhkan — ketiga service
(`monitoringService.ts`/`memoryService.ts`/`knowledgeService.ts`) sudah
lewat `apiClient` (otomatis lampirkan `X-API-Key`), beda dari `files.py`
yang punya `<a href>` biasa.

- **`api/routes/memory.py`**: pakai ulang `_require_session_owner`
  LANGSUNG dari `api/routes/chat.py` (bukan mekanisme baru) — `session_id`
  di modul ini memang dimaksudkan sama dengan sesi `ChatEngine`, jadi
  gerbang kepemilikan Tahap 22 berlaku apa adanya di kelima rute
  (`GET`/`DELETE` per-tier). `session_id` yang belum pernah disentuh
  ChatEngine (kasus umum hari ini, karena `core/chat/engine.py` belum
  menulis ke `memory/` — gap lama yang tak berubah) tetap terbuka, cuma
  sesi dengan *owner tercatat* yang menolak pemanggil lain.
- **`api/routes/monitoring.py`**: `require_role("view_dashboard")` —
  pemakai PERTAMA sungguhan dari action `view_dashboard` yang sudah ada di
  `security/permissions.py` sejak Tahap 7 (ADR-0010) tapi tak pernah
  dipasang ke rute mana pun. Semua role sudah punya `view_dashboard`, jadi
  efeknya hari ini murni "wajib terautentikasi", belum jadi gerbang
  per-role granular — tapi memakai mekanisme yang benar, bukan cuma
  `Depends(get_current_principal)` telanjang.
- **`api/routes/knowledge.py`**: `Depends(get_current_principal)` di
  keempat rute — autentikasi, sama seperti `files.py`, bukan kepemilikan
  per-pengguna (`Document` tak punya konsep pemilik, basis pengetahuan
  tetap dibagi semua pemanggil, sama seperti sebelumnya).
- **Temuan performa nyata ditemukan saat menulis test, di luar rencana**:
  `GET /api/v1/monitoring/dashboard` — belum pernah ada test integrasi
  HTTP untuk rute ini sama sekali sebelum Tahap ini — ternyata makan
  **9+ detik** per panggilan karena `health_dashboard()`/
  `provider_dashboard()` memanggil `check_readiness()` yang benar-benar
  menghubungi Ollama/OpenAI/Claude/Gemini sungguhan (persis kerja
  `/health/ready`), DITAMBAH `workspace_dashboard()` yang re-scan
  filesystem tiap folder Workspace terdaftar (limitasi yang sudah dicatat
  Tahap 19/21) — makin lambat karena ada baris `Workspace` yatim dari
  sesi verifikasi manual sebelumnya yang menunjuk folder yang sudah tak
  ada. Bukan regresi Tahap 26, tapi test baru untuk rute ini WAJIB
  di-mock (DB via sqlite kosong + `check_readiness()` di-stub) supaya
  tetap cepat dan aman-CI (Bab 12.3) — tanpa itu, satu test saja makan
  10-30 detik.
- **20 test baru** (539/539 total, stabil 2x berturut-turut, ~13 detik
  total — bukan 10+ detik per test berkat mock di atas): 6
  `test_memory_ownership.py` (pemilik baca sukses, orang lain ditolak
  403 baca DAN hapus, sesi tak dikenal ChatEngine tetap terbuka, perilaku
  tanpa `API_KEYS` tak berubah), 5 `test_monitoring_auth.py`, 7
  `test_knowledge_auth.py`; plus satu baris `test_workspace_api.py` yang
  sudah ada diperbarui (memanggil `/knowledge/search` tanpa header, kini
  perlu kunci karena Tahap 26).
- **Diverifikasi live sungguhan**: `API_KEYS` sementara diisi. Ketiga rute
  tanpa header → 401 sungguhan. Dengan kunci valid → 200. Untuk memory:
  kirim pesan chat sungguhan dapat `session_id` nyata, User A baca memori
  sendiri → 200; **User B pakai `session_id` User A → 403 sungguhan**
  (`"Sesi ini milik pengguna lain"`) — mekanisme Tahap 22 terbukti berlaku
  apa adanya di rute baru ini. `.env` dikembalikan, service di-restart,
  perilaku dev normal (tanpa `API_KEYS`) dikonfirmasi tak berubah di
  ketiga rute.

**Tahap 27 — Loose ends Docker (`tesseract-ocr` + `HEALTHCHECK`)**

Dipilih lewat `AskUserQuestion` sebagai yang termurah dari 4 kandidat.
Menutup dua gap yang sama-sama dicatat eksplisit di Tahap 21 sebagai
"ditemukan tak sengaja, di luar cakupan saat itu" — bukan regresi baru,
dua celah lama yang sengaja ditunda.

- **`tesseract-ocr` + `tesseract-ocr-ind` ditambahkan ke stage runtime
  kedua Dockerfile** (`docker/Dockerfile.api` dan `docker/Dockerfile.worker`
  — worker ikut disentuh karena keduanya menjalankan `agent/tools/registry.py`
  yang sama, sebuah job bisa memanggil `read_image()` persis seperti
  panggilan tool Chat). `agent/tools/readers.py::read_image()` memanggil
  `pytesseract.image_to_string(img, lang="eng+ind")` — `pytesseract` cuma
  wrapper Python murni di sekitar binary CLI `tesseract` (ada di
  `requirements.txt`, tapi binary-nya sendiri tak pernah diinstal di image
  manapun), dan paket Debian `tesseract-ocr` defaultnya cuma membawa data
  bahasa Inggris — `tesseract-ocr-ind` adalah paket terpisah untuk separuh
  "ind" dari `"eng+ind"`, wajib karena ini alat dokumen pertambangan
  Indonesia.
- **`HEALTHCHECK` ditambahkan ke keduanya, dengan mekanisme berbeda**:
  `Dockerfile.api` pakai `curl -f http://localhost:8000/health/` (endpoint
  liveness murah, BUKAN `/health/ready` — `/health/ready` memanggil
  `check_readiness()` yang menghubungi Ollama + tiap provider cloud
  sungguhan, diukur Tahap 26 makan 9-32 detik; menjadikannya healthcheck
  tiap 30 detik berarti API bisa ditandai "unhealthy" cuma karena Ollama
  sedang lambat sesaat). `Dockerfile.worker` tidak punya server HTTP sama
  sekali (RQ worker) — dipakai `python -c "...redis.from_url(...).ping()"`
  sebagai gantinya, satu-satunya dependency nyata yang dibutuhkan
  `worker_ai`/`worker_gis` (image sama, `command:` beda di
  `docker-compose.yml`) untuk bisa maju; tidak membuktikan loop kerja RQ
  itu sendiri tak macet, cuma bahwa proses masih bisa menjangkau antrian —
  batas yang lebih longgar dari API, diakui sadar (bukan false-precision).
- **Diverifikasi live penuh, bukan cuma review**: `docker compose build
  --no-cache` ketiga image → `tesseract --list-langs` di dalam image
  mengonfirmasi `eng`+`ind`+`osd` tersedia → **`read_image()` yang
  SESUNGGUHNYA dipanggil di dalam container** (bukan cuma binary
  `tesseract` langsung) terhadap gambar PNG buatan sendiri berisi teks
  `"Izin Usaha Pertambangan Wilayah Kalimantan"` → OCR mengembalikan teks
  itu persis, `has_ocr_text: true` — membuktikan jalur kode nyata, bukan
  cuma paket terinstal. `docker compose up -d --no-deps api worker_ai
  worker_gis` merecreate ketiga container dari image baru →
  `docker ps`/`docker inspect .State.Health` ketiganya `healthy` dalam
  <20 detik, log health check API menunjukkan probe HTTP sungguhan
  (`{"status":"ok","service":"AI Engine"}`, exit 0), log worker
  menunjukkan `redis.ping()` sukses (exit 0).
- **Koreksi catatan basi ditemukan saat menulis Tahap ini** (pola sama
  seperti koreksi `projects.py` di Tahap 26): bagian "Gap kumulatif" masih
  menyimpan kalimat lama dari Tahap 19 yang bilang "`core/chat/engine.py`
  belum workspace-aware... ChatEngine masih hanya tahu Uploaded Files" —
  ini sudah salah sejak Tahap 23 (Agent Workspace Context) menutupnya.
  Diperbaiki di bagian yang sama, bukan dibiarkan kontradiksi dengan
  paragraf Tahap 20-26 tepat di atasnya.
- **Tidak ada test Python baru** — perubahan murni Docker/infrastruktur,
  tak ada logika Python yang berubah. `pytest -q` penuh tetap 539/539,
  dijalankan ulang untuk konfirmasi nol regresi tak terduga.
- **Gap yang diakui**: `HEALTHCHECK` worker cuma menjamin konektivitas
  Redis, bukan bahwa loop `worker.work()` benar-benar memproses job (mis.
  proses bisa saja hidup+terhubung Redis tapi macet di satu job) — heartbeat
  RQ yang lebih tepat (`rq info`/`Worker.all()`) di luar cakupan tugas
  kecil ini, dicatat sebagai kandidat lanjutan kalau pernah jadi masalah
  nyata di produksi.

**Tahap 28 — MCP Server (Bab 60), arah sebaliknya dari Client Tahap 17**

Dipilih lewat `AskUserQuestion` dari 4 kandidat (MCP Server / gambar-GIS
Workspace via Chat / heartbeat RQ / Bab 68 Backlog). Menutup item #1 yang
tersisa di "Titik mulai sesi berikutnya" sejak Tahap 17 sengaja menunda
sisi Server: `mcp_client/` bisa mengonsumsi MCP server pihak ketiga, tapi
tak ada yang membuat AI_ENGINE sendiri BISA dikonsumsi client MCP
eksternal (mis. Claude Desktop). Rencana lengkap (5 keputusan desain +
implementasi + test) ditulis dulu lewat Plan Mode dan disetujui sebelum
coding — perubahan arsitektural dengan beberapa keputusan konsekuensial
(transport, subset tool, model RBAC), bukan sekadar tambah baris ke modul
yang sudah ada.

- **Transport: stdio saja** (`mcp_server/server.py` baru, sejajar
  `mcp_client/`) — sama seperti `mcp_client/demo_server.py`, dan
  sengaja BUKAN SSE/HTTP: server jaringan berarti pemanggil tak dikenal
  bisa memberi `file_path` sembarang ke tool baca/tulis, butuh tinjauan
  keamanan sandboxing path tersendiri yang di luar cakupan tugas ini.
  Dijalankan `python -m mcp_server.server`, digerbang `ENABLE_MCP` (Bab
  57.1, flag yang sama dipakai sisi Client) — mati eksplisit di startup
  kalau `false`, bukan menggantung di stdio.
- **API rendah (`mcp.server.Server`), bukan `FastMCP`'s decorator** —
  `demo_server.py` cocok untuk 2 tool tetap dengan signature Python tetap;
  di sini tool datang dinamis dari `core/chat/tool_schemas.py::TOOL_SCHEMAS`
  (skema JSON yang SUDAH ADA, dipakai ulang apa adanya, bukan ditulis
  baru) + `agent/tools/registry.py`'s `ToolRegistry.execute()` yang sama
  dipakai tiap jalur lain di app ini.
- **Subset tool yang diekspos = `TOOL_SCHEMAS` dikurangi 4 tool yang tak
  masuk akal dipanggil di luar pemanggil normalnya**: `workspace_list_files`/
  `workspace_read_file` (Tahap 23) — gerbang keamanan sesungguhnya untuk
  keduanya adalah `_run_tool` MENYUNTIKKAN `session.workspace_id` dari
  sesi ChatEngine, bukan model; panggil `registry.execute()` langsung dari
  sini tak punya sesi sama sekali untuk disuntikkan, mengeksposnya berarti
  entah selalu gagal atau (lebih buruk) menerima `workspace_id` polos dari
  pemanggil luar tanpa cek keanggotaan Project apa pun. `mcp_list_tools`/
  `mcp_call_tool` (Tahap 17) — jembatan proxy ke MCP server LAIN yang kami
  konsumsi; mengekspos "client MCP kami" sebagai tool lewat "server MCP
  kami sendiri" pola proxy membingungkan tanpa use-case jelas. Sisa ~23
  tool (reader/writer/GIS/transform gambar/`analyze_text`/`plugin_weather`)
  diekspos apa adanya.
- **RBAC: pakai ulang `security/permissions.py` PERSIS seperti Bab 60.1
  mewajibkan** ("MCP tidak memiliki jalur pintas keamanan") — stdio tak
  punya identitas pemanggil per-request (tak ada header `X-API-Key`), jadi
  seluruh proses server jalan sebagai SATU role tetap sepanjang hidupnya:
  setting baru `MCP_SERVER_ROLE` (default `"user"`, pilihan konservatif —
  semua tool baca tetap ungated, semua tool tulis/convert/generate
  ditolak `PermissionError` sungguhan sampai operator eksplisit set
  `MCP_SERVER_ROLE=operator` di environment yang menjalankan proses ini).
  Gate yang dipakai SAMA PERSIS `registry.execute(name, args, role=...)`
  yang dipakai `agent/core.py`/`core/chat/engine.py`.
- **Bug nyata ditemukan saat verifikasi live PERTAMA, bukan lewat
  pytest**: `logging.info(...)` lewat `core/utils/logger.py` (structlog,
  `PrintLoggerFactory()` → default ke stdout) — pada transport stdio,
  stdout ADALAH kanal protokol JSON-RPC itu sendiri. Baris log apa pun ke
  situ merusak stream, dikonfirmasi nyata: client MCP sungguhan (skrip
  verifikasi manual di bawah) gagal parse frame JSON-RPC dengan error
  pydantic literal. **Fix**: `mcp_server/server.py` sengaja TIDAK memakai
  `core.utils.logger.get_logger()` (shared, protected secara de-facto oleh
  dipakai di mana-mana) — dipakai `logging` standar dikonfigurasi eksplisit
  ke `sys.stderr`, kanal yang memang disediakan MCP SDK untuk ini
  (`stdio_client`'s `errlog=sys.stderr` di sisi client). **Pelajaran
  ditulis di komentar kode** (hidden constraint yang akan mengejutkan
  pembaca lain yang menambah modul stdio baru nanti).
- **10 test baru (549/549 total, stabil 2x berturut-turut)**:
  `tests/unit/test_mcp_server.py` (7, fake `ToolRegistry` pola
  `test_tool_registry_rbac.py` — filter skema, tool tak dikenal/dikecualikan
  ditolak, RBAC user vs operator, tool baca tak terpengaruh role) +
  `tests/integration/test_mcp_server_e2e.py` (3, **dogfooding** — pakai
  `mcp_client.client.MCPClient` KITA SENDIRI melawan `mcp_server/server.py`
  KITA SENDIRI sebagai subprocess sungguhan, mirror persis pola
  `test_mcp_client.py` terhadap `demo_server.py` tapi membuktikan sisi
  Server: `list_tools()` menampilkan tool asli+bukan 4 yang dikecualikan;
  role `operator` menulis+membaca file SUNGGUHAN di `reports/`; role
  `user` (default) ditolak nyata pada PROSES SUNGGUHAN, bukan cuma fake
  registry unit-level). `mcp_client/client.py`'s `MCPClient.__init__` dapat
  parameter opsional `env` (aditif, dipakai test untuk set
  `MCP_SERVER_ROLE` per subprocess) — satu-satunya sentuhan ke kode Tahap
  17 yang sudah ada.
- **Diverifikasi live sungguhan DI LUAR pytest juga** (skrip ad-hoc,
  dihapus setelah selesai): role `user` → `list_tools()` menampilkan 23
  tool nyata (bukan 27 — 4 dikecualikan terbukti benar-benar tak muncul);
  `write_txt` → ditolak nyata (`"role 'user' lacks permission
  'tool:write_txt'"`); role `operator` → `write_txt` lalu `read_txt`
  BENAR menulis+membaca file nyata di `~/ai_engine/reports/` (isi cocok
  persis); `ENABLE_MCP=false` → proses keluar langsung (exit 0) alih-alih
  menggantung di stdio. Log startup tampil bersih di stderr, nol frame
  JSON-RPC rusak lagi setelah fix logger di atas.
- **Gap yang diakui, didokumentasikan eksplisit sebagai tindak lanjut**:
  transport SSE/HTTP (server jaringan, butuh auth+path-sandboxing sendiri)
  belum ada; gambar/GIS Workspace via MCP tetap tak terjangkau (sama
  seperti lewat Chat, Bab 69.5); baru satu role tetap per PROSES server
  (bukan per-panggilan seperti HTTP `X-API-Key`) — wajar untuk stdio
  tapi berarti satu server = satu tingkat akses tetap, bukan granular
  per klien.

**Tahap 29 — Gambar/GIS Workspace via Chat (Bab 69.5 Vision follow-up)**

Dipilih lewat `AskUserQuestion` dari 4 kandidat (gambar/GIS Workspace /
Bab 68 Backlog / transport SSE/HTTP MCP / heartbeat RQ). Menutup gap yang
Tahap 23 tinggalkan eksplisit: `workspace_read_file` cuma bisa dokumen
(pdf/txt/docx/csv/json) — file gambar atau GIS di Project Workspace
mengembalikan "Tipe file tidak didukung". Direncanakan dulu lewat Plan
Mode (protected folder `core/chat/engine.py` disentuh, beberapa keputusan
desain) sebelum coding.

- **Koreksi cakupan ditemukan saat riset, sebelum coding dimulai**: opsi
  yang ditawarkan ke Boss menyebut "Chat DAN MCP Server" — itu TIDAK
  akurat. `mcp_server/server.py` (Tahap 28) sengaja MENGECUALIKAN
  `workspace_list_files`/`workspace_read_file` sama sekali (tak ada sesi
  ChatEngine di sana untuk menyuntikkan `workspace_id`) — jadi tak ada
  apa pun untuk diperluas di sisi MCP. Tahap ini murni ChatEngine; akses
  Workspace lewat MCP tetap gap terpisah yang lebih besar (sudah dicatat
  di gap Tahap 28).
- **`agent/tools/workspace_reader.py`'s `_read_file` kini dispatch per
  kategori** via `tools/adapters/filesystem.py::classify()` (fungsi yang
  SUDAH ADA, dipakai `FilesystemAdapter.scan()` sejak Tahap 19 — bukan
  logika klasifikasi baru): `document` (jalur lama, tak berubah), `image`
  (baru: baca byte mentah, base64-encode, `mimetypes.guess_type` stdlib —
  bentuk data PERSIS yang sudah dipakai gambar upload di
  `_build_user_message`), `gis` (baru: pakai ulang `agent/tools/gis_io.py`'s
  `_load_any_fc()`/`_summarize_fc()` — ringkasan luas/centroid/bbox
  kompak yang SAMA dipakai `read_kml`/`read_geojson`/`read_shp`, BUKAN
  dump koordinat mentah, sesuai pelajaran `gis-tool-output-consistency`
  yang sudah lama dicatat).
- **Mekanisme baru: suntik giliran vision sungguhan setelah hasil tool
  gambar**, di `core/chat/engine.py::stream_run` (protected, aditif
  murni). Pesan `tool`-role Ollama tak bisa dipercaya membawa `images` —
  mekanisme yang SUDAH TERBUKTI di codebase ini adalah pesan `user`-role
  dengan daftar `images` base64 (persis yang sudah dipakai gambar upload
  di `_build_user_message`). Jadi tepat setelah pesan hasil tool
  di-append, kalau hasilnya `type == "image"`, di-append SATU pesan lagi:
  `{"role": "user", "content": "(Gambar dari Workspace: ...)", "images": [base64]}`
  — giliran berikutnya `_stream_chat` akan benar-benar mengirim gambar
  itu ke Ollama.
- **Detail teknis ditemukan saat membaca ulang loop, sebelum bug sempat
  terjadi**: pesan `tool`-role isinya `json.dumps(result)[:12000]` —
  membiarkan base64 mentah masuk situ akan menghabiskan sebagian besar
  budget 12.000 karakter untuk fragmen base64 terpotong yang tak berguna
  (model tak bisa "melihat" gambar dari teks base64). Fix: base64 dibuang
  dari salinan `result` sebelum di-JSON-dump ke pesan `tool`; salinan ASLI
  (base64 utuh) dipakai untuk pesan vision baru di atas.
- **3 test baru (552/552 total, stabil 2x berturut-turut)**: 2
  `test_workspace_reader.py` (gambar → base64 decode balik = byte file
  asli + mime_type benar; GeoJSON poligon nyata → `total_area_ha`/
  `polygon_count` benar, TIDAK ada `"coordinates"` mentah di hasil), 1
  `test_chat_engine_workspace_context.py` (fake `workspace_read_file`
  bertipe image → pesan `user`/`images` muncul TEPAT setelah pesan `tool`,
  dan base64 TIDAK bocor ke konten JSON pesan `tool` itu sendiri).
- **Diverifikasi live sungguhan lewat model asli** (`gemma4:e2b`, restart
  `ai-engine.service`, Project+Workspace+folder scratch nyata dengan satu
  PNG 200×100 biru+kotak kuning di tengah dan satu GeoJSON poligon nyata):
  "deskripsikan gambar site.png" → model BENAR menyebut "biru terang" di
  atas-bawah dan "kuning cerah" di tengah, plus tata letak spasial yang
  cocok (kotak kuning "dibatasi garis biru di kiri dan kanan") — bukti
  kuat model benar-benar MELIHAT gambar sungguhan (bukan halusinasi warna
  acak), mekanisme suntik-vision-di-tengah-loop terbukti berfungsi
  terhadap model dan chat template asli, bukan cuma tak error. "berapa
  luas blok.geojson" → jawaban **12298.3366 Ha**, cocok dengan perhitungan
  independen untuk poligon 0.1°×0.1° di lintang -7° (~11.1km × ~11.0km ≈
  122 km²) — angka nyata dari file nyata, bukan dikarang. Project/
  Workspace/folder scratch dihapus (soft-delete) setelah verifikasi.
- **Gap yang diakui**: akses Workspace lewat MCP Server tetap tak ada
  sama sekali (lihat koreksi cakupan di atas — gap terpisah, lebih besar,
  dari Tahap 28); tak ada batas ukuran file gambar sebelum base64-encode
  (sama seperti upload biasa — bukan risiko baru, konsisten dengan
  perilaku yang sudah ada).

## Test
- **Backend: 552/552 lulus** (`pytest -q`, stabil 2x berturut-turut,
  ~16-20 detik total) — naik dari 549 lewat 3 test gambar/GIS Workspace
  (Tahap 29, lihat detail di atas: 2 unit `test_workspace_reader.py`, 1
  unit `test_chat_engine_workspace_context.py`). Sebelumnya naik dari 539
  lewat 10 test MCP Server (Tahap 28, lihat detail di atas: 7 unit
  `test_mcp_server.py`, 3 integrasi `test_mcp_server_e2e.py` dogfooding
  subprocess sungguhan). Sebelumnya tetap 539 di Tahap 27 (loose ends
  Docker, murni infrastruktur, nol test
  Python baru; diverifikasi live lewat rebuild image + `docker inspect`
  alih-alih pytest, lihat detail di atas). Sebelumnya naik dari 521 lewat 20 test autentikasi
  `memory.py`/`monitoring.py`/`knowledge.py` (Tahap 26, lihat detail di
  atas). Sebelumnya naik dari 510 lewat 11 test autentikasi+traversal
  `files.py` (Tahap 25, lihat detail di atas). Sebelumnya naik dari 504
  lewat 6 test kepemilikan file download Chat (Tahap 24,
  lihat detail di atas). Sebelumnya naik dari 489 lewat 15 test Agent
  Workspace Context (Tahap 23, lihat
  detail di atas). Sebelumnya naik dari 481 lewat 8 test kepemilikan sesi
  Chat (Tahap 22, lihat detail di
  atas: `test_chat_session_ownership.py`). Sebelumnya naik dari 474 lewat 7
  test RBAC ChatEngine (Tahap 20, lihat detail di atas: 4
  unit `test_chat_engine_rbac.py`, 3 integrasi `test_chat_api_rbac.py`;
  plus perbaikan isolasi RAG pra-ada di `test_workspace_api.py` yang bikin
  suite penuh rapuh tergantung urutan file). Sebelumnya naik dari 409 lewat 65 test
  Workspace (Tahap 19, lihat detail di atas: filesystem adapter, scanner/
  indexer, RBAC, integrasi API, monitoring dashboard). Sebelumnya naik dari 384 lewat 25 test
  migrasi RBAC (Tahap 18, lihat detail di atas). Sebelumnya naik dari 372 lewat 12 test
  MCP Client (Tahap 17, lihat detail di atas): 4 unit MCPClient, 5 unit
  registry bridge, 3 unit permission. Sebelumnya naik dari 356 lewat 16 test
  Plugin (Tahap 16, lihat detail di atas): 5 unit registry, 3 unit
  WeatherPlugin, 4 unit permission, 4 integrasi API. Sebelumnya naik dari 341 lewat 15 test
  Automation (Tahap 15, lihat detail di atas): 7 unit `test_scheduler.py`,
  8 integrasi `test_automation_api.py`. Sebelumnya naik dari 328 lewat 13 test
  Vision (Tahap 14, lihat detail di atas): 7 unit provider payload, 2 unit
  agent, 2 unit planner, 2 integrasi endpoint. Sebelumnya naik dari 318
  lewat 10 test integrasi `tests/integration/test_projects_api.py` (CRUD + role
  owner/editor/viewer, akses ditolak untuk stranger, viewer tak bisa PATCH,
  arsip bukan hard-delete, sama pola SQLite in-memory seperti
  `test_knowledge_api.py`, identitas caller disimulasikan lewat
  `API_KEYS`+header `X-API-Key` per test). Sebelumnya naik dari 308 lewat
  10 test: `tests/integration/test_memory_api.py` (5 — baca/hapus
  tiap tier lewat `MemoryManager` yang di-monkeypatch persis pola
  `_orchestrator`), `tests/integration/test_knowledge_api.py` (5 —
  ingest+list+search+delete+404, dengan `_retriever` route di-monkeypatch
  ke `InMemoryKnowledgeStore` eksplisit dan sesi DB SQLite in-memory via
  `dependency_overrides`, supaya tak bergantung pada `VECTOR_BACKEND=pgvector`
  yang kebetulan aktif di lingkungan dev ini). Baru Tahap 10: 12 test.
  Baru Tahap 11: 9 test integrasi `tests/integration/test_orchestrator_api.py`
  (roles/modes, tolak roles kosong/mode tak dikenal, sequential selesai,
  eskalasi reflection masuk daftar approval, decide menyelesaikan/menolak,
  404 trace_id tak dikenal, 403 role tak cukup) — agent distub persis pola
  `tests/unit/test_orchestrator.py`, nol panggilan provider sungguhan.
- **Frontend (`web/`): 5/5 lulus** (`npm test`, Vitest + React Testing
  Library) — `workflowStore.applyEvent()`/`setFromRunResult()` dan
  `ApprovalCard` interaksi. `npm run lint`/`npm run build` hijau.

## Gap kumulatif (Tahap 1-29, diakui bukan disamarkan)
- **RBAC ke `core/chat/engine.py` SELESAI** (Tahap 20) — gap yang diakui
  berulang sejak Tahap 10/16/17/18 kini tertutup: `stream_run(role=...)`
  menggerbang setiap panggilan tool lewat jalur Chat, satu-satunya jalur
  yang benar eksekusi tool untuk `tool:*`/`plugin:*`/`mcp:call`.
  **Kepemilikan sesi Chat SELESAI juga (Tahap 22)** — `session_id` kini
  terikat `Principal.api_key` yang pertama menyentuhnya; orang lain
  ditolak 403 baca/lanjut/hapus/upload, `GET /sessions` cuma tampilkan
  milik sendiri. **Agent Workspace Context ke ChatEngine SELESAI juga
  (Tahap 23)** — Chat kini bisa `workspace_list_files`/`workspace_read_file`
  dari Project Workspace (Tahap 19), digerbang RBAC Project-role sekali di
  rute, `workspace_id` selalu disuntik dari sesi (tak pernah dari model).
  **Kepemilikan file download Chat SELESAI juga (Tahap 24)** —
  `/api/v1/chat/download/{filename}` kini wajib `session_id` + kepemilikan
  + bukti file itu memang dihasilkan di sesi itu (`session.produced_files`).
  **`api/routes/files.py` SELESAI juga (Tahap 25)** — bypass nyata yang
  dikonfirmasi hidup di Tahap 24 kini tertutup: keempat endpoint
  (`/reports/{filename}`, `/reports`, `/upload`, `/uploads`) wajib
  autentikasi, plus bug path traversal kedua (ditemukan di file yang sama,
  `os.path.basename()` tak pernah dipakai) diperbaiki sekalian. Autentikasi
  di sini BUKAN kepemilikan per-pengguna seperti Chat — tak ada konsep
  sesi, siapa pun yang terautentikasi tetap lihat file siapa pun (jaminan
  lebih sempit, didokumentasikan sadar). **`memory.py`/`monitoring.py`/
  `knowledge.py` SELESAI juga (Tahap 26)** — pola gap yang sama persis
  dengan `files.py` sebelum Tahap 25 kini tertutup: `memory.py` pakai
  ulang kepemilikan sesi Tahap 22 langsung (bukan mekanisme baru),
  `monitoring.py` jadi pemakai pertama sungguhan `require_role("view_dashboard")`
  (ada sejak Tahap 7, tak pernah dipasang), `knowledge.py` autentikasi
  polos (tak ada konsep pemilik dokumen). **Gambar/GIS di Workspace SELESAI
  juga (Tahap 29)** — `workspace_read_file` kini menampilkan gambar
  sungguhan sebagai giliran vision (bukan cuma teks) dan meringkas file
  GIS persis seperti `read_kml`/`read_geojson`/`read_shp`; diverifikasi
  live model benar-benar mendeskripsikan warna/bentuk gambar nyata dan
  menyebut luas GIS nyata (lihat detail Tahap 29 di atas). Rute
  API selain yang sudah opt-in RBAC (chat, agent/run, projects, workspace,
  files, memory, monitoring, knowledge) masih terbuka tanpa autentikasi —
  makin sedikit yang tersisa. **Loose ends Docker SELESAI juga (Tahap 27)**
  — `tesseract-ocr`/`tesseract-ocr-ind` terinstal (OCR `read_image` yang
  sebelumnya kemungkinan gagal senyap di Docker sejak awal kini
  diverifikasi live benar-benar bekerja di dalam container) dan
  `HEALTHCHECK` eksplisit ada di kedua Dockerfile (API via `/health/`,
  worker via ping Redis). Gap tersisa: healthcheck worker cuma menjamin
  konektivitas Redis, bukan bahwa `worker.work()` benar-benar memproses
  job.
- **Project Workspace (Tahap 19) baru sumber Local** — Network/Server/
  Cloud/SharePoint/OneDrive/GDrive/S3 belum ada adapternya (Bab 69.16,
  scope-sempit-sadar); `mount` menolak eksplisit, bukan diam-diam
  menerima. **Koreksi catatan basi (ditemukan saat menulis Tahap 27,
  pola sama seperti koreksi `projects.py` Tahap 26)**: kalimat di sini dulu
  bilang "`core/chat/engine.py` belum workspace-aware... ChatEngine masih
  hanya tahu Uploaded Files" — itu sudah salah sejak Tahap 23 menutupnya
  (lihat paragraf Tahap 23 di atas: `workspace_list_files`/
  `workspace_read_file` sungguhan tersambung, RBAC Project-role sekali di
  rute). Gap yang MASIH benar: hanya dokumen (pdf/txt/docx/csv/json) yang
  bisa dibaca lewat Chat dari Workspace — gambar/GIS Workspace masih baris
  Vision Bab 69.5 terpisah. Tidak ada cache counts persisten — `workspace_dashboard()`
  dan `GET .../status` re-scan filesystem tiap dipanggil (O(files on disk)),
  bukan baca dari kolom ter-materialisasi. Tidak ada interactive browser
  drive (tidak ada Playwright/Cypress di repo ini) — WorkspacePage.tsx
  diverifikasi lewat `npm run build`/code review, bukan klik sungguhan di
  browser. Auto Sync/Live File Watcher/Incremental Index/Versioning/
  Snapshot/Multi Workspace/Remote Workspace/Collaboration/Workspace
  Permission Management UI granular — semua Backlog Prioritas 21-29, nol
  disentuh.
- **MCP Client (Tahap 17) — sisi Server SELESAI juga (Tahap 28)**.
  `mcp_server/server.py` baru mengekspos ~23 tool AI_ENGINE (dikurangi 4
  tool session-bound/meta, lihat detail Tahap 28 di atas) ke client MCP
  eksternal manapun lewat stdio, RBAC digerbang `MCP_SERVER_ROLE`. SSE/HTTP
  transport tetap belum ada (keputusan skop sadar Tahap 28 — butuh
  tinjauan auth+path-sandboxing sendiri untuk pemanggil jaringan tak
  dikenal). **Baru satu server pihak ketiga terkonfigurasi di sisi Client**
  (`demo`, fixture dev murni untuk pembuktian) — belum tersambung ke MCP
  server pihak ketiga sungguhan manapun; nambah server nyata baru tinggal
  satu baris di `MCP_SERVERS` tapi belum ada yang dipilih/diverifikasi.
  **Session Management minimal di sisi Client** — satu koneksi baru per
  panggilan (bukan persisten/pooled), jadi tiap panggilan bayar biaya
  spawn subprocess; untuk pemakaian intensif ini perlu ditinjau ulang.
  **Koreksi catatan basi ditemukan saat menulis Tahap 28** (pola sama
  seperti koreksi `projects.py` Tahap 26 / ChatEngine-workspace-aware
  Tahap 27): baris ini dulu bilang "RBAC `mcp:call` inert dari Chat" —
  itu sudah salah sejak Tahap 20 (hari yang sama, beberapa Tahap
  setelahnya) menyambungkan `role` ke SETIAP panggilan `registry.execute()`
  dari ChatEngine secara generik, termasuk `mcp_call_tool`; dicek ulang
  kodenya (`core/chat/engine.py`'s `_run_tool`), bukan diasumsikan dari
  catatan lama. Tidak ada rate-limit/timeout eksplisit di `MCPClient` di
  luar default SDK. **Dependency `mcp` menaikkan `pydantic` (2.10.3→2.13.4)
  dan mengunci `starlette==0.41.3`** — sudah diverifikasi 384 test lama
  tetap lulus dan service live tetap sehat setelah bump, tapi ini
  transitive-dependency footprint baru yang perlu diingat saat upgrade
  FastAPI/pydantic berikutnya.

- **Plugin (Tahap 16) enabled/disabled state in-memory saja** — restart
  proses API mengembalikan semua plugin ke enabled (default manifest),
  belum persisten ke Postgres. Baru **satu plugin nyata** (`weather`);
  kategori lain Bab 59.2 (ERP/SAP/Mining/Email/GIS Eksternal) semua masih
  nol kode — nambah plugin baru sudah punya polanya (folder
  `plugins/<nama>/` + satu baris di `_AVAILABLE` dict), tapi belum
  dilakukan untuk kategori lain. **RBAC `plugin:weather` inert dari Chat**
  (`core/chat/` tak pernah mengirim role ke `ToolRegistry.execute()`) —
  gap yang sama persis dengan `write_pdf` sejak Tahap 10, bukan regresi
  baru. Tidak ada Tool Discovery/Capability Discovery dinamis (Bab 59
  cuma menyebutnya untuk MCP, bukan Plugin — jadi bukan gap yang relevan
  di sini, tapi dicatat untuk kejelasan cakupan). Plugin belum bisa
  dipanggil dari jalur Orchestrator/Workflow — hanya dari Chat, karena
  jalur Orchestrator memang tidak punya tool-calling apa pun sama sekali
  (gap arsitektural yang jauh lebih besar dari Plugin itu sendiri, lihat
  temuan riset Tahap 16 di atas).

- **Automation (Tahap 15) tanpa sintaks cron** — cuma interval polos
  ("tiap N detik"), keputusan skop sadar (lihat docstring
  `db.models.ScheduledJob`), bukan keterbatasan; kalau nanti butuh "tiap
  Senin jam 9 pagi", perlu desain ulang trigger. **Scheduler jalan
  in-process** lewat `asyncio.create_task`, bukan proses worker
  terpisah — job sedang berjalan akan hilang kalau proses API
  restart di tengah jalan (diterima untuk pass pertama, dicatat di
  docstring `scheduler/scheduler.py`, sama semangat dengan penerimaan
  gap serupa di Tahap-tahap sebelumnya). **Tidak ada RBAC di atas
  ownership-setelah-dibuat** — siapa pun yang punya API key valid manapun
  (atau tanpa key sama sekali saat `API_KEYS` kosong) boleh membuat
  `ScheduledJob` baru; begitu dibuat baru dia scoped ke `owner_key`-nya.
  `messaging.TaskQueue` (Bab 23) makin lama makin tak terpakai — sekarang
  tiga fitur (Orchestrator, Vision, Automation) semua jalan langsung
  in-process, belum ada satu pun yang benar-benar konsumsi antrean itu.
  Counter/jam scheduler pakai `datetime.utcnow()` server, bukan per-user
  timezone — `interval_seconds` tak peduli zona waktu (memang tak relevan
  untuk interval polos, tapi akan jadi relevan kalau nanti cron
  ditambahkan).
- **Vision (Tahap 14) diverifikasi dengan model lokal gratis (`tool`/Ollama),
  bukan role `vision` sungguhan (default Gemini, cloud)** — payload gambar
  tiap provider cloud (Gemini/OpenAI/Claude) sudah benar secara *bentuk*
  (unit test langsung ke method pembangun payload), tapi belum pernah
  diverifikasi *live* menembak API cloud sungguhan dengan gambar nyata
  (beda dari teks yang sudah pernah, per catatan Tahap sebelumnya). Chat UI
  (`core/chat/`) sendiri sudah lama punya vision lewat Ollama — Tahap 14
  cuma membuka jalur yang sama di sisi Orchestrator/multi-agent, dua jalur
  ini tetap tidak terhubung satu sama lain (gap lama, dicatat sejak Tahap
  11). `WorkflowRunRequest.images` juga tidak ada batas ukuran/jumlah
  eksplisit — payload besar (banyak gambar resolusi tinggi) bisa saja bikin
  request tersendat, belum ada validasi/limit.
- **`Project` (Tahap 13) berdiri sendiri** — belum ada FK dari
  `ConversationMessage`/`Document` ke `Project.id`, jadi membuka Chat/Files
  dari dalam sebuah Project (atau melihat "semua percakapan proyek ini")
  belum mungkin — itu keputusan lanjutan yang sengaja ditunda
  (`PROJECT_SPECIFICATION.md` §2/§6), bukan lupa. Tidak ada `User` table di
  sistem ini — `owner_key`/`principal_key` adalah string API key mentah,
  bukan ID user; ganti API key = "identitas" berbeda, tidak ada
  penyatuan/migrasi kepemilikan otomatis kalau key berubah. RBAC per-proyek
  di `api/routes/projects.py` sungguhan (owner/editor/viewer dicek dari
  `ProjectMember`), tapi endpoint-nya sendiri tetap bisa diakses siapa pun
  yang punya API key valid manapun (atau tanpa key sama sekali saat
  `API_KEYS` kosong) — tak ada gerbang "siapa boleh membuat Project baru".
  Plugin/Automation/Vision/MCP (4 dari 5 area Phase 3) masih nol kode sama
  sekali, belum disentuh.
- **Dashboard observability kini ADA di web UI (Tahap 12, menutup gap sejak
  Tahap 6)** — `MonitoringPage.tsx` + `api/routes/monitoring.py`, 7 dari 8
  dashboard Bab 62. Yang masih gap: **Memory Dashboard** (field ke-5
  `vector_entries` butuh instance `VectorMemory` yang tak berguna tanpa
  integrasi ChatEngine↔memory/ — lihat bawah); **Execution Timeline**
  (`Tracer.timeline(trace_id)`) belum ada di UI sama sekali, dan tak bisa
  didaftar tanpa `trace_id` diketahui dulu (tak ada method "list semua
  trace_id").
- **`api/routes/memory.py` kini ADA (Tahap 12 lanjutan)**, tapi **ChatEngine
  (`core/chat/`) dan `memory/` (Tahap 3) tetap dua sistem terpisah total** —
  gap ini bukan gap API lagi, melainkan gap *data*. `core/chat/engine.py`
  (fondasi terlindungi) tidak pernah menulis ke `memory/` tier manapun,
  jadi `GET /api/v1/memory/{session_id}` benar secara kontrak tapi kosong
  untuk sesi chat nyata mana pun — dikonfirmasi sebagai pilihan sadar Boss
  (via `AskUserQuestion`), bukan diam-diam. Mengisi gap ini butuh integrasi
  ChatEngine→memory/ (strangler pattern, sentuh fondasi hati-hati) — belum
  dimulai. Reflection memory & Vector memory sengaja tidak diekspos di rute
  ini (lihat catatan Tahap 12 di atas).
- **`api/routes/knowledge.py` kini ADA (Tahap 12 lanjutan)** — wiring HTTP
  pertama untuk `rag/` (Tahap 5), ingest teks tempel + list + search +
  delete, dipakai `db.models.Document` sebagai manifest. Gap yang tersisa:
  ingest masih teks-tempel saja (bukan upload file/OCR — keputusan sadar
  Boss, bukan keterbatasan teknis); `KnowledgeStore` masih tak punya
  delete-by-dokumen (hapus manifest tak menghapus chunk vector-nya);
  `RAG_EMBEDDING_PROVIDER` default ke `hashed_bow_embedder` offline (bukan
  embedding model sungguhan) kecuali dikonfigurasi eksplisit — relevansi
  hasil pencarian akan lebih baik dengan embedder asli.
- **`services/eventStream.ts` (frontend) ditulis tapi belum dipakai** —
  mengikuti kontrak `EVENT_CATALOG.md` (event kanonis PascalCase:
  `WorkflowCreated`/`AgentStarted`/dst.), siap pasang begitu ada endpoint
  SSE canonical sungguhan. Saat ini Timeline (`WorkflowPage.tsx`) masih
  polling `POST /api/v1/orchestrator/run` yang **sinkron** (blocking sampai
  workflow selesai, bukan event per-langkah) — real-time granular belum
  ada.
- **`api/routes/monitoring.py`/`memory.py`/`knowledge.py` tidak dipasangi
  RBAC** — sama seperti `orchestrator.py` (kecuali endpoint decide
  approval), ketiganya terbuka tanpa autentikasi. Konsisten dengan gap RBAC
  yang sudah dicatat di bawah, bukan regresi baru — tapi `memory.py`
  patut disorot: siapa pun yang tahu `session_id` orang lain bisa membaca/
  menghapus memori sesi itu tanpa otorisasi sama sekali.
- **UI Multi-Agent baru mencakup jalur run+approve** (Tahap 11), kini juga
  Monitoring (Tahap 12); ChatEngine (`core/chat/`) dan Orchestrator tetap
  dua sistem terpisah tanpa jembatan — pengguna memilih salah satu lewat
  tab, tools file (baca/tulis/GIS) tetap hanya ada di jalur Chat.
- **RBAC ke `agent/tools/` SELESAI untuk semua tool `write_*`/`convert_geo`/
  `generate_code`** (Tahap 10 pilot `write_pdf` + Tahap 18 menyelesaikan
  sisanya) — gap lama ini sudah tertutup. Yang masih terbuka: tool image
  (`image_*`/`images_to_pdf`, keputusan sadar — profil risiko beda, lihat
  Tahap 18 di atas) dan tool baca (`read_*`). **`core/chat/engine.py`
  (ChatEngine) kini tersambung ke RBAC (Tahap 20)** — gap lama "gate ini
  masih inert untuk semua panggilan dari Chat" sudah tertutup, lihat detail
  Tahap 20 di atas; identitas tetap per-*request* (dari `X-API-Key`), bukan
  per-sesi tersimpan — kepemilikan `session_id` sendiri tetap terbuka
  (gap terpisah, lihat Tahap 20). Rute API selain yang sudah opt-in RBAC
  (`/api/v1/agent/run`, `/api/v1/chat/stream`, `projects`, `workspace`)
  masih terbuka tanpa autentikasi.
- **Circuit Breaker SELESAI untuk provider** (Tahap 9, ADR-0012); sasaran
  kedua Bab 55 (`tools/tool_executor.py`) belum ada foldernya di repo —
  saat `tools/` dibangun, pakai registry yang sama dengan key nama tool.
  Counter breaker read-modify-write (bukan HINCRBY atomik) — race kecil
  antar pod diterima, dicatat di ADR-0012.
- **RAG belum otomatis** — `Retriever`/`build_context`/`llm_rerank()` (Tahap 5)
  ada dan teruji tapi tak dikaitkan otomatis ke setiap dispatch Orchestrator
  — pemanggil pakai eksplisit saat butuh (Bab 29 rule 4: pengaya opsional).
- **Dockerfile multi-stage SELESAI (Bab 37 rule 2, Tahap 21)** — gap ini
  (dicatat sejak ADR-0011) sudah tertutup; `.dockerignore` baru sekalian
  menutup temuan keamanan nyata (`.env` sungguhan ter-bake ke image
  sebelumnya). Image turun 2.83GB→699MB. Lihat detail Tahap 21 di atas.
- **Postgres/Redis single-instance** — tidak ada operator HA (Patroni/
  CloudNativePG untuk Postgres, Sentinel/Cluster untuk Redis) baik di
  `docker-compose.yml` maupun `k8s/`. Dicatat sejak ADR-0011.
- **Verifikasi cluster K8s sungguhan SELESAI** (2026-07-05, `kind` lokal —
  lihat addendum ADR-0011); prasyarat sebelum produksi sungguhan yang masih
  tersisa: build+push image ke registry nyata, isi `secret.yaml` dengan nilai
  asli via metode di header filenya, sediakan StorageClass RWX kalau mau
  API >1 replika (lihat gap RWX di atas).
- **`MESSAGE_BROKER=redis`'s race condition** (dicatat ADR-0009) — cost
  budget check di `Orchestrator.run()` mengasumsikan pengiriman event
  sinkron; perlu ditinjau ulang sebelum multi-instance paralel dengan
  broker Redis (bukan `MESSAGE_BROKER=memory` yang jadi default saat ini).
- **CI (`.github/workflows/ci.yml`)** masih cuma `pytest --cov` — belum
  build/push image container atau apply manifest K8s.

## Titik mulai sesi berikutnya (di luar roadmap 8-tahap awal)
Roadmap `MASTER_INSTRUCTION.md`/`DEVELOPMENT_ROADMAP.md` selesai seluruhnya;
Circuit Breaker (ADR-0012), RBAC pilot ke `agent/tools/` (ADR-0013), UI
Multi-Agent (Tahap 11), Frontend AI Workspace + Monitoring/Memory/Knowledge
(Tahap 12), Projects (Tahap 13), Vision (Tahap 14), Automation (Tahap 15),
Plugin (Tahap 16), MCP Client (Tahap 17), migrasi RBAC penuh ke
`write_*`/`convert_geo`/`generate_code` (Tahap 18, ADR-0013 selesai
ditutup), Project Workspace & Folder Access (Tahap 19, Bab 69/ADR-0005,
hand-off Cowork), sambungkan RBAC ke ChatEngine (Tahap 20), Dockerfile
multi-stage (Tahap 21, ADR-0011 gap ditutup), kepemilikan sesi Chat
(Tahap 22), Agent Workspace Context ke ChatEngine (Tahap 23, Bab 69.5),
kepemilikan file download Chat (Tahap 24), autentikasi+fix traversal
`api/routes/files.py` (Tahap 25), autentikasi
`memory.py`/`monitoring.py`/`knowledge.py` (Tahap 26), loose ends
Docker — `tesseract-ocr`/`HEALTHCHECK` (Tahap 27), MCP Server, Bab 60
sisi sebaliknya dari Client (Tahap 28), dan gambar/GIS Workspace via Chat
(Tahap 29, Bab 69.5 Vision) semua selesai 2026-07-06. **Seluruh 5 area
Phase 3 (`PROJECT_SPECIFICATION.md`) kini punya kode nyata**, ditambah
kapabilitas Workspace baru di atasnya, gate RBAC kini benar-benar hidup di
satu-satunya jalur yang mengeksekusi tool (Chat), sesi Chat DAN file hasil
kerjanya (di kedua rute yang menyajikannya) DAN memori/monitoring/knowledge
kini terikat autentikasi, Chat kini bisa membaca Project Workspace DAN
melihat gambar/menghitung luas GIS-nya (bukan cuma dokumen teks), image
Docker turun 2.83GB→699MB dengan bug keamanan nyata (`.env` ter-bake ke
image) tertutup sekalian, OCR+HEALTHCHECK Docker kini nyata bekerja, dan
AI_ENGINE kini bisa jadi MCP Server sungguhan (bukan cuma Client) untuk
client eksternal manapun. **Dicek ulang sebelum ditulis di sini** (bukan
diasumsikan dari catatan lama): `projects.py` TERNYATA sudah punya
`Depends(get_current_principal)` di SETIAP rute sejak Tahap 13 — catatan
gap lama yang bilang "endpoint projects.py masih terbuka" sudah basi,
diperbaiki di bagian "Untuk lanjutan frontend" di bawah; bagian "Gap
kumulatif" Tahap 19 masih menyimpan klaim basi "ChatEngine belum
workspace-aware" yang sudah salah sejak Tahap 23 — dikoreksi Tahap 27; dan
bagian "Gap kumulatif" Tahap 17 masih menyimpan klaim basi "RBAC mcp:call
inert dari Chat" yang sudah salah sejak Tahap 20 — dikoreksi Tahap 28.
**Koreksi cakupan Tahap 29 sebelum coding**: opsi yang ditawarkan
menyebut "Chat DAN MCP Server" untuk gambar/GIS Workspace — TIDAK akurat,
`mcp_server/server.py` (Tahap 28) sengaja mengecualikan tool Workspace
sama sekali, jadi Tahap 29 murni ChatEngine (lihat detail di atas).
Kandidat prioritas berikutnya, dari yang paling murah dieksekusi: (1)
solusi storage RWX (StorageClass NFS/Longhorn atau pindah ke object
storage) kalau memang butuh API >1 replika di produksi; (2) Bab 68
Enterprise Architecture Backlog (20 prioritas di
`DEVELOPMENT_ROADMAP.md`) — belum satupun dimulai; (3) akses Workspace
lewat MCP Server (gap yang ditemukan+didokumentasikan saat Tahap 29 —
`mcp_server/server.py` tak punya sesi ChatEngine untuk menyuntikkan
`workspace_id`, butuh mekanisme otorisasi baru untuk pemanggil eksternal
yang beda dari pola sesi Chat); (4) heartbeat RQ yang lebih tepat untuk
`HEALTHCHECK` worker (Tahap 27 cuma menjamin konektivitas Redis, bukan
bahwa `worker.work()` sungguh memproses job); (5) transport SSE/HTTP
untuk MCP Server (Tahap 28 sengaja stdio-saja, server jaringan butuh
tinjauan auth+path-sandboxing sendiri) — ketiga item terakhir kecil/
menengah, cuma relevan kalau ada kebutuhan konkret (produksi bermasalah,
atau client MCP eksternal butuh Workspace/akses jarak jauh).

**Untuk lanjutan frontend/Phase 2-3 spesifik**: (a) Memory page kini
terwire tapi kosong sampai ChatEngine↔`memory/` diintegrasikan (strangler
pattern ke `core/chat/engine.py`) — pekerjaan backend belum dimulai; (b)
Knowledge page kini bisa ingest+cari tapi cuma teks tempel — upload
file/OCR, embedder sungguhan (ganti `hashed_bow_embedder` offline), dan
delete-by-dokumen di `KnowledgeStore` semua masih terbuka; (c)
Timeline/Approval versi penuh — butuh endpoint SSE canonical baru
(`EVENT_CATALOG.md`) menggantikan polling `POST /run` sinkron saat ini; (d)
RBAC untuk `monitoring.py`/`memory.py`/`knowledge.py` SELESAI (Tahap 26,
lihat detail di atas). **Koreksi catatan lama**: `projects.py` TERNYATA
sudah punya `Depends(get_current_principal)` di setiap rute sejak Tahap
13 (dicek ulang saat menulis Tahap 26, bukan diasumsikan) — klaim
sebelumnya di sini bahwa "endpoint projects.py masih terbuka" salah/basi,
RBAC per-resource internalnya SUDAH dijaga otentikasi endpoint-level
juga, tak ada tindak lanjut dibutuhkan; (e) Project belum
terhubung ke Conversation/File sungguhan (Tahap 13, keputusan lanjutan
yang sengaja ditunda); (f) Vision (Tahap 14) belum diverifikasi live ke
provider cloud sungguhan (Gemini/OpenAI/Claude) dengan gambar nyata — baru
bentuk payload yang teruji; (g) Automation (Tahap 15) SELESAI dan
diverifikasi live termasuk auto-fire background tanpa interaksi manual —
gap tersisa cuma RBAC-di-atas-ownership dan ketiadaan sintaks cron (lihat
"Gap kumulatif" di atas); (h) Plugin (Tahap 16) SELESAI — satu plugin nyata
(`weather`) diverifikasi live lewat Chat tool-calling + Settings toggle;
gap tersisa cuma state in-memory (bukan persisten) dan baru satu kategori
plugin dari yang dicontohkan Bab 59.2; (i) MCP Client (Tahap 17) SELESAI —
diverifikasi live lewat Chat memanggil tool `add` di server demo sungguhan
(protokol MCP asli via SDK resmi, bukan mock); gap tersisa: baru sisi
Client (bukan Server, keputusan skop sadar), baru satu server
terkonfigurasi (fixture dev, belum tersambung ke MCP server pihak ketiga
sungguhan), dan sesi tak persisten (satu koneksi baru per panggilan).
**Seluruh 5 area Phase 3 kini punya kode nyata**, tak ada lagi yang nol
kode sama sekali. (j) Project Workspace (Tahap 19) SELESAI — diverifikasi
live lewat scan+index folder sungguhan dan RAG search sungguhan menemukan
isinya (lihat detail Tahap 19 di atas); `WorkspacePage.tsx` sendiri belum
pernah diklik di browser sungguhan (tidak ada Playwright/Cypress di repo
ini), baru `npm run build`/code review; UI belum menampilkan pesan error
per-folder dari `errors` (`workspace_dashboard`) atau progres granular
Scanning→Active (halaman perlu di-refresh manual, belum polling otomatis).

**Untuk lanjutan Workspace (Tahap 19) spesifik**: (a) folder sumber baru
Local — Network/Server/Cloud/SharePoint/OneDrive/GDrive/S3 (Bab 69.16,
Backlog Prioritas 21-29) nol disentuh; (b) `core/chat/engine.py` belum
tersambung ke Workspace sama sekali — Agent Workspace Context (Bab 69.5)
murni backend/API hari ini, ChatEngine masih hanya tahu Uploaded Files;
(c) tidak ada cache counts persisten — `workspace_dashboard()`/`GET
.../status` re-scan filesystem tiap panggilan (O(files on disk)), jadi
akan melambat untuk Workspace besar; kandidat solusi: kolom
`document_count`/`image_count`/`gis_count`/`size_bytes` ter-materialisasi
di `Workspace`, diperbarui hanya saat `POST .../scan` (selaras Bab 68
Prioritas 23, Incremental Index); (d) WorkspacePage.tsx polling status
manual (tombol Scan/Index), belum auto-poll `GET .../status` ala
`workflowStore.applyEvent()`.

