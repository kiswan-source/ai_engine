# ADR-0014: Implementasi Project Workspace & Folder Access (Tahap 19)

> **Catatan disambiguasi wajib:** ADR ini merealisasikan keputusan **produk**
> ADR-0005 di `D:\01_Project\AI ENGINE\docs\ARCHITECTURE_DECISIONS.md` (dimiliki
> Boss/Project Owner) — nomor **ADR-0014 di sini adalah seri lokal repo kode**,
> tidak berelasi urutan dengan seri ADR-0005 tersebut. Kebetulan repo kode ini
> **sudah punya** `ADR-0005-orchestrator-workflow-engine.md` (Tahap 5, topik
> sama sekali berbeda: Orchestrator/Workflow Engine) — persis contoh nyata
> tabrakan nomor dua sistem ADR berbeda yang diperingatkan hand-off doc
> `CLAUDE_CODE_PROMPT_WORKSPACE_IMPLEMENTATION.md` §2. Kedua ADR-0005 tetap
> dibiarkan apa adanya (tidak dinomori ulang, berisiko merusak riwayat) —
> dibedakan lewat path lengkap tiap kali dirujuk.

| Field | Isi |
|---|---|
| Nomor | ADR-0014 |
| Judul | `workspace/` (domain) + `tools/adapters/filesystem.py` (infra) + `api/routes/workspace.py` — implementasi Project Workspace & Folder Access |
| Status | Accepted |
| Tanggal | 2026-07-06 |
| Penanggung Jawab | Boss (Project Owner) via hand-off Cowork → Claude Code |
| Rujukan | `MASTER_INSTRUCTION.md` Bab 69 (v1.4); ADR-0005 produk (`D:\01_Project\AI ENGINE\docs\ARCHITECTURE_DECISIONS.md`); `PROJECT_SPECIFICATION.md` §7; `API_CONTRACT.md` §3.6; audit F-003/F-004 (`D:\01_Project\AI ENGINE\audit\remediation\HIGH.md`) |

## Latar Belakang

Roadmap 8-tahap + Phase 3 (Tahap 1-18) selesai. Boss menyetujui desain Bab 69
(Project Workspace & Folder Access) tapi belum ada kode — hand-off doc
`CLAUDE_CODE_PROMPT_WORKSPACE_IMPLEMENTATION.md` menginstruksikan sesi ini
untuk mengimplementasikannya sebagai kapabilitas aditif murni.

## Keputusan

1. **`tools/` dibuat baru**, bukan diperluas — Bab 69.11 menyebut memperluas
   `tools/adapters/filesystem.py` "yang sudah ada", tapi tidak ada package
   `tools/` di repo ini sebelum Tahap 19 (dikonfirmasi lewat pencarian
   penuh). Dibuat sejajar `registry/`/`rag/`/`memory/`/`agent/` (Bab 5) —
   bukan pelanggaran Bab 45.1 (yang menyebut `agent/tools/` secara spesifik,
   bukan ini). Berisi `tool_validator.py` (Root Restriction, Bab 69.6) dan
   `adapters/filesystem.py` (`FilesystemAdapter`, Local-only pass ini).
2. **`workspace/` domain module** (`scanner.py`, `indexer.py`) bergantung pada
   `tools/adapters/filesystem.py` (infra) dan `rag/retriever.py` — tidak
   pernah bergantung pada `api/` (Hexagonal Architecture, Bab 4.2: rute
   memanggil domain, bukan sebaliknya).
3. **DB**: `Workspace`/`WorkspaceFolder` (`db/models.py`) persis skema
   `PROJECT_SPECIFICATION.md` §7.1, dengan satu deviasi terdokumentasi:
   soft-delete lewat `deleted_at` terpisah (bukan memperluas enum `status`
   yang eksplisit 4-nilai tertutup di spesifikasi) — beda dari pola
   `Project.status="archived"`.
4. **RBAC resource-scoped, bukan global** — Workspace Permission (Bab 69.7)
   dipetakan dari Project role (owner/editor/viewer, `api/routes/projects.py`),
   bukan entri baru di `_ROLE_PERMISSIONS`/`TOOL_RISK_ACTIONS`, karena
   Workspace selalu adalah bagian dari satu Project (Bab 69.11). Lihat
   `security/permissions.py` docstring Tahap 19.
