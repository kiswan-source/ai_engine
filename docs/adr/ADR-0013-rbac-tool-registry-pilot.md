# ADR-0013: RBAC ke `agent/tools/` — pilot satu tool (`write_pdf`)

| Field | Isi |
|---|---|
| Nomor | ADR-0013 |
| Judul | `ToolRegistry.execute(role=...)` + `security/permissions.check_tool_permission` — gerbang RBAC pertama ke folder fondasi `agent/tools/`, dimulai dari `write_pdf` |
| Status | Accepted |
| Tanggal | 2026-07-05 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 30 rule 2, Bab 45.1 (strangler pattern); docs/PROGRESS.md "Titik mulai sesi berikutnya" butir 1; ADR-0010 (RBAC dibangun tapi belum dipasang ke `agent/tools/`) |

## Latar Belakang

ADR-0010 (Tahap 7) membangun `security/auth.py` + `security/permissions.py`
lengkap tapi hanya memasangnya di satu titik (`Orchestrator.finalize_approval`)
— `agent/tools/` (folder fondasi, Bab 45.1) dan setiap route API dicatat
sebagai gap yang belum tersentuh. `docs/PROGRESS.md` menandai ini prioritas
#1 pasca-Circuit-Breaker, dengan instruksi eksplisit: mulai dari SATU tool
berisiko tinggi, bukan semua sekaligus.

`write_pdf` dipilih sebagai tool pilot — representatif kategori "write
filesystem" Bab 30 rule 2, dipakai baik oleh `agent/core.py` (`AIAgent`,
jalur `/api/v1/agent/run`) maupun `core/chat/engine.py` (ChatEngine), lewat
satu choke point yang sudah ada: `ToolRegistry.execute()`.

## Keputusan

1. **Gerbang di choke point yang sudah ada, bukan tool baru** —
   `ToolRegistry.execute()` (`agent/tools/registry.py`) dapat parameter
   opsional `role: str | None = None`. `role=None` (default) = perilaku
   identik sebelum perubahan ini — persis pola opt-in ADR-0007/ADR-0010.
   ChatEngine (`core/chat/engine.py`, juga folder fondasi) TIDAK disentuh
   sama sekali sesi ini dan otomatis tidak terpengaruh karena tidak pernah
   mengirim `role`.
2. **Perubahan ke `agent/tools/registry.py` bersifat aditif** (strangler
   pattern Bab 45.1): satu blok `if role is not None: check_tool_permission(...)`
   ditambahkan sebelum eksekusi tool; tidak ada baris lama yang dihapus atau
   ditulis ulang.
3. **`security/permissions.py` dapat `TOOL_RISK_ACTIONS`** — pemetaan
   `{"write_pdf": "tool:write_pdf"}`, sengaja satu entri. Tool yang tidak ada
   di peta ini tidak terpengaruh berapa pun ketatnya role pemanggil —
   cakupan sesi ini murni `write_pdf`; tool `write_*`/`convert_geo` lain
   dicatat sebagai kandidat migrasi sesi berikutnya di bagian Konsekuensi.
4. **Role baru `operator`** (`tool:write_pdf`, `view_dashboard`) — role
   konkret non-admin yang bisa menulis file, untuk membuktikan jalur allow
   selain admin (`"*"`).
5. **`AIAgent` (`agent/core.py`, BUKAN folder fondasi) dapat `role`
   konstruktor** — diteruskan ke `ToolRegistry.execute(..., role=self.role)`.
   `_execute()` berubah dari sync ke `async def` (pola breaking-change yang
   sama seperti `VectorMemory.count()`/`HumanApprovalGate.get()` di
   ADR-0008/ADR-0011) supaya bisa `await audit_log.record(...)` saat
   `PermissionError` tertangkap — `run()`'s satu pemanggil disesuaikan
   (`await self._execute(...)`).
