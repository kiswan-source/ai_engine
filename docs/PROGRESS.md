# AI_ENGINE v4 — Catatan Progres & Resume

> Catatan lanjutan pembangunan enterprise multi-agent per `MASTER_INSTRUCTION.md`
> (tersimpan di `D:\01_Project\AI ENGINE` = `/mnt/d/01_Project/AI ENGINE`).
> Sumber kebenaran = MASTER_INSTRUCTION.md (67 Bab) + 9 dokumen pendamping.

## Status per 2026-07-05

| Tahap | Fokus | Status |
|---|---|---|
| 1 | Provider Layer + Registry | ✅ SELESAI |
| 2 | Orchestrator + Workflow (sequential, parallel) | ✅ SELESAI |
| 3 | Shared Memory + Message Bus (Redis/Postgres) | ✅ SELESAI |
| 4 | Reflection / Consensus / Confidence / Human Approval | ✅ SELESAI |
| 5 | RAG penuh (chunker→embed→store→retrieve→hybrid→rerank→context) | ✅ SELESAI |
| 6 | Observability + Cost | ⏭️ BERIKUTNYA |
| 7 | Security hardening | belum |
| 8 | Kubernetes ready | belum |

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
- **Ditemukan, di luar cakupan Tahap 5**: tabel `documents` (dibuat
  `scripts/init_db.sql` lama dengan `id UUID`) tak cocok dengan
  `db.models.Document.id` (`String(36)`) — INSERT lewat SQLAlchemy ORM gagal.
  Bug lama, baru ketahuan saat mencoba index row `Document` sungguhan untuk
  verifikasi. Belum diperbaiki — di luar lingkup RAG.

## Test
- **166/166 lulus** (`pytest -q`). Baru Tahap 5: `tests/unit/test_rag.py` (25
  test — chunker, embeddings dengan fallback, InMemoryKnowledgeStore,
  retriever + index_document, hybrid_search, rerank + llm_rerank (mocked),
  context_builder) + 2 test baru di `test_providers.py` (Claude sampling-param
  retry). Semua CI-safe (hashed-BOW/stub, bukan panggilan live) — backend
  pgvector/provider nyata diverifikasi live terpisah (lihat di atas), sama
  seperti PostgresConversationStore/PostgresLongTermStore Tahap 3 tak
  di-unit-test langsung.

## Catatan penting untuk sesi berikutnya
- Tahap 1-5 **sudah di-commit** ke `main` (per tahap/topik, lihat `git log`).
- Cloud API key AKTIF (bukan cuma Ollama lagi) — role apa pun yang dirutekan
  ke openai/claude/gemini akan benar-benar keluar biaya. Jika perlu murni
  offline lagi, kosongkan key di `.env` (Model Registry otomatis fallback ke
  Ollama, Bab 54).
- `VECTOR_BACKEND=pgvector` aktif di `.env` lokal — Vector Memory & RAG
  korpus keduanya nyata sekarang, bukan in-memory. Default `.env.example`
  tetap `memory` untuk CI/dev baru; produksi eksplisit set `pgvector`.
- Batas sengaja: `llm_rerank()` ada tapi tak otomatis dipasang (biaya/latensi
  per query); RAG belum dikaitkan otomatis ke setiap dispatch Orchestrator —
  pemanggil pakai `Retriever`/`build_context` eksplisit saat butuh (Bab 29
  rule 4: RAG itu pengaya opsional, bukan wajib). Cost Tracking (Bab 27)
  masih 0.0 di mana-mana (→ Tahap 6).

## Titik mulai Tahap 6
Bangun Observability + Cost (Bab 27, 33-35): `telemetry/cost_tracker.py`
(catat biaya token per agent/provider/task — provider layer sudah punya
`prompt_tokens`/`completion_tokens` di `ProviderResponse`, tinggal dikalikan
tarif per model), dashboard minimum (Bab 62) di atas event yang sudah mengalir
sejak Tahap 3 (`agent.*`/`workflow.*`/`consensus.decided`), dan cost budget
per-task/sesi yang memicu penghentian/eskalasi (bukan berjalan tanpa batas) —
titik integrasi alami: Dispatcher (sudah emit event tiap percobaan) dan
Human Approval gate (Bab 61.2 — biaya lampaui budget = wajib approval).
