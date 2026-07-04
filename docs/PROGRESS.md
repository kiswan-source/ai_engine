# AI_ENGINE v4 — Catatan Progres & Resume

> Catatan lanjutan pembangunan enterprise multi-agent per `MASTER_INSTRUCTION.md`
> (tersimpan di `D:\01_Project\AI ENGINE` = `/mnt/d/01_Project/AI ENGINE`).
> Sumber kebenaran = MASTER_INSTRUCTION.md (67 Bab) + 9 dokumen pendamping.

## Status per 2026-07-04

| Tahap | Fokus | Status |
|---|---|---|
| 1 | Provider Layer + Registry | ✅ SELESAI |
| 2 | Orchestrator + Workflow (sequential, parallel) | ✅ SELESAI |
| 3 | Shared Memory + Message Bus (Redis/Postgres) | ✅ SELESAI |
| 4 | Reflection / Consensus / Confidence | ⏭️ BERIKUTNYA |
| 5 | RAG penuh | belum |
| 6 | Observability + Cost | belum |
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
  (PostgreSQL `memory_entries`, upsert), vector (hashed-BOW placeholder → Tahap 5),
  reflection (jurnal per peran, capped) + `memory_manager.py` (facade/factory dari
  `MEMORY_BACKEND` + `MEMORY_PERSISTENT_BACKEND`).
- Integrasi: Orchestrator publish `workflow.<state>` di tiap transisi; Dispatcher
  publish `agent.assigned/running/retry/completed/failed` (exit criteria Tahap 3).
  `TaskManager` dapat seam `TaskStore` → `RedisTaskStore` (klien sync, TTL) via
  `TASK_STATE_BACKEND=redis`, kontrak tidak berubah.
- **Bugfix fondasi:** `init_db()` tidak pernah membuat tabel (db.models tak pernah
  di-import siapa pun) — kini `init_db()` meng-import `db.models` sebelum `create_all`.

## Test
- **109/109 lulus** (`pytest -q`). Baru: `tests/unit/test_messaging.py`,
  `test_memory.py`, + 3 test Tahap 3 di `test_orchestrator.py`. Semua broker/
  redis/postgres di-fake (Bab 12.3) — CI tetap tanpa layanan hidup.
- Diverifikasi live (WSL): Working Memory di Redis nyata; event lifecycle utuh
  diterima subscriber via Redis Pub/Sub; Conversation + Long-Term di Postgres
  nyata (insert/history/upsert/forget); e2e orchestrator dengan Ollama
  `qwen2.5:3b` → 7 event lifecycle terkirim, state `completed` tersimpan di Redis.

## Catatan penting untuk sesi berikutnya
- **Belum ada commit** — semua perubahan Tahap 1–3 masih di working tree.
  Pertimbangkan commit (Conventional Commits, Bab 14); saran branch:
  `feature/orchestrator`.
- Default config sengaja service-free (`memory`); produksi set di `.env`:
  `MESSAGE_BROKER=redis`, `MEMORY_BACKEND=redis`,
  `MEMORY_PERSISTENT_BACKEND=postgres`, `TASK_STATE_BACKEND=redis`.
- Hanya **Ollama** aktif (belum ada API key cloud) → peran cloud fallback ke
  Ollama lokal (Bab 54). `gemma4:e2b` masih mengembalikan output kosong
  (kuirk model); pakai `qwen2.5:3b`/`gemma4:26b` untuk verifikasi live.
- Batas sengaja: Vector Memory = hashed-BOW placeholder (embedding nyata +
  vector store → Tahap 5); Confidence heuristik (→ Tahap 4); cost 0.0 (→ Tahap 6).

## Titik mulai Tahap 4
Bangun Reflection Engine (`orchestrator/reflection.py` + `workflows/reflection.py`,
Bab 25 — konsumsi `ReflectionMemory` dari Tahap 3), Consensus Engine
(`orchestrator/consensus.py` + `workflows/voting.py`/`consensus.py`, Bab 26 —
publish `consensus.decided` yang sudah didefinisikan di `messaging/events.py`),
dan Confidence Scoring nyata (Bab 28) menggantikan heuristik di
`agents/generic_agent.py`, terhubung ke gerbang Human Approval (`workflows/approval.py`).
