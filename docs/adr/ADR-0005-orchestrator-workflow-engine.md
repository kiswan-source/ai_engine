# ADR-0005: Orchestrator & Workflow Engine (Sequential + Parallel)

| Field | Isi |
|---|---|
| Nomor | ADR-0005 |
| Judul | Orchestrator multi-agent + Workflow Engine dasar (sequential, parallel) |
| Status | Accepted |
| Tanggal | 2026-07-04 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 18, 24, 49, 53, 54; DEVELOPMENT_ROADMAP.md Tahap 2 |

## Latar Belakang

Setelah Provider Layer (ADR-0001), sistem butuh lapisan koordinasi yang memilih
agent, menjalankan task dalam pola tertentu, dan melacak status end-to-end —
tanpa men-hardcode provider/urutan di endpoint (Bab 18, 53).

## Permasalahan

Tanpa orchestrator, setiap alur multi-agent akan menyalin logika routing, retry,
dan chaining di banyak tempat, melanggar SOLID/DRY dan menyulitkan penambahan
pola workflow baru.

## Keputusan

Bangun `orchestrator/` sebagai otak koordinasi (Bab 18) + `workflows/` untuk pola
eksekusi (Bab 24). Tahap 2 dibatasi pada **Sequential** dan **Parallel** sesuai
Roadmap. Semua akses agent lewat Agent Registry (Bab 19) → Routing Engine (Bab 53)
→ Dispatcher (Fallback Bab 54). State task/workflow mengikuti state machine Bab 49.

## Alternatif yang Dipertimbangkan

1. Menaruh logika orkestrasi di dalam `api/routes/*` — ditolak (mencampur HTTP dgn
   business logic, melanggar Bab 8 & 18).
2. Membangun seluruh 8 pola workflow sekaligus — ditolak; incremental per Roadmap
   (Bab 3), Reflection/Consensus/Voting/Approval menyusul di Tahap 4.
3. LLM-driven planner sejak awal — ditunda; planner rule-based dulu (Bab 18) untuk
   menghindari halusinasi & biaya, LLM planner sebagai evolusi berikutnya.

## Trade-off

Lapisan orkestrasi menambah komponen baru untuk dipelihara, terbayar oleh
extensibility: pola/agent/provider baru masuk tanpa mengubah endpoint.

## Konsekuensi

- Orchestrator stateless di proses; state di Task Manager (in-memory kini, dapat
  diganti Redis pada Tahap 3 tanpa mengubah pemanggil, Bab 18.2).
- Komunikasi antar-agent Tahap 2 masih in-process; Message Bus (Bab 23) menyusul
  di Tahap 3 tanpa mengubah kontrak `Dispatcher.dispatch`.

## Catatan Implementasi (Tahap 2)

- **Domain (DDD, Bab 4.4):** `agents/base_agent.py` — `Task`, `AgentResult`,
  `BaseAgent` (sesuai AGENT_SPECIFICATION §5: output/confidence/trace_id/
  provider_used/cost). `agents/generic_agent.py` — `GenericLLMAgent` role-driven,
  provider via `create_for_role` (Bab 16.2).
- **Registry:** `registry/agent_registry.py` (Bab 19) — agent wajib terdaftar
  sebelum dapat dipanggil; `build_default_agent_registry()` mendaftarkan 15 peran.
- **Orchestrator:** `planner.py` (rule-based, Bab 18), `routing_engine.py`
  (Bab 53, peta task_type→role), `dispatcher.py` (Fallback: retry backoff →
  switch ke fallback lokal → degraded flag, Bab 54), `execution_graph.py` (DAG +
  Kahn topological layering), `task_manager.py` (state machine Bab 49 dgn validasi
  transisi), `orchestrator.py` (entry `run`/`run_single`).
- **Workflows:** `workflows/base.py` (`BaseWorkflow`, `WorkflowResult` — modul
  internal pendamping, bukan perubahan struktur resmi), `sequential.py` (chaining
  output antar-langkah), `parallel.py` (`asyncio.gather(return_exceptions=True)`,
  Bab 9 — kegagalan satu langkah tidak membatalkan sibling).
- **Confidence** masih heuristik placeholder (Bab 28 penuh di Tahap 4); **cost**
  masih 0.0 (Cost Tracker Bab 27 di Tahap 6).

Cakupan test: `tests/unit/test_orchestrator.py` (21 test, agent di-stub, tanpa
jaringan, Bab 12.3). Diverifikasi end-to-end melalui Ollama nyata (model
`qwen2.5:3b`): workflow sequential menghasilkan output berantai, state `completed`.
