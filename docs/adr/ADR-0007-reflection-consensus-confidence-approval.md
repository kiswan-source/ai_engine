# ADR-0007: Reflection Engine, Consensus Engine, Confidence Scoring & Human Approval (Tahap 4)

| Field | Isi |
|---|---|
| Nomor | ADR-0007 |
| Judul | Reflection Engine (`orchestrator/reflection.py`) + Consensus Engine (`orchestrator/consensus.py`) + Confidence Scoring nyata (`orchestrator/confidence.py`) + Human Approval gate (`workflows/approval.py`) |
| Status | Accepted |
| Tanggal | 2026-07-04 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 24, 25, 26, 28, 57, 61; DEVELOPMENT_ROADMAP.md Tahap 4 |

## Latar Belakang

Tahap 2 mengirimkan `GenericLLMAgent` dengan confidence berupa heuristik
placeholder (Bab 28 "menyusul"), dan hanya dua workflow (sequential/parallel).
Tahap 3 menyediakan Reflection Memory dan event `consensus.decided` yang belum
dipakai siapa pun. Roadmap Tahap 4 mensyaratkan Reflection Engine, Consensus
Engine, Confidence Scoring nyata, dan gerbang Human Approval yang benar-benar
terhubung ke Orchestrator/Task State Machine (Bab 49), bukan modul berdiri
sendiri.

## Permasalahan

1. Confidence yang hanya dari satu sinyal (self-reported) mudah salah percaya
   diri pada model lokal kecil — perlu sinyal tambahan tanpa panggilan LLM
   ekstra yang mahal (Bab 27 semangat, walau Cost Tracking baru Tahap 6).
2. Reflection harus punya batas iterasi tegas (Bab 25 rule 1) dan tidak boleh
   memaksakan hasil lolos begitu ambang tak tercapai (rule 3) — harus ada
   jalur eskalasi yang konsisten dengan modul lain (Voting/Consensus).
3. `workflows/` dan `orchestrator/` sudah saling impor sejak Tahap 2
   (`workflows/*.py` → `orchestrator.dispatcher`, `orchestrator/orchestrator.py`
   → `workflows.WORKFLOWS`). Menambah lebih banyak modul di kedua sisi
   membuat urutan import pertama kali (`orchestrator` dulu vs `workflows` dulu)
   rawan `ImportError: cannot import name ... from partially initialized module`.
4. Human Approval (Bab 61) harus jadi gerbang, bukan workflow yang
   "menghasilkan" jawaban dari graf seperti workflow lain di Bab 24.

## Keputusan

1. **`orchestrator/confidence.py`** — `ConfidenceScorer` membaurkan tiga sinyal
   yang benar-benar tersedia di platform ini: self-reported (heuristik
   `AgentResult.confidence` dari Bab 20), historical accuracy (rata-rata skor
   role dari `ReflectionMemory`, Bab 25), dan agreement rate (opsional, dari
   Consensus/Voting, Bab 26). Sinyal yang tak tersedia di-drop dan bobot
   sisanya dinormalisasi ulang — skor akhir selalu di `[0.0, 1.0]`. Sinyal
   guardrail/output-validator (Bab 30) **belum** dipakai — modul itu baru
   Tahap 7. `threshold_for("default"|"high")` membaca
   `CONFIDENCE_THRESHOLD_DEFAULT`/`CONFIDENCE_THRESHOLD_HIGH_RISK`.
2. **`orchestrator/reflection.py`** — `ReflectionEngine.run()` menjalankan
   generate → self-evaluate → revise hingga `REFLECTION_MAX_ITERATIONS` (default
   3), mencatat tiap iterasi ke `ReflectionMemory`, dan mengembalikan
   `ReflectionOutcome(escalate=...)` alih-alih memaksakan lolos — pemanggil
   (Orchestrator) yang memutuskan apa yang terjadi pada eskalasi.
3. **`orchestrator/consensus.py`** — `ConsensusEngine` mengimplementasikan
   Majority Voting, Weighted Voting, dan Arbitrator Model dari tabel Bab 26;
   Structured Debate diimplementasikan satu lapis di atas
   (`workflows/consensus.py`) karena butuh me-redispatch task lintas ronde,
   bukan cuma memutuskan pemenang. Setiap keputusan menerbitkan
   `consensus.decided` (event yang sudah didefinisikan sejak Tahap 3).
4. **Tiga workflow baru** didaftarkan di `workflows.WORKFLOWS`:
   `reflection` (chaining seperti sequential, tiap step lewat
   `ReflectionEngine`), `voting` (dispatch independen lalu majority vote),
   `consensus` (`CONSENSUS_DEBATE_ROUNDS` ronde debat lalu arbitrase). Semua
   mengembalikan `WorkflowResult.escalate=True` ketika confidence/agreement
   tidak mencapai ambang.
