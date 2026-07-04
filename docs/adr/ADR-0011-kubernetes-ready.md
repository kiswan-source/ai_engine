# ADR-0011: Kubernetes Readiness — Manifests + HumanApprovalGate Statelessness (Tahap 8)

| Field | Isi |
|---|---|
| Nomor | ADR-0011 |
| Judul | `k8s/` manifest set (Kustomize) + `workflows/approval.py` pindah dari dict in-memory ke `HashStore` pluggable |
| Status | Accepted |
| Tanggal | 2026-07-05 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 37, 38, 58.1, 64; DEVELOPMENT_ROADMAP.md Tahap 8 (tahap terakhir roadmap 8-tahap) |

## Latar Belakang

Bab 38 mendaftar lima syarat kesiapan Kubernetes. Empat sudah terpenuhi
sebagai efek samping tahap-tahap sebelumnya (stateless task/memory/cost/trace
via Redis-backend opsional sejak Tahap 3/6; config murni env var sejak awal;
`/health/`+`/health/ready` sejak Tahap 6; worker terpisah dari API sejak
awal). Satu yang BELUM: `HumanApprovalGate` (Tahap 4) masih `dict` di memori
proses — satu-satunya state Bab-38-rule-1 yang bolong di seluruh sistem.

**Batasan sesi ini**: tidak ada cluster Kubernetes aktif di lingkungan
pengembangan (tidak ada kubectl/minikube/kind/k3s terpasang). Setelah
dikonfirmasi ke Boss, disepakati manifest disiapkan dan divalidasi via
sintaks YAML + penalaran manual — BUKAN `kubectl apply` yang diamati
langsung seperti tahap-tahap sebelumnya yang selalu diverifikasi live.

## Permasalahan

1. `HumanApprovalGate._pending: dict[str, ApprovalRequest]` berarti dua
   replika API pod akan punya daftar pending approval yang BERBEDA — approval
   yang diminta di pod A tidak terlihat di pod B, dan restart pod
   menghilangkan semuanya. Ini bertentangan langsung dengan Bab 38 rule 1.
2. Tidak ada satupun manifest Kubernetes di repo — perlu dibangun dari nol,
   mencerminkan `docker-compose.yml` yang sudah ada (Bab 37) tanpa
   duplikasi/drift antara keduanya.
3. RQ worker (`worker/ai/worker_ai.py`, `worker/gis/worker_gis.py`) tidak
   punya HTTP surface — health probe Kubernetes standar (httpGet) tidak
   berlaku; perlu diverifikasi apakah RQ sendiri sudah menangani graceful
   shutdown (Bab 38 rule 5) sebelum mengasumsikan itu "gratis".
4. `docker/Dockerfile.api`/`Dockerfile.worker` bukan multi-stage build (Bab 37
   rule 2) — image lebih besar dari seharusnya untuk pola scheduling/scaling
   K8s yang sering.

## Keputusan

1. **`workflows/approval.py` pindah ke `HashStore` pluggable** — pola yang
   SAMA persis dengan setiap tier lain sejak Tahap 3 (`memory.stores.HashStore`,
   `InMemoryHashStore`/`RedisHashStore`), bukan abstraksi baru. Satu scope
   hash bernama `"approvals"`, field = trace_id, value = `ApprovalRequest`
   ter-JSON. Config baru `APPROVAL_STATE_BACKEND` (memory|redis), default
   `memory` (Bab 12 — CI/dev tetap service-free), production set `redis`.
   `get()`/`pending()`/`overdue()` jadi async — perubahan kontrak yang sama
   jenisnya dengan `VectorMemory.count()`/`.clear()` di Tahap 5, untuk alasan
   yang sama (delegasi ke store yang mungkin remote). Diverifikasi live: dua
   instance `HumanApprovalGate` di atas `RedisHashStore` yang sama
   benar-benar saling melihat permintaan & keputusan satu sama lain —
   mensimulasikan dua pod.
2. **Kustomize, bukan Helm** (Bab 45.3 — hindari tool baru; `kubectl apply -k`
   sudah bawaan `kubectl`). `k8s/base/` = satu set manifest lengkap
   (Namespace, ConfigMap, Secret template, StatefulSet Postgres + headless
   Service + PVC, Deployment Redis + Service + PVC, Deployment API (2 replika)
   + Service, dua Deployment worker terpisah — Bab 38 rule 4, scaling
   independen). `k8s/overlays/production/` — satu contoh overlay
   mendemonstrasikan Bab 64 "build once, promote everywhere": image sama,
   cuma tag registry + replica count yang beda.
3. **ConfigMap/Secret persis mengikuti pembagian `api/config.py`** — SEMUA
   setting non-sensitif (dari App sampai Rate Limiting) di ConfigMap; hanya
   `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL`, tiga API key provider,
   `API_KEYS`, kredensial Postgres di Secret. `secret.yaml` adalah TEMPLATE
   (placeholder eksplisit `CHANGE_ME_*`, aman di-commit — Bab 45.2 rule 4)
   dengan instruksi jelas cara mengisi nilai asli tanpa pernah menulisnya ke
   file di repo.
4. **`scripts/init_db.sql` di-generate via kustomize `configMapGenerator`
   langsung dari file asli** (bukan disalin manual ke YAML) — mencegah drift
   antara apa yang docker-compose mount dan apa yang Kubernetes mount,
   masalah PERSIS yang baru diperbaiki di Tahap 5 (ADR-0008) untuk hal lain.
