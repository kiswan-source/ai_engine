# ADR-0006: Shared Memory Multi-Tier & Messaging Layer (Tahap 3)

| Field | Isi |
|---|---|
| Nomor | ADR-0006 |
| Judul | Shared Memory 6 tier (`memory/`) + Message/Event Bus & Task Queue (`messaging/`) |
| Status | Accepted |
| Tanggal | 2026-07-04 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 17.3, 22, 23, 48, 49; DEVELOPMENT_ROADMAP.md Tahap 3 |

## Latar Belakang

Tahap 2 meninggalkan tiga hal yang sengaja ditunda: dispatch in-process tanpa
event, state task hanya di memori proses, dan belum ada memori bersama
antar-agent. Roadmap Tahap 3 mensyaratkan Working Memory (Redis) +
Conversation Memory (PostgreSQL) terintegrasi, dan Event Bus yang
mempublikasikan seluruh event lifecycle agent (Bab 48) dan workflow (Bab 49).

## Permasalahan

1. CI tidak menyediakan Redis/Postgres/Ollama — semua modul baru harus tetap
   teruji tanpa layanan hidup (Bab 12).
2. Broker fisik harus bisa diganti tanpa menyentuh kontrak pesan (Bab 23
   prinsip 3).
3. Kontrak `TaskManager` (sinkron) dan `Orchestrator` tidak boleh berubah
   (janji Tahap 2, Bab 45 no big rewrite).

## Keputusan

1. **`messaging/`** — kontrak Pydantic di `schemas.py` (bentuk pesan Bab 17.3
   verbatim), nama event di `events.py` (cermin state Bab 48.1 + 49.1),
   transport di `broker.py` dengan dua adapter: `InMemoryBroker` (in-process,
   default dev/CI) dan `RedisBroker` (Pub/Sub + list). `MessageBus`
   (point-to-point/broadcast per agent), `EventBus` (publish **best-effort** —
   broker mati tidak boleh menggagalkan workflow), `TaskQueue` (FIFO untuk
   pekerjaan panjang). Pemilihan lewat `MESSAGE_BROKER=memory|redis`.
2. **`memory/`** — enam tier per Bab 22 di atas dua abstraksi store kecil
   (`stores.py`: HashStore/ListStore → in-memory atau Redis) plus store
   Postgres khusus untuk tier persisten. `MemoryManager` merakit semuanya dari
   `MEMORY_BACKEND` (volatile: memory|redis) dan `MEMORY_PERSISTENT_BACKEND`
   (memory|postgres). Tabel baru: `conversation_messages`, `memory_entries`.
3. **Vector Memory = placeholder disengaja** — embedder hashed bag-of-words
   deterministik tanpa dependency baru (Bab 45.3); antarmuka `add`/`search`
   final, implementasi embedding/vector store nyata masuk di Tahap 5 (RAG)
   di balik antarmuka yang sama.
4. **Summary Memory** menerima `summarizer` async injektabel; default memakai
   provider peran `memory` (fallback Ollama lokal) secara lazy.
5. **TaskManager** mendapat seam `TaskStore` (in-memory | `RedisTaskStore`
   dengan klien redis **sync** + TTL) — kontrak publik tak berubah;
   `TASK_STATE_BACKEND=redis` membuat state tahan restart dan bisa dibagi
   antar-instance (Bab 18.2).
6. **Orchestrator & Dispatcher** kini mempublikasikan event lifecycle:
   `workflow.<state>` pada tiap transisi state machine, dan `agent.assigned/
   running/retry/completed/failed` di jalur dispatch + fallback (Bab 54).
   EventBus dapat di-inject; default memakai broker global.

## Alternatif yang Dipertimbangkan

- **RQ/Celery untuk task queue v4** — ditolak untuk jalur agent: RQ tetap
  melayani pipeline lama; TaskQueue baru cukup list Redis tanpa dependency baru.
- **pgvector untuk Vector Memory sekarang** — ditolak: image Postgres saat ini
  belum menyediakannya dan RAG baru Tahap 5; jangan menambah infra lebih awal.
- **Async TaskManager** — ditolak: mengubah kontrak sinkron Tahap 2 dan
  merembet ke seluruh orchestrator.

## Trade-off

- Publish event inline (await) menambah latensi kecil per transisi; diterima
  karena best-effort + Redis lokal cepat, dan menjaga urutan event deterministik.
- Fallback in-memory berarti dev tanpa `.env` tidak merasakan persistensi —
  eksplisit didokumentasikan di `.env.example` (produksi wajib redis/postgres).

## Konsekuensi

- Exit criteria Tahap 3 terpenuhi (diverifikasi live: Redis pub/sub, Postgres
  conversation/long-term, Ollama qwen2.5:3b end-to-end).
- Bug laten diperbaiki: `init_db()` tidak pernah membuat tabel karena
  `db.models` tak pernah di-import; kini di-import di dalam `init_db()`.
- Tahap 4 (Reflection/Consensus) tinggal mengonsumsi `ReflectionMemory` dan
  menerbitkan `consensus.decided`; Tahap 6 (Observability) tinggal subscribe
  `agent.*`/`workflow.*`.
