# ADR-0010: Security — Prompt/PII Guardrails, Output Validation, Audit Log, RBAC (Tahap 7)

| Field | Isi |
|---|---|
| Nomor | ADR-0010 |
| Judul | `security/` (prompt_guard, pii_detector, output_validator, audit_log, auth, permissions) + guardrail escalation ke Human Approval |
| Status | Accepted |
| Tanggal | 2026-07-05 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 30, 31, 45, 58, 61; DEVELOPMENT_ROADMAP.md Tahap 7; ADR-0007 (janji sinyal ke-4 Confidence Scoring) |

## Latar Belakang

ADR-0007 (Tahap 4) sengaja meninggalkan slot ke-4 Confidence Scoring (Bab 28
— "hasil validasi guardrail dan output validator") kosong karena modulnya
belum ada. Sejak Tahap 6, setiap `agent.completed` sudah membawa cukup data
untuk sinyal lain; Tahap 7 mengisi sinyal terakhir sekaligus memenuhi Bab 30
(Security) dan Bab 31 (Guardrail) yang belum tersentuh sejak Tahap 1.

## Permasalahan

1. Tidak ada satupun pemeriksaan sebelum prompt keluar ke provider — Bab 30
   rule 1 mewajibkan `prompt_guard.py` + `pii_detector.py` di setiap
   panggilan eksternal, tapi kode saat ini tidak punya keduanya sama sekali.
