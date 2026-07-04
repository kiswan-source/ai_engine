# ADR-0009: Telemetry — Observability + Cost Tracking (Tahap 6)

| Field | Isi |
|---|---|
| Nomor | ADR-0009 |
| Judul | `telemetry/` (tracing, metrics, cost_tracker, logging, monitoring) + cost-budget escalation ke Human Approval |
| Status | Accepted |
| Tanggal | 2026-07-05 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 27, 33, 34, 35, 56, 62; DEVELOPMENT_ROADMAP.md Tahap 6 |

## Latar Belakang

Sejak Tahap 3, `messaging/event_bus.py` menegaskan: "Every significant domain
event... must be published here so observability (Tahap 6)... can react
without coupling." Tahap 3-5 sudah menerbitkan seluruh event lifecycle
(`agent.*`, `workflow.*`, `consensus.decided`) tapi tak ada satupun yang
membacanya untuk observability. Tahap 6 mengisi itu: `telemetry/` sesuai Bab
34's daftar modul, plus penegakan cost budget (Bab 27 rule 4) yang terhubung
ke Human Approval (Bab 61.2) yang sudah dibangun Tahap 4.

## Permasalahan

1. `AgentResult` sudah punya `prompt_tokens`/`completion_tokens` sejak Tahap 1
   tapi tak pernah keluar dari Dispatcher — cost tracking butuh data itu di
   event, bukan di dalam `AgentResult` yang cuma dikembalikan ke caller.
2. Bab 34 "Execution Timeline" (jejak lengkap satu request lintas agent/
   provider/tool) tumpang tindih persis dengan apa yang sudah dipublikasikan
   ke Event Bus sejak Tahap 3 — instrumentasi baru di setiap call site akan
   duplikasi.
3. Bab 11 (structured logging) sudah dipenuhi `core/utils/logger.py`; Bab 34
   tetap mendaftarkan `telemetry/logging.py` sebagai modul.
4. Bab 35 rule 3 minta health check memverifikasi konektivitas ke *setiap*
   provider LLM — `api/routes/health.py`'s `/ready` cuma cek Ollama.
5. `TaskManager` tak punya cara enumerasi "semua id yang sedang dilacak" —
   Workflow Dashboard (Bab 62) yang minta "status workflow aktif" real-time
   makin sulit dipenuhi tanpa perubahan lebih luas ke `TaskStore`.

## Keputusan

1. **Tiga collector, satu pola**: `telemetry/tracing.py` (`Tracer`),
   `telemetry/metrics.py` (`MetricsCollector`), `telemetry/cost_tracker.py`
   (`CostTracker`) semuanya *subscriber* Event Bus murni — konstruktor
   `(event_bus=None, ...)`, method `async start()` yang subscribe
   (idempotent), nol pemanggilan langsung dari Dispatcher/Orchestrator.
   `Orchestrator` memasang ketiganya dari `self.events` (miliknya sendiri,
   bukan `EventBus()` default baru) dan men-subscribe secara lazy di awal
   `run()`/`run_single()` (`__init__` tak bisa `await`).
2. **Dispatcher diperkaya, bukan dipasangi cost tracker** — `agent.completed`
   kini membawa `model`/`prompt_tokens`/`completion_tokens`/`confidence` di
   payload-nya (satu-satunya perubahan Dispatcher); `CostTracker` dan
   `MetricsCollector` membaca dari situ. Zero coupling terjaga persis seperti
   niat desain Tahap 3.
3. **Cost budget = alasan eskalasi baru, bukan gerbang baru** — `Orchestrator.run()`
   menghitung `cost_for_trace(trace_id)` setelah workflow selesai; jika
   melebihi `COST_BUDGET_PER_TASK`, dipakai jalur `State.REVIEWING` +
   `HumanApprovalGate` yang SAMA dengan `result.escalate` (Tahap 4), hanya
   beda `reason="cost_budget_exceeded"` (sudah didefinisikan di
   `workflows/approval.py`'s `Reason` Literal sejak Tahap 4 — dipakai
   sekarang). Tidak ada gerbang/state baru.
4. **Storage**: `Tracer` & `CostTracker` memakai ulang `memory.stores.ListStore`
   (Tahap 3) — bukan abstraksi penyimpanan baru. `CostTracker` menyimpan satu
   ledger bersama (`cost_ledger`) dan memfilter saat query (`cost_for_trace`,
   `cost_by_provider`, dst.) — O(ukuran ledger) per query, cukup untuk skala
   alat ini, bukan pipeline metrik throughput tinggi. `MetricsCollector`
   sengaja in-process saja (tanpa `METRICS_BACKEND`) — sama seperti asumsi
   `TaskManager`'s default in-memory: yang penting kondisi saat ini, bukan
   riwayat lintas restart.
5. **`telemetry/logging.py` re-export, bukan config baru** — `core.utils.logger`
   tetap satu-satunya konfigurasi structlog; modul ini cuma jalur impor
   kanonis di bawah `telemetry.*` biar Bab 34's daftar modul terpenuhi tanpa
   duplikasi config.
