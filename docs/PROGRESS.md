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
| 12* | Frontend AI Workspace (React) Phase 1 + Monitoring dashboard (Phase 2 parsial) | ✅ SELESAI |

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

## Test
- **Backend: 308/308 lulus** (`pytest -q`, tidak berubah dari Tahap 11 —
  Tahap 12 murni frontend + satu route baru tipis tanpa test Python
  tambahan; `api/routes/monitoring.py` diverifikasi via curl + browser
  langsung, bukan pytest). Baru Tahap 10: 12 test (lihat di atas). Baru
  Tahap 11: 9 test integrasi `tests/integration/test_orchestrator_api.py`
  (roles/modes, tolak roles kosong/mode tak dikenal, sequential selesai,
  eskalasi reflection masuk daftar approval, decide menyelesaikan/menolak,
  404 trace_id tak dikenal, 403 role tak cukup) — agent distub persis pola
  `tests/unit/test_orchestrator.py`, nol panggilan provider sungguhan.
- **Frontend (`web/`): 5/5 lulus** (`npm test`, Vitest + React Testing
  Library) — `workflowStore.applyEvent()`/`setFromRunResult()` dan
  `ApprovalCard` interaksi. `npm run lint`/`npm run build` hijau.

## Gap kumulatif (Tahap 1-12, diakui bukan disamarkan)
- **Dashboard observability kini ADA di web UI (Tahap 12, menutup gap sejak
  Tahap 6)** — `MonitoringPage.tsx` + `api/routes/monitoring.py`, 7 dari 8
  dashboard Bab 62. Yang masih gap: **Memory Dashboard** (field ke-5
  `vector_entries` butuh instance `VectorMemory` yang tak berguna tanpa
  integrasi ChatEngine↔memory/ — lihat bawah); **Execution Timeline**
  (`Tracer.timeline(trace_id)`) belum ada di UI sama sekali, dan tak bisa
  didaftar tanpa `trace_id` diketahui dulu (tak ada method "list semua
  trace_id").
- **ChatEngine (`core/chat/`) dan `memory/` (Tahap 3) dua sistem terpisah
  total** — bukan sekadar "belum ada route API" seperti diasumsikan
  `IMPLEMENTATION_BLUEPRINT.md`. `core/chat/engine.py` (fondasi terlindungi)
  tidak pernah menulis ke `memory/` tier manapun; keenam tier `memory/` juga
  tidak punya method enumerasi sesi/scope di tier manapun (working/
  conversation/summary/long-term/reflection — semua butuh scope/session_id/
  namespace diketahui dulu, cuma Vector Memory yang punya `count()`).
  Frontend `Memory` page tetap placeholder karena diwire sekarang = selalu
  kosong. Mengisi gap ini butuh (a) integrasi ChatEngine→memory/ (strangler
  pattern, sentuh fondasi hati-hati) DAN/ATAU (b) tambah method enumerasi ke
  tiap tier — dua pekerjaan backend terpisah, belum dimulai.
- **`rag/` (Tahap 5) nol wiring ke endpoint HTTP manapun** — bukan cuma
  frontend yang kurang. Tidak ada route ingest dokumen, tidak ada route
  list sumber pengetahuan; `KnowledgeStore` sendiri tidak punya method
  "list semua namespace/dokumen". Frontend `Knowledge` page tetap
  placeholder — butuh keputusan desain produk (UX ingest: upload file?
  paste teks? chunking otomatis?) sebelum jadi tugas coding.
- **`services/eventStream.ts` (frontend) ditulis tapi belum dipakai** —
  mengikuti kontrak `EVENT_CATALOG.md` (event kanonis PascalCase:
  `WorkflowCreated`/`AgentStarted`/dst.), siap pasang begitu ada endpoint
  SSE canonical sungguhan. Saat ini Timeline (`WorkflowPage.tsx`) masih
  polling `POST /api/v1/orchestrator/run` yang **sinkron** (blocking sampai
  workflow selesai, bukan event per-langkah) — real-time granular belum
  ada.
- **`api/routes/monitoring.py` tidak dipasangi RBAC** — sama seperti
  `orchestrator.py` (kecuali endpoint decide approval), rute ini terbuka
  tanpa autentikasi. Konsisten dengan gap RBAC yang sudah dicatat di bawah,
  bukan regresi baru.
- **UI Multi-Agent baru mencakup jalur run+approve** (Tahap 11), kini juga
  Monitoring (Tahap 12); ChatEngine (`core/chat/`) dan Orchestrator tetap
  dua sistem terpisah tanpa jembatan — pengguna memilih salah satu lewat
  tab, tools file (baca/tulis/GIS) tetap hanya ada di jalur Chat.
- **RBAC ke `agent/tools/` dimulai** (Tahap 10, ADR-0013) tapi baru
  `write_pdf`; `write_docx`/`write_html`/`write_txt`/`write_json`/
  `write_geojson`/`write_shp`/`convert_geo`/`generate_code` masih terbuka
  untuk role apa pun. `core/chat/engine.py` (ChatEngine) sama sekali belum
  tersambung ke RBAC — tidak ada konsep identitas per sesi chat untuk
  dipetakan ke role. Rute API selain `/api/v1/agent/run` masih terbuka
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
Multi-Agent (Tahap 11), dan Frontend AI Workspace + Monitoring (Tahap 12)
semua selesai 2026-07-05. Kandidat prioritas berikutnya, dari yang paling
murah dieksekusi: (1) lanjutkan migrasi RBAC ke tool `write_*`/`convert_geo`
lain satu per satu (pola sama seperti ADR-0013, tinggal tambah entri
`TOOL_RISK_ACTIONS`); (2) Dockerfile multi-stage dengan rebuild+verifikasi
live penuh (bukan cuma review kode) mengingat riwayat insiden ADR-0009;
(3) solusi storage RWX (StorageClass NFS/Longhorn atau pindah ke object
storage) kalau memang butuh API >1 replika di produksi; (4) Bab 68
Enterprise Architecture Backlog (20 prioritas di `DEVELOPMENT_ROADMAP.md`)
— belum satupun dimulai.

**Untuk lanjutan frontend spesifik (Phase 2 sisa + Phase 3)**: (a) Memory
page — butuh keputusan scope dulu (integrasi ChatEngine↔`memory/` vs.
method enumerasi per tier vs. skip); (b) Knowledge page — butuh desain
UX ingest dokumen dulu sebelum `api/routes/knowledge.py` dibangun; (c)
Timeline/Approval versi penuh — butuh endpoint SSE canonical baru
(`EVENT_CATALOG.md`) menggantikan polling `POST /run` sinkron saat ini;
(d) Phase 3 (Projects/Plugin/Automation/Vision/MCP) — semua masih
`NOT IMPLEMENTED` di backend, lihat `PROJECT_SPECIFICATION.md` untuk desain
awal entity Project.