5. **Tidak ada liveness/readiness probe untuk worker RQ** — diverifikasi
   dulu (bukan diasumsikan) bahwa `rq==1.16.2`'s `Worker.request_stop()`
   sudah menangani warm shutdown (tunggu job selesai) built-in saat SIGTERM
   pertama, baru cold-shutdown di sinyal kedua — jadi Bab 38 rule 5 sudah
   terpenuhi tanpa kode tambahan untuk worker. Exec probe yang berarti butuh
   `pgrep`/`ps` yang tak ada di image saat ini — dicatat sebagai gap, bukan
   dipaksakan dengan probe yang mungkin salah.
6. **Dockerfile TIDAK dijadikan multi-stage di sesi ini** — meski Bab 37
   rule 2 secara eksplisit meminta ini, risikonya nyata: image api/worker
   yang SEDANG jalan baru saja diperbaiki dari insiden gagal-start di Tahap
   6 (ADR-0009) akibat rebuild yang kurang hati-hati. Menulis ulang
   Dockerfile berarti harus memastikan lib runtime GDAL/PostGIS tetap ada di
   stage final tanpa header/compiler build-time — perlu sesi tersendiri
   dengan rebuild+verifikasi penuh, bukan dilakukan tergesa di tahap ini.

## Alternatif yang Dipertimbangkan

- **Helm chart** — ditolak (Bab 45.3); Kustomize cukup untuk kompleksitas
  saat ini dan tidak menambah tool/dependency baru di luar `kubectl` yang
  memang prasyarat memakai Kubernetes sama sekali.
- **HumanApprovalGate tetap in-memory, dokumentasikan saja sebagai gap** —
  ditolak: berbeda dari gap lain (Circuit Breaker, RBAC ke `agent/tools/`)
  yang genuinely di luar cakupan/butuh migrasi besar, statelessness gate ini
  BISA diperbaiki dengan pola yang sudah ada (`HashStore`) tanpa desain
  baru — memperbaikinya jauh lebih murah daripada mendokumentasikan
  kenapa tidak diperbaiki.
- **Menulis probe `exec` dengan `pgrep` untuk worker meski belum ada di
  image** — ditolak: menyarankan sesuatu yang akan gagal begitu diterapkan
  bukan lebih baik daripada tidak ada probe sama sekali; kejujuran soal gap
  lebih berguna daripada probe palsu.
- **Coba install kind/minikube untuk verifikasi live** — ditawarkan ke Boss
  secara eksplisit, ditolak (pilih opsi manifest-only) karena menambah
  instalasi tool + waktu setup yang tidak sedikit untuk satu tahap.
- **Postgres/Redis sebagai managed service eksternal (RDS, ElastiCache, dst.)
  alih-alih StatefulSet/Deployment in-cluster** — ditolak untuk manifest
  dasar ini: menambah asumsi penyedia cloud tertentu; StatefulSet/Deployment
  generik lebih portable sebagai titik awal, dengan catatan HA nyata butuh
  operator/managed service di produksi sungguhan (dicatat di gap).

## Trade-off

- `HumanApprovalGate`'s `pending()`/`overdue()`/`get()` jadi async —
  breaking change kecil untuk kode yang sudah ada sejak Tahap 4
  (`Orchestrator.pending_approvals()` ikut jadi async); diterima karena
  tanpa ini statelessness mustahil, dan pola sudah pernah diterima sebelumnya
  (VectorMemory, Tahap 5).
- PVC `ReadWriteMany` untuk `uploads`/`reports` di manifest dasar
  mengasumsikan `StorageClass` yang mendukungnya — kebanyakan cluster default
  cuma `ReadWriteOnce`. Diterima sebagai asumsi eksplisit (didokumentasikan
  di README) daripada diam-diam membatasi API ke 1 replika saja, yang
  sebetulnya mengalahkan tujuan menyiapkan 2 replika di awal.
- Tidak ada verifikasi live sama sekali untuk seluruh tahap ini — pertama
  kalinya sejak Tahap 1 sebuah tahap tidak diakhiri dengan bukti "berjalan
  nyata". Diterima secara eksplisit oleh Boss sebagai keterbatasan
  lingkungan, bukan kelalaian.

## Konsekuensi

- Exit criteria Tahap 8 (versi "manifest siap" bukan "sudah live di cluster"):
  4 dari 5 syarat Bab 38 sudah terpenuhi sejak sebelumnya, satu yang bolong
  (statelessness Human Approval) sudah diperbaiki dan diverifikasi live
  (simulasi dua pod berbagi state via Redis). 271/271 test lulus (4 baru).
- Roadmap 8-tahap `MASTER_INSTRUCTION.md`/`DEVELOPMENT_ROADMAP.md` **selesai
  seluruhnya** — lihat `docs/PROGRESS.md` untuk ringkasan Tahap 1-8 dan daftar
  gap yang diakui secara kumulatif (Circuit Breaker Bab 55, RBAC belum
  menyentuh `agent/tools/` atau route API, Dockerfile belum multi-stage,
  belum ada operator HA Postgres/Redis, belum ada verifikasi cluster
  sungguhan) sebagai peta kerja untuk sesi-sesi berikutnya di luar roadmap
  awal.