6. **`check_readiness()` dipindah ke `telemetry/monitoring.py`**, diperkaya
   memeriksa tiap provider LLM yang aktif (`list_enabled_providers()`), bukan
   cuma Ollama (Bab 35 rule 3). `api/routes/health.py`'s `/ready` sekarang
   memanggilnya — satu sumber kebenaran untuk route dan `health_dashboard()`.
7. **8 dashboard Bab 62** — semua dependency-injected (terima `AgentRegistry`/
   `MetricsCollector`/`CostTracker`/`VectorMemory` eksplisit), bukan baca
   singleton global, jadi caller kontrol instance mana yang direfleksikan.
   `check_alerts()` (Bab 35 rule 2) membaca objek yang SAMA dengan dashboard
   — tak ada dua sumber kebenaran, sesuai aturan penutup Bab 62.
8. **Gap yang diakui, bukan disamarkan**: Workflow Dashboard tak bisa
   menampilkan "workflow aktif saat ini" (`TaskManager` tak punya enumerasi
   — nambahnya berarti SCAN di `RedisTaskStore`, di luar cakupan); Provider
   Dashboard tak menyertakan status Circuit Breaker (Bab 55 belum
   diimplementasikan sama sekali di codebase ini); Memory Dashboard cuma
   melaporkan `vector.count()` — tier lain tak punya metode ukuran.

## Alternatif yang Dipertimbangkan

- **OpenTelemetry / Prometheus client** — ditolak (Bab 45.3, hindari
  dependency baru); event stream yang sudah ada + `ListStore` sudah cukup
  untuk kebutuhan observability saat ini.
- **Dispatcher memanggil `cost_tracker.record()` langsung** (bukan lewat
  event) — ditolak: memutus prinsip "Event Bus = satu-satunya jalur
  observability" yang sudah ditegaskan sejak Tahap 3; event-driven juga
  berarti siapapun bisa menambah collector baru tanpa menyentuh Dispatcher.
- **`TaskManager` diberi metode enumerasi penuh sekarang** — ditolak: perlu
  SCAN di backend Redis, perubahan kontrak `TaskStore` yang lebih besar dari
  yang dibutuhkan Tahap 6; dicatat sebagai gap eksplisit, bukan dipaksakan.
- **`llm_rerank()`-style LLM-based alerting/anomaly detection** — ditolak:
  `check_alerts()` cukup berbasis ambang statis (Bab 35 rule 2 tidak minta
  lebih dari itu); menambah panggilan LLM ke jalur alerting kontradiktif
  dengan semangat Cost Optimization yang justru sedang dibangun.

## Trade-off

- `CostTracker`/`Tracer` query berskala O(ledger)/O(span per trace) —
  diterima untuk alat observability skala dev/tim kecil; migrasi ke agregat
  ter-index kalau volumenya jadi masalah nyata, bukan sekarang.
- `cost_for_trace()` dipanggil tepat setelah `workflow.run()` selesai
  mengasumsikan pengiriman event SINKRON (`MESSAGE_BROKER=memory`, default
  saat ini) — kalau nanti pindah ke `MESSAGE_BROKER=redis` (pengiriman lewat
  background reader task), pengecekan budget bisa balapan dengan event
  `agent.completed` terakhir yang belum sampai. Didokumentasikan langsung di
  `orchestrator.py`, bukan diselesaikan sekarang karena deployment saat ini
  single-process dengan broker in-memory.
- Dashboard tanpa frontend/route API — diterima; ini lapisan data, bukan UI;
  menyambungkannya ke route/tampilan adalah pekerjaan terpisah yang bisa
  menyusul kapan saja tanpa mengubah kontrak modul ini.

## Konsekuensi

- Exit criteria Tahap 6 terpenuhi: cost per task/provider/role terlacak
  nyata (diverifikasi live dengan panggilan Claude sungguhan — 1 kalimat
  jawaban berbiaya $0.000423), Execution Timeline terekonstruksi lengkap dari
  event yang sudah ada, task yang melebihi `COST_BUDGET_PER_TASK` benar-benar
  berhenti di `REVIEWING` dan butuh keputusan manusia sebelum `COMPLETED`.
  206/206 test lulus (40 baru).
- **Ditemukan & diperbaiki di luar rencana awal**: container `ai_engine_api`
  Docker sudah gagal start selama ~2 jam sejak Tahap 5 menambah `pgvector` ke
  `requirements.txt` tanpa rebuild image (`docker compose build` cuma
  dijalankan untuk `postgres` waktu itu). `uvicorn --reload`-nya membuat
  container tetap tampak "Up" walau `lifespan`/`init_db()` gagal berulang —
  gejalanya tak terlihat dari `docker ps`, baru ketahuan saat verifikasi live
  Tahap 6 mencoba `curl /health/ready`. Diperbaiki: rebuild + recreate
  `api`/`worker_ai`/`worker_gis`. Worker Redis DNS error yang ikut ketemu
  ternyata transient — hilang sendiri setelah recreate, tak berulang.
- Tahap 7 (Security hardening) bisa menambah sinyal guardrail ke
  `ConfidenceScorer` (Tahap 4) dan memakai `check_alerts()`/Cost Dashboard
  yang sama untuk anomaly-based access alerts, tanpa mengubah kontrak
  `telemetry/` ini.
