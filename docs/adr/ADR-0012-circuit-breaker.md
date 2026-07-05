# ADR-0012: Circuit Breaker per Provider (Tahap 9 — pasca-roadmap)

| Field | Isi |
|---|---|
| Nomor | ADR-0012 |
| Judul | `providers/circuit_breaker.py` — state machine Closed→Open→Half-Open per provider, terintegrasi di Dispatcher |
| Status | Accepted |
| Tanggal | 2026-07-05 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 55 (+ Bab 54.1 langkah 5–6, Bab 38 rule 1, Bab 62 Provider Dashboard); docs/PROGRESS.md "Titik mulai sesi berikutnya" butir 1 |

## Latar Belakang

Roadmap 8-tahap selesai (ADR-0011), tetapi Bab 55 belum diimplementasikan
sama sekali — gap yang dicatat sejak ADR-0009. Dispatcher hanya punya
retry + switch-provider (Bab 54 tier 1–3): saat sebuah provider benar-benar
down, SETIAP dispatch tetap membayar `PROVIDER_MAX_RETRIES + 1` kali
timeout ke provider mati itu sebelum jatuh ke fallback — persis pemborosan
yang Bab 55 larang. Terverifikasi live sebelum perbaikan: dispatch pertama
ke Claude yang tidak reachable makan ~17 detik; setelah breaker aktif,
dispatch berikutnya dilayani fallback dalam ~1 detik.

## Keputusan

1. **Lokasi modul: `providers/circuit_breaker.py`** — Bab 55 menyebut
   penerapannya "di lapisan `providers/`". Arah dependency tetap bersih
   (Bab 7 rule 7): `orchestrator` → `providers`. `tools/tool_executor.py`
   (sasaran kedua Bab 55) belum ada di repo — di luar cakupan, dicatat di
   bagian Konsekuensi.
2. **State machine persis Bab 55.2**: `CLOSED` (normal, hitung kegagalan
   beruntun) → `OPEN` saat `failure_threshold` tercapai (semua permintaan
   ditolak tanpa menyentuh provider) → `HALF_OPEN` setelah
   `recovery_timeout` (maksimal `trial_requests` probe; semua sukses →
   `CLOSED`, satu gagal → `OPEN` lagi). Sukses di `CLOSED` mereset hitungan
   beruntun.
3. **State di `HashStore` pluggable** (`CIRCUIT_STATE_BACKEND=memory|redis`)
   — pola yang sama dengan `TASK_STATE_BACKEND`/`APPROVAL_STATE_BACKEND`
   sejak Tahap 3/8, demi Bab 38 rule 1: provider yang di-trip satu pod
   terlihat OPEN oleh semua pod. Timestamp pakai wall-clock (`time.time`),
   bukan monotonic, karena harus bisa dibandingkan lintas proses. Manifest
   K8s (`configmap.yaml`) memakai `redis`.
4. **Parameter per provider, bukan global** (aturan penutup Bab 55):
   `CIRCUIT_PROVIDER_OVERRIDES="openai:3/60/1,gemini:5/30/2"`
   (threshold/recovery_detik/trials); provider tanpa override memakai
   default `CIRCUIT_*`. Entri malformed → `ValueError` keras, bukan diam-diam
   jatuh ke default (Bab 10.2).
5. **Integrasi di Dispatcher, satu titik** (bukan di tiap provider class):
   - Sebelum tier 1: breaker provider primer `Open` → langsung ke tier 2
     (switch provider) tanpa memanggil provider — Bab 54.2 baris "Provider
     tidak merespons berkali-kali".
   - Setiap hasil panggilan mengumpan breaker (`record_success`/
     `record_failure`); trip di tengah retry menghentikan sisa retry.
   - Breaker provider fallback ikut dicek (kecuali sama dengan primer);
     keduanya `Open` → fail fast dengan `AgentResult.error`, bukan exception
     (Bab 10.4).
   - `ENABLE_CIRCUIT_BREAKER=false` mengembalikan perilaku lama persis.
6. **Satu registry default level modul** (`providers.circuit_breaker.breakers`)
   dipakai bersama Dispatcher dan Provider Dashboard — keputusan skip dan
   tampilan dashboard tidak mungkin berbeda sumber (aturan penutup Bab 62).
   Test meng-inject registry sendiri; `tests/conftest.py` mereset registry
   default per test (pola isolasi yang sama dengan `AUDIT_LOG_PATH` Tahap 7).
7. **Transisi state = event** `circuit.opened|half_open|closed` di Event Bus
   (best-effort, Bab 23 prinsip 1); `Tracer` menambah pola `circuit.*` —
   Execution Timeline memuat kapan provider di-trip/pulih.

## Verifikasi

- **Unit**: 16 test baru (`tests/unit/test_circuit_breaker.py`) — seluruh
  transisi Bab 55.2 dengan fake clock, parsing override, dan 5 skenario
  integrasi Dispatcher (skip primer, akumulasi trip, fail-fast dua breaker,
  pemulihan half-open, jalur nonaktif). Suite penuh 287/287 lulus.
- **Live end-to-end** (bukan mock): `ANTHROPIC_BASE_URL` diarahkan ke port
  mati → 2 kegagalan nyata membuka breaker, hasil dilayani fallback Ollama;
  dispatch kedua ~1 detik (vs ~17 detik sebelum breaker); Provider Dashboard
  menampilkan `claude: open`; setelah recovery timeout, panggilan Claude
  SUNGGUHAN (jawab "PULIH") menutup breaker kembali. Dua registry di atas
  `RedisHashStore` yang sama (Redis Docker live) saling melihat state OPEN —
  simulasi dua pod.

## Konsekuensi

- Dispatcher kini punya dependency baru ke `providers.circuit_breaker`
  (opsional — `None` saat dinonaktifkan).
- Breaker hanya melindungi jalur `Dispatcher.dispatch()` (semua workflow
  Orchestrator). Jalur legacy (`agent/core.py`, chat engine `core/chat/`)
  TIDAK tersentuh — FONDASI terlindungi (Bab 45.1), dan Ollama lokal jarang
  butuh breaker.
- `tools/tool_executor.py` (sasaran kedua Bab 55) belum ada; saat folder
  `tools/` dibangun, pakai `CircuitBreakerRegistry` yang sama dengan key
  nama tool.
- Race antar-pod pada increment counter (read-modify-write, bukan HINCRBY
  atomik) bisa menghitung kegagalan sedikit meleset saat dua pod gagal
  bersamaan — dampak terburuk: trip satu-dua kegagalan lebih lambat/cepat.
  Diterima; konsisten dengan catatan race `MESSAGE_BROKER=redis` ADR-0009.

## Alternatif yang Dipertimbangkan

- **Library eksternal (pybreaker/aiobreaker)** — ditolak: state in-process
  (tidak shareable antar pod), dependency baru untuk state machine ~150
  baris, dan tidak mengikuti pola `HashStore` yang sudah ada.
- **Breaker di dalam tiap provider class** — ditolak: empat tempat duplikasi
  + `BaseProvider` harus tahu kebijakan resiliensi (bukan tanggung jawabnya);
  Dispatcher sudah menjadi satu-satunya titik yang tahu retry/fallback.
- **Redis Lua/HINCRBY untuk atomisitas penuh** — ditunda: kompleksitas tidak
  sebanding dengan dampak race yang diterima di atas; bisa menyusul tanpa
  mengubah kontrak.
