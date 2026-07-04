# ADR-0001: Adopsi Provider Abstraction Layer Multi-Vendor

| Field | Isi |
|---|---|
| Nomor | ADR-0001 |
| Judul | Adopsi Provider Abstraction Layer multi-vendor (OpenAI, Claude, Gemini, Ollama) |
| Status | Accepted |
| Tanggal | 2026-07-04 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 16, 20; `ARCHITECTURE_DECISIONS.md` |

## Latar Belakang

AI_ENGINE membutuhkan akses ke beberapa LLM (ChatGPT, Claude, Gemini, Gemma
Local) untuk peran agent yang berbeda, dengan kemungkinan penggantian model di
masa depan.

## Permasalahan

Jika setiap agent memanggil SDK vendor secara langsung, penggantian model/vendor
akan memerlukan perubahan kode tersebar di banyak tempat, melanggar Open/Closed
Principle (Bab 4.3).

## Keputusan

Seluruh akses ke LLM wajib melalui interface `BaseProvider` di `providers/`,
diinstansiasi melalui `providers/provider_factory.py`, dan tidak pernah dipanggil
langsung dari `agents/`/`orchestrator/` (Bab 45.5).

## Alternatif yang Dipertimbangkan

1. Memanggil SDK vendor langsung di tiap agent — ditolak (tidak scalable, melanggar SOLID).
2. Menggunakan satu vendor tunggal — ditolak (mengurangi fleksibilitas & resiliensi).
3. Menambahkan SDK resmi tiap vendor sebagai dependency — ditunda; adapter REST via
   `httpx` (yang sudah menjadi dependency) dipilih agar tidak menambah pustaka pihak
   ketiga baru (Bab 45.3).

## Trade-off

Lapisan abstraksi menambah sedikit kompleksitas awal, terbayar oleh fleksibilitas
jangka panjang. Adapter REST manual berarti perubahan kontrak API vendor harus
dipantau sendiri (tanpa jaminan SDK), namun memberi kendali penuh dan nol dependency baru.

## Konsekuensi

- Provider baru cukup ditambahkan sebagai modul `providers/<nama>_provider.py` +
  entri di `registry/provider_registry.py`, tanpa mengubah orchestrator/agents.
- Pemilihan model per peran agent dipisah ke `registry/model_registry.py` (Bab 20).

## Catatan Implementasi (Tahap 1)

Diimplementasikan pada Tahap 1 Roadmap (Provider Layer & Model Registry):

- `providers/base_provider.py` — `BaseProvider` (`generate`/`stream`/`embed`/
  `count_tokens`/`health_check`) + value object `GenerationParams`,
  `ProviderResponse`, `Chunk`.
- `providers/exceptions.py` — hierarki `AIEngineError` → `ProviderError` →
  `ProviderTimeoutError`/`ProviderNotConfiguredError`/`ProviderResponseError`/
  `ProviderCapabilityError`; error vendor dinormalisasi ke exception internal (Bab 10.6).
- `providers/ollama_provider.py` — integrasi **nyata**, reuse `core/ai/gemma_client.py` (Bab 3).
- `providers/{openai,claude,gemini}_provider.py` — adapter REST via `httpx`, aktif
  otomatis saat API key tersedia di environment; tanpa key → provider disabled.
- `providers/provider_factory.py` — `create_provider(name, model)` dan
  `create_for_role(role)` dengan fallback ke Ollama lokal (Bab 54) bila primary
  belum ber-key.
- `registry/provider_registry.py`, `registry/model_registry.py` — katalog provider
  & peta peran→model (Bab 19–20).

Cakupan test: `tests/unit/test_providers.py`, `tests/unit/test_registry.py`
(seluruh panggilan LLM eksternal di-mock, Bab 12.3).

**Status lingkungan saat ini:** hanya Ollama yang ber-key/aktif. Model default
`gemma4:e2b` pada host ini mengembalikan output kosong (`done_reason: length`,
teks kosong) — kuirk model, bukan cacat provider layer; `qwen2.5:3b` dan
`gemma4:26b` berfungsi normal melalui code path yang sama.