5. **`workflows/approval.py`** — `HumanApprovalGate` **bukan** `BaseWorkflow`:
   ia menggerbang hasil yang sudah diproduksi workflow lain, bukan
   menghasilkan dari graf. `Orchestrator.run()` berhenti di `State.REVIEWING`
   dan memanggil `approval.request()` saat `result.escalate` (dan
   `ENABLE_HUMAN_APPROVAL=true`, Bab 57); `Orchestrator.finalize_approval()`
   dipanggil manusia untuk pindah ke `APPROVED→COMPLETED` atau `CANCELLED`
   (transisi ini sudah ada di state machine Bab 49 sejak Tahap 2, tak berubah).
6. **Pemutus siklus impor** — nama dari `workflows` yang benar-benar dipakai
   saat runtime di `orchestrator/orchestrator.py` (`WORKFLOWS`,
   `HumanApprovalGate`) diimpor lokal di dalam `__init__`/`run()`, bukan di
   level modul; anotasi tipe tetap memakai nama-nama itu berkat
   `from __future__ import annotations` + blok `TYPE_CHECKING`. Ini pola yang
   sama dengan `registry.agent_registry.build_default_agent_registry()` dan
   `task_manager._default_store()` — bukan pengecualian baru.

## Alternatif yang Dipertimbangkan

- **Confidence Agent sebagai panggilan LLM terpisah** (Bab 28 menyiratkan
  "Confidence Agent menilai") — ditolak untuk sekarang: menambah biaya/latensi
  per hasil tanpa manfaat jelas dibanding pembauran sinyal yang sudah ada;
  role `confidence` di Model Registry tetap tersedia untuk pemakaian
  eksplisit nanti.
- **Guardrail sebagai sinyal keempat sekarang** — ditolak: modul guardrail/
  output-validator belum ada (Tahap 7); menambah sinyal palsu lebih buruk
  daripada tidak menambahkannya.
- **Human Approval sebagai `BaseWorkflow` biasa** (biar seragam dengan entri
  lain di tabel Bab 24) — ditolak: kontraknya (`run(graph, dispatcher) →
  WorkflowResult`) tak cocok untuk sesuatu yang menggerbang hasil yang sudah
  ada dan menunggu keputusan manusia async; dipaksakan hanya menambah
  abstraksi tanpa manfaat.
- **Auto-timeout yang memutuskan approval sendiri saat SLA lewat** — ditolak:
  Bab 61.3 rule 1 minta eskalasi, bukan keputusan otomatis yang meniru
  manusia; `overdue()` hanya menandai, tidak pernah memutuskan.

## Trade-off

- Confidence blend menambah satu pembacaan `ReflectionMemory` (I/O) per hasil
  yang direfleksikan — diterima karena memori itu sendiri in-process/Redis
  yang cepat, dan skor yang lebih baik berarti lebih sedikit eskalasi keliru.
- Consensus/Voting butuh N kali panggilan agent untuk N kandidat (lebih mahal
  dari sequential/parallel) — sesuai semangat Bab 26: dipilih justru saat
  akurasi lebih penting dari biaya, bukan default untuk semua task.
- Lazy import di `orchestrator.py` sedikit mengurangi keterbacaan "semua impor
  di atas" — diterima karena alternatifnya (menata ulang seluruh
  `orchestrator/__init__.py` dan `workflows/__init__.py` agar linear) akan
  menyentuh lebih banyak modul untuk manfaat yang sama.

## Konsekuensi

- Exit criteria Tahap 4 terpenuhi: Confidence Scoring nyata menggantikan
  heuristik murni, Reflection Engine mengeskalasi (bukan memaksa lolos),
  Consensus Engine menerbitkan `consensus.decided`, Human Approval benar-benar
  menggerbang state machine — semua teruji tanpa layanan hidup (Bab 12).
- `Planner.plan()` kini menerima lima mode (`sequential`, `parallel`,
  `reflection`, `voting`, `consensus`); mode chained (`sequential`,
  `reflection`) vs independen (`parallel`, `voting`, `consensus`) diatur satu
  set konstanta (`_CHAINED_MODES`), bukan per-mode if/else yang menyebar.
- Tahap 5 (RAG) dan Tahap 6 (Observability/Cost) tinggal mengonsumsi
  `consensus.decided`/`agent.reviewing` yang sudah mengalir di Event Bus sejak
  Tahap 3, dan bisa menambah sinyal guardrail ke `ConfidenceScorer` tanpa
  mengubah kontraknya (parameter opsional baru, bukan breaking change).