5. **Kontrak API diformalkan** dari rancangan Bab 69.13 ke bentuk RESTful
   `/workspace/{id}/mount|scan|index|files|tree|status` — `api/routes/workspace.py`
   docstring menjelaskan alasannya (id eksplisit di path, konsisten pola
   `/projects/{id}/members`).
6. **RAG**: `POST .../index` menggunakan ulang **instance** `_retriever`
   singleton `api/routes/knowledge.py` (bukan sekadar nama namespace yang
   sama) — dengan `VECTOR_BACKEND=memory` (default dev/CI), dua `Retriever`
   yang dibangun terpisah membungkus `InMemoryKnowledgeStore` yang berbeda
   dan tidak saling melihat data; berbagi instance yang sama membuat
   "Workspace Folder adalah Source RAG resmi" (Bab 69.10) benar-benar
   berlaku ujung-ke-ujung, tidak cuma saat kebetulan pakai backend pgvector.
7. **F-003 diselesaikan sebagai berikut** (bukan edit `docs/`, murni
   keputusan implementasi): Uploaded Files tetap mekanisme `Document`/upload
   yang sudah ada, tidak berubah; Workspace Files (`GET .../files`) adalah
   konsep aditif baru dari `WorkspaceFolder`, bukan tabel gabungan.
   `WorkspaceFolder.source_type` mencantumkan `"Upload"` di enum (sesuai
   §7.1) tapi tidak pernah dipakai — `POST .../mount` hanya menerima
   `"Local"` pass ini.
8. **F-004**: `Workspace`/`WorkspaceFolder` kini punya skema nyata,
   siap jadi rujukan konkret saat Boss memperbarui Bab 4.4.

## Alternatif yang Dipertimbangkan

- **Menafsirkan ulang Bab 69.11 dan menaruh adapter di `agent/tools/`**
  (folder yang benar-benar "sudah ada") — ditolak: itu folder fondasi
  (Bab 45.1) yang secara eksplisit dilarang disentuh hand-off doc §5,
  dan tujuannya beda (tool Chat/Agent, bukan infra domain Workspace).
- **Role matrix global untuk Workspace Permission** (menambah 8 action ke
  `_ROLE_PERMISSIONS`) — ditolak: Workspace bukan aksi sistem-lebar, ia
  selalu terikat satu Project; role matrix global tidak tahu Project mana.
- **Enum status 5 nilai (+`Deleted`)** — ditolak: menyimpang dari enum
  tertutup 4-nilai yang eksplisit di `PROJECT_SPECIFICATION.md` §7.1 tanpa
  ADR produk baru dari Boss.

## Trade-off

Root Restriction (Bab 69.6) ditegakkan per-`WorkspaceFolder` yang
diregistrasikan, bukan per satu "Workspace Root" tunggal yang menaungi
semua folder — `Workspace.root_path` bersifat informasional saja (diisi
otomatis dari folder pertama yang di-mount). Ini justru jaminan yang lebih
ketat (setiap folder sandboxed independen), tapi berarti `Workspace.root_path`
tidak benar-benar membatasi apa pun secara teknis — hanya field tampilan
(Bab 69.14 "Workspace Path").

## Konsekuensi

- Jangka pendek: Network/Server/Cloud/SharePoint/OneDrive/GDrive/S3 folder
  source belum ada adapternya (Bab 69.16, sesuai cakupan); `mount` menolak
  eksplisit dengan pesan "roadmap", bukan diam-diam menerima.
- ChatEngine (`core/chat/engine.py`, folder fondasi) belum workspace-aware —
  Agent Workspace Context (Bab 69.5) baru ada di sisi backend/API, belum ada
  tool Chat yang membaca dari Workspace. Gap yang diakui, bukan disamarkan.
- Tidak ada interactive browser verification (tidak ada Playwright/Cypress
  di repo ini) — verifikasi live dilakukan penuh di level API + `npm run
  build`/`lint`, dicatat eksplisit di `docs/PROGRESS.md` Tahap 19.

---

*Setiap ADR baru ditambahkan sebagai file baru di `docs/adr/`, tanpa menomori
ulang ADR sebelumnya, sesuai `MASTER_INSTRUCTION.md` Bab 47.*
