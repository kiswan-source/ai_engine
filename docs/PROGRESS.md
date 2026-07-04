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
| 4 | Reflection / Consensus / Confidence / Human Approval | ✅ SELESAI |
| 5 | RAG penuh | ⏭️ BERIKUTNYA |
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
- **Bugfix laten:** `orchestrator/orchestrator.py` mengimpor `from workflows
  import WORKFLOWS` di level modul, dan `workflows/__init__.py` (lewat
  `consensus.py`/`reflection.py`/`voting.py`) mengimpor balik `orchestrator.*` —
  siklus ini sudah ada sejak Tahap 2 tapi baru kepegang sekarang karena
  `workflows/__init__.py` jadi lebih berat: kalau `workflows` diimpor duluan
  (mis. `from workflows.approval import ...` sebagai baris pertama test),
  `ImportError: cannot import name 'WORKFLOWS' from partially initialized
  module`. Diperbaiki dengan mengimpor `WORKFLOWS`/`HumanApprovalGate` secara
  lokal di dalam method (pola yang sama dengan
  `registry.agent_registry.build_default_agent_registry` dan
  `task_manager._default_store`), anotasi tipe tetap jalan lewat
  `from __future__ import annotations` + `TYPE_CHECKING`. Diverifikasi tahan di
  kedua urutan impor (`import workflows; import orchestrator` dan sebaliknya).

## Test
- **139/139 lulus** (`pytest -q`). Baru Tahap 4: `test_confidence.py`,
  `test_reflection.py`, `test_consensus.py`, `test_approval.py`, + 6 test
  integrasi Orchestrator (escalate→REVIEWING→finalize_approval, mode
  reflection/voting, feature flag `ENABLE_HUMAN_APPROVAL`/`ENABLE_CONSENSUS_VOTING`)
  di `test_orchestrator.py`. Semua agent tetap stub (Bab 12.3) — CI tanpa
  layanan hidup.
- Tahap 1-3 tetap 109/109 seperti sebelumnya (diverifikasi live: Redis pub/sub,
  Postgres, Ollama qwen2.5:3b e2e — lihat riwayat commit).

## Catatan penting untuk sesi berikutnya
- Tahap 1-4 **sudah di-commit** ke `main` (per tahap, lihat `git log`).
- Default config sengaja service-free (`memory`); produksi set di `.env`:
  `MESSAGE_BROKER=redis`, `MEMORY_BACKEND=redis`,
  `MEMORY_PERSISTENT_BACKEND=postgres`, `TASK_STATE_BACKEND=redis`.
- Hanya **Ollama** aktif (belum ada API key cloud) → peran cloud fallback ke
  Ollama lokal (Bab 54). `gemma4:e2b` masih mengembalikan output kosong
  (kuirk model); pakai `qwen2.5:3b`/`gemma4:26b` untuk verifikasi live —
  termasuk untuk mencoba mode `reflection`/`voting`/`consensus` end-to-end.
- Batas sengaja: Vector Memory = hashed-BOW placeholder (embedding nyata +
  vector store → Tahap 5); Confidence Scoring belum pakai sinyal guardrail
  (Bab 30 → Tahap 7); cost masih 0.0 (→ Tahap 6). Confidence Agent (role
  `confidence` di Model Registry) belum dipanggil sebagai LLM terpisah —
  ConfidenceScorer murni kode, lihat ADR-0007 alternatif yang dipertimbangkan.

## Titik mulai Tahap 5
Bangun RAG penuh (Bab 29): ganti `memory/vector_memory.py`'s embedder
hashed-BOW dengan embedding nyata (mis. via provider role `research`/`analyst`
atau model embedding lokal) + vector store sungguhan (pgvector — catatan
ADR-0006 sudah menandai ini ditunda ke sini, bukan Redis/in-memory list
seperti sekarang), retrieval pipeline yang menyuntik hasil pencarian ke prompt
sebelum dispatch, dan `Document`/`GISProject` existing sebagai sumber korpus
pertama untuk diindeks.