6. **Route API pertama yang benar-benar memasang RBAC**:
   `/api/v1/agent/run` (`api/routes/agent.py`, bukan folder fondasi) dapat
   `Depends(get_current_principal)`; `AIAgent(role=principal.role)`.
   `API_KEYS` kosong (default dev) → `Principal(role="admin")` → perilaku
   persis sebelum ADR ini untuk siapa pun yang belum mengonfigurasi API key.
7. **Audit log pada penolakan** — `tool_access.denied` (actor = role,
   detail = nama tool) via `security.audit_log.record()`, mengikuti pola
   `prompt_guard.blocked`/`output_validator.violation` ADR-0010.

## Verifikasi

- **Unit** (26 test baru/diperluas, suite penuh 299/299 lulus):
  `test_auth_permissions.py` (4 test `check_tool_permission`),
  `test_tool_registry_rbac.py` (5 test — role `None` tak berubah, `user`
  ditolak, `operator`/`admin` diterima, tool di luar peta tak terpengaruh),
  `test_agent_core_rbac.py` (3 test — role diteruskan, penolakan jadi
  `StepResult` gagal + entri audit, `role=None` tak berubah).
- **Live end-to-end** (bukan mock): panggilan langsung ke
  `AIAgent(role=...)._execute(ToolCall(tool="write_pdf", ...))` dengan tool
  `write_pdf` SUNGGUHAN (`agent/tools/writers.py`) — `role="user"` ditolak
  + entri `tool_access.denied` nyata masuk `security_audit.log`;
  `role="operator"`/`"admin"`/`None` menghasilkan PDF sungguhan di
  `reports/`. Lapisan HTTP diverifikasi terpisah dengan `TestClient` +
  `API_KEYS` diisi live (`userkey:user,opkey:operator`): `userkey` diterima
  (lalu ditolak di dalam agent), `opkey` diterima, key tak dikenal → 401.

## Konsekuensi

- Hanya `write_pdf` yang digerbang; `write_docx`/`write_html`/`write_txt`/
  `write_json`/`write_geojson`/`write_shp`/`convert_geo`/`generate_code`
  masih terbuka untuk role apa pun — migrasi lanjutan menambah entri ke
  `TOOL_RISK_ACTIONS` satu per satu, tanpa mengubah `ToolRegistry.execute()`
  lagi.
- ChatEngine (`core/chat/engine.py`) tidak memanggil dengan `role` —
  pengguna chat tetap tidak digerbang RBAC sesi ini; menyambungkannya
  butuh sesi identitas per percakapan (belum ada di ChatEngine) di luar
  cakupan pilot ini.
- `AIAgent._execute()` sekarang `async` — pemanggil baru di luar
  `agent/core.py` (belum ada saat ini) harus `await`.
- Rute API selain `/api/v1/agent/run` masih terbuka tanpa autentikasi,
  persis seperti sebelum ADR ini (gap yang sama, dicatat sejak ADR-0010).

## Alternatif yang Dipertimbangkan

- **Gerbang semua tool `write_*` sekaligus** — ditolak: instruksi eksplisit
  `docs/PROGRESS.md` untuk mulai dari satu tool dulu, supaya migrasi bisa
  diverifikasi live per tool tanpa mengubah perilaku semua pemanggil
  sekaligus (Bab 45.2 rule 1, larangan big rewrite).
- **Menyambungkan ChatEngine sekalian**, memakai role default yang sama —
  ditolak karena ChatEngine adalah folder fondasi (Bab 45.1) yang sengaja
  tidak disentuh sesi ini, dan belum ada konsep identitas per sesi chat
  untuk dipetakan ke role.
- **Middleware RBAC generik di level FastAPI** untuk semua route sekaligus
  — ditolak: pola ADR-0007/ADR-0010 di proyek ini konsisten opt-in per
  titik integrasi, bukan middleware global; route lain tetap gap yang
  dicatat, bukan disamarkan dengan middleware yang belum diuji live per
  route.
