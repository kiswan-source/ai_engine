# AI_ENGINE v4 — Catatan Progres & Resume

> Catatan lanjutan pembangunan enterprise multi-agent per `MASTER_INSTRUCTION.md`
> (tersimpan di `D:\01_Project\AI ENGINE` = `/mnt/d/01_Project/AI ENGINE`,
> **bukan** di `docs/` repo git ini — dua lokasi berbeda).
> Sumber kebenaran = MASTER_INSTRUCTION.md (v1.3, 68 Bab) + 16 dokumen pendamping
> (9 backend, 2 product-facing, 5 implementation-facing dari FINAL ARCHITECTURE
> DECISION 5 Juli 2026).

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

## Test
- **Backend: 409/409 lulus** (`pytest -q`) — naik dari 384 lewat 25 test
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

## Gap kumulatif (Tahap 1-18, diakui bukan disamarkan)
- **MCP Client (Tahap 17) cuma Client, bukan Server** — keputusan skop
  sadar (dipilih Boss lewat `AskUserQuestion`); AI_ENGINE tidak bisa
  dikonsumsi client MCP eksternal (mis. Claude Desktop) sampai sisi Server
  dibangun terpisah. **Baru satu server terkonfigurasi** (`demo`, fixture
  dev murni untuk pembuktian) — belum tersambung ke MCP server pihak
  ketiga sungguhan manapun; nambah server nyata baru tinggal satu baris
  di `MCP_SERVERS` tapi belum ada yang dipilih/diverifikasi. **Session
  Management minimal** — satu koneksi baru per panggilan (bukan
  persisten/pooled), jadi tiap panggilan bayar biaya spawn subprocess;
  untuk pemakaian intensif ini perlu ditinjau ulang. **RBAC `mcp:call`
  inert dari Chat** (`core/chat/` tak mengirim role) — gap yang sama
  persis dengan `write_pdf`/`plugin_weather`, bukan regresi baru. Tidak
  ada rate-limit/timeout eksplisit di `MCPClient` di luar default SDK.
  **Dependency `mcp` menaikkan `pydantic` (2.10.3→2.13.4) dan mengunci
  `starlette==0.41.3`** — sudah diverifikasi 384 test lama tetap lulus dan
  service live tetap sehat setelah bump, tapi ini transitive-dependency
  footprint baru yang perlu diingat saat upgrade FastAPI/pydantic
  berikutnya.

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
  Tahap 18 di atas) dan tool baca (`read_*`). `core/chat/engine.py`
  (ChatEngine) sama sekali belum tersambung ke RBAC — tidak ada konsep
  identitas per sesi chat untuk dipetakan ke role, jadi gate ini masih
  inert untuk semua panggilan dari Chat (satu-satunya jalur yang benar
  eksekusi tool untuk plugin/MCP, lihat Tahap 16-17). Rute API selain
  `/api/v1/agent/run` masih terbuka
  tanpa autentikasi.
- **Circuit Breaker SELESAI untuk provider** (Tahap 9, ADR-0012); sasaran
  kedua Bab 55 (`tools/tool_executor.py`) belum ada foldernya di repo —
  saat `tools/` dibangun, pakai registry yang sama dengan key nama tool.
  Counter breaker read-modify-write (bukan HINCRBY atomik) — race kecil
  antar pod diterima, dicatat di ADR-0012.
- **RAG belum otomatis** — `Retriever`/`build_context`/`llm_rerank()` (Tahap 5)
  ada dan teruji tapi tak dikaitkan otomatis ke setiap dispatch Orchestrator
  — pemanggil pakai eksplisit saat butuh (Bab 29 rule 4: pengaya opsional).
- **Dockerfile belum multi-stage (Bab 37 rule 2)** — `docker/Dockerfile.api`/
  `Dockerfile.worker` install build tooling ke image final. Dicatat sejak
  ADR-0011.
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
Plugin (Tahap 16), MCP Client (Tahap 17), dan migrasi RBAC penuh ke
`write_*`/`convert_geo`/`generate_code` (Tahap 18, ADR-0013 selesai
ditutup) semua selesai 2026-07-05/06. **Seluruh 5 area Phase 3
(`PROJECT_SPECIFICATION.md`) kini punya kode nyata** — MCP baru sisi
Client (bukan Server, keputusan skop sadar). Kandidat prioritas
berikutnya, dari yang paling murah dieksekusi: (1) MCP Server (sisi Bab
60 yang sengaja ditunda Tahap 17); (2) Dockerfile multi-stage dengan
rebuild+verifikasi live penuh (bukan cuma review kode) mengingat riwayat
insiden ADR-0009; (3) solusi storage RWX (StorageClass NFS/Longhorn atau
pindah ke object storage) kalau memang butuh API >1 replika di produksi;
(4) Bab 68 Enterprise Architecture Backlog (20 prioritas di
`DEVELOPMENT_ROADMAP.md`) — belum satupun dimulai; (5) sambungkan RBAC ke
`core/chat/` (ChatEngine) sendiri — gap yang kini jadi satu-satunya alasan
`tool:*`/`plugin:*`/`mcp:call` masih inert untuk jalur Chat.

**Untuk lanjutan frontend/Phase 2-3 spesifik**: (a) Memory page kini
terwire tapi kosong sampai ChatEngine↔`memory/` diintegrasikan (strangler
pattern ke `core/chat/engine.py`) — pekerjaan backend belum dimulai; (b)
Knowledge page kini bisa ingest+cari tapi cuma teks tempel — upload
file/OCR, embedder sungguhan (ganti `hashed_bow_embedder` offline), dan
delete-by-dokumen di `KnowledgeStore` semua masih terbuka; (c)
Timeline/Approval versi penuh — butuh endpoint SSE canonical baru
(`EVENT_CATALOG.md`) menggantikan polling `POST /run` sinkron saat ini; (d)
RBAC untuk `monitoring.py`/`memory.py`/`knowledge.py`/`projects.py`
(endpoint-level; `projects.py` sudah punya RBAC per-resource internal,
tapi endpoint-nya sendiri masih terbuka) — `memory.py` khususnya berisiko
(baca/hapus data sesi tanpa otorisasi apa pun); (e) Project belum
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
kode sama sekali.