2. `agent/tools/` (RBAC rule 2's sasaran utama — "tool call berisiko tinggi")
   adalah folder FONDASI terlindungi (Bab 45.1) — tidak boleh disentuh sesi
   ini tanpa migrasi bertahap yang jauh lebih besar dari cakupan Tahap 7.
3. `audit.log` di root repo sudah dipakai systemd sebagai target stdout
   capture umum — bukan audit trail terstruktur append-only seperti yang
   Bab 30 minta.
4. Bab 61.3 rule 2 ("keputusan approve/reject dicatat di audit log beserta
   identitas") tak pernah benar-benar diimplementasikan sejak Tahap 4 —
   `HumanApprovalGate.decide()` cuma logging terstruktur biasa, bukan audit
   trail.
5. Tidak ada satupun mekanisme autentikasi/otorisasi di API — semua endpoint
   terbuka, `SECRET_KEY` di `api/config.py` tak pernah dipakai.

## Keputusan

1. **`prompt_guard.py`** — heuristik pattern-based (bukan classifier ML,
   Bab 45.3), dua ambang: `PROMPT_GUARD_SUSPICIOUS_THRESHOLD` menetralisir
   (ganti span mencurigakan jadi `[neutralized]`, prompt tetap lanjut),
   `PROMPT_GUARD_BLOCK_THRESHOLD` memblokir total — persis kata Bab 30
   ("mendeteksi **dan menetralisir**").
2. **`pii_detector.py`** — regex untuk email, telepon Indonesia, NIK, kartu
   kredit, IPv4. Redaksi HANYA diterapkan saat provider tujuan bukan Ollama
   (Bab 30 tabel — "sebelum dikirim ke provider eksternal"; Ollama lokal,
   tak pernah keluar sistem).
3. **Satu choke point: `agents/generic_agent.py`** — `GenericLLMAgent.execute()`
   dipakai oleh SEMUA 15 peran (bukan folder terlindungi, beda dari
   `agent/tools/` legacy), jadi cukup satu tempat untuk prompt_guard +
   redaksi PII (sebelum `generate()`) dan output_validator (sesudahnya) —
   tidak perlu duplikasi per provider.
4. **`output_validator.py` mengisi sinyal ke-4 Confidence Scoring** —
   `ConfidenceScorer.score()` dapat parameter baru `guardrail_score` yang
   **default ke `result.guardrail_score`** bila tak diberikan eksplisit —
   `ReflectionEngine` otomatis mendapat sinyal ini tanpa perubahan kode
   sama sekali (opt-out, bukan opt-in). Bobot dirombak dari 3 sinyal
   (0.5/0.3/0.2) jadi 4 (self-reported 0.4, history 0.2, agreement 0.15,
   guardrail 0.25) — renormalisasi tetap menjaga skor di `[0,1]` untuk
   kombinasi sinyal manapun yang tersedia.
5. **`AgentResult.guardrail_blocked` mengalir otomatis ke `WorkflowResult.escalate`
   di SEMUA mode** — `BaseWorkflow._aggregate()` sekarang menghitung
   `guardrail_blocked = any(r.guardrail_blocked for r in results)` dan
   meng-OR-kannya ke `escalate`, bukan cuma untuk reflection/voting/consensus
   yang sudah py escalate sendiri. Ini memenuhi Bab 31 rule 4 persis:
   "dieskalasi ke Human Approval, bukan diblokir diam-diam tanpa jejak" —
   berlaku untuk sequential/parallel juga, bukan cuma tiga mode yang sudah
   punya alasan eskalasi sendiri.
6. **`audit_log.py`** — file terpisah (`AUDIT_LOG_PATH`, default
   `security_audit.log`) BUKAN `audit.log` yang sudah dipakai systemd —
   menulis JSON append-only ke sana sekaligus menerbitkan event
   `security.<event_type>` di Event Bus (Bab 23 prinsip 1);
   `telemetry.tracing.Tracer` ditambah satu pola subscribe (`security.*`)
   supaya Execution Timeline ikut memuat aksi keamanan. `HumanApprovalGate.decide()`
   sekarang memanggilnya — memenuhi Bab 61.3 rule 2 yang selama ini belum
   terpenuhi sejak Tahap 4.
7. **`auth.py`/`permissions.py` dibangun lengkap TAPI tidak dipasang ke
   route manapun** — `API_KEYS` kosong = auth nonaktif (semua endpoint
   tetap terbuka persis seperti sebelumnya, Bab 45 no big rewrite tanpa
   permintaan eksplisit). Satu-satunya titik integrasi nyata:
   `Orchestrator.finalize_approval(..., role=None)` — beri `role` untuk
   memaksa pemeriksaan `has_permission(role, "approve_workflow")`; tidak
   memberi `role` (default) = perilaku persis sebelum Tahap 7.
8. **Test isolasi global** — `tests/conftest.py` baru: fixture
   `autouse=True` yang mengarahkan `AUDIT_LOG_PATH` ke file temp di SETIAP
   test, karena `HumanApprovalGate.decide()` (dipakai luas sejak Tahap 4)
   kini menulis file sungguhan — tanpa ini, seluruh suite test yang
   menyentuh Human Approval akan mengotori `security_audit.log` di root
   repo setiap kali dijalankan.

## Alternatif yang Dipertimbangkan

- **Wiring RBAC ke `agent/tools/`** (persis Bab 30 rule 2 minta) — ditolak:
  folder itu FONDASI terlindungi (Bab 45.1), butuh strangler-pattern
  migration bertahap yang jauh di luar cakupan satu sesi. Dicatat sebagai
  gap eksplisit, bukan disamarkan.
- **Blokir semua pelanggaran guardrail (bukan neutralize+block bertingkat)**
  — ditolak: Bab 30 sendiri bilang "mendeteksi **dan menetralisir**",
  bukan cuma memblokir; heuristik regex pasti punya false positive, jadi
  hanya skor tertinggi yang benar-benar diblokir.
- **Reuse `audit.log` yang sudah ada** — ditolak: sudah jadi target stdout
  capture systemd yang berisi baris log apa saja; menyisipkan JSON
  terstruktur ke situ akan merusak keduanya.
- **ML classifier untuk prompt injection** (mis. model klasifikasi khusus)
  — ditolak (Bab 45.3); heuristik pattern-based cukup untuk deteksi kasus
  umum tanpa dependency/model baru.

## Trade-off

- Heuristik regex `prompt_guard`/`pii_detector` pasti punya false negative
  (serangan yang diformulasikan ulang lolos) dan sesekali false positive
  (frasa jinak yang kebetulan mirip pola) — diterima sebagai batas
  pendekatan dependency-free; ambang ganda (neutralize vs block)
  meminimalkan dampak false positive dengan tidak langsung memblokir semua
  yang cuma "mencurigakan".
- RBAC nyata hanya menyentuh satu aksi (`approve_workflow`) — sengaja
  sempit; memperluas ke tool call sungguhan menunggu migrasi `agent/tools/`
  yang lebih besar.
- `output_validator`'s deteksi PII-leak memanggil `pii_detector.detect()`
  lagi (bukan reuse hasil redaksi input) — sedikit kerja ganda, diterima
  karena keduanya murah (regex) dan mengecek hal berbeda (input vs output).

## Konsekuensi

- Exit criteria Tahap 7 terpenuhi: setiap dispatch melewati prompt_guard +
  redaksi PII + output_validator; percobaan prompt injection nyata
  diverifikasi live memblokir total dan mengeskalasi ke REVIEWING dengan
  alasan `guardrail_blocked`; PII nyata dalam prompt terverifikasi
  ter-redact sebelum keluar ke Claude; RBAC menolak role tak berwenang lalu
  menerima role yang tepat; audit trail berisi kedua kejadian. 267/267 test
  lulus (61 baru).
- Sinyal ke-4 Confidence Scoring (janji ADR-0007) terpenuhi tanpa perubahan
  di `orchestrator/reflection.py` — desain default-parameter opt-out
  terbukti membayar dirinya sendiri.
- Tahap 8 (Kubernetes ready) bisa langsung memakai `API_KEYS`/`auth.py`
  sebagai titik migrasi ke Kubernetes Secrets (Bab 58.1) tanpa mengubah
  `api/config.py`'s kontrak; RBAC nyata ke `agent/tools/` dan integrasi
  Circuit Breaker (Bab 55, dicatat sebagai gap sejak ADR-0009) tetap jadi
  kandidat sesi terpisah.
