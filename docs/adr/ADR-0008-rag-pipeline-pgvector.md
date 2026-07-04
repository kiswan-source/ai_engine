# ADR-0008: RAG Pipeline + pgvector Knowledge Store (Tahap 5)

| Field | Isi |
|---|---|
| Nomor | ADR-0008 |
| Judul | `rag/` (chunker, embeddings, knowledge_store, retriever, hybrid_search, reranker, context_builder) + pgvector sebagai backend Vector Memory (Bab 22) & korpus dokumen RAG |
| Status | Accepted |
| Tanggal | 2026-07-05 |
| Penanggung Jawab | Boss (Project Owner) |
| Rujukan | MASTER_INSTRUCTION.md Bab 22, 29; DEVELOPMENT_ROADMAP.md Tahap 5; ADR-0006 (janji "Tahap 5" untuk embedding & vector store nyata) |

## Latar Belakang

ADR-0006 (Tahap 3) sengaja menunda dua hal ke Tahap 5: embedding nyata
(waktu itu hanya Ollama aktif) dan pgvector (image Postgres saat itu belum
menyediakannya). Sejak sesi sebelumnya, API key OpenAI/Claude/Gemini sudah
aktif dan diverifikasi live, sehingga kedua prasyarat itu kini terpenuhi.

## Permasalahan

1. `memory/vector_memory.py` (Tahap 3) memakai *hashed bag-of-words* —
   cukup untuk uji offline, tapi tidak benar-benar semantik.
2. Image Postgres yang berjalan (`postgis/postgis:16-3.4-alpine`) tidak
   punya extension `vector` — dicek langsung: `pg_available_extensions`
   kosong untuk `vector`.
3. RAG (Bab 29) perlu tujuh modul (chunker → embeddings → knowledge_store →
   retriever → hybrid_search → reranker → context_builder), sementara Vector
   Memory (Bab 22) sudah punya kontrak `add`/`search` yang tak boleh berubah
   — dua kebutuhan yang tumpang tindih tapi tidak boleh saling duplikasi.
4. Reranker "sungguhan" biasanya cross-encoder — menambah model/dependency
   besar bertentangan dengan Bab 45.3 (hindari dependency baru).

## Keputusan

1. **Postgres image** — `docker/Dockerfile.postgres` baru: `postgis/postgis:16-3.4-alpine`
   + `apk add postgresql-pgvector` (paket Alpine v0.6.2, tak perlu compile
   dari source). **Catatan penting**: base image punya build PostgreSQL
   sendiri di `/usr/local` (bukan paket Alpine `postgresql16` di
   `/usr/share/postgresql16`) — dua instalasi terpisah. File `vector.so` +
   `vector*.sql` + `vector.control` di-copy manual ke path `/usr/local/...`
   yang benar-benar dibaca server yang jalan, lalu paket apt yang cuma jadi
   perantara di-`apk del` supaya image tetap ramping. `docker-compose.yml`
   diubah dari `image:` ke `build:` untuk service `postgres`. Container
   sudah di-rebuild + direstart (volume data utuh, extension dibuat via
   `CREATE EXTENSION vector` manual karena `scripts/init_db.sql` cuma jalan
   di volume baru).
2. **Satu tabel bersama** — `db.models.VectorEmbedding` (`vector_embeddings`:
   `namespace`, `text`, `meta`, `embedding Vector(RAG_EMBEDDING_DIM)`) dipakai
   BAIK oleh Vector Memory (namespace `"memory"`) MAUPUN korpus dokumen RAG
   (namespace `"rag:documents"`, dsb) — bukan dua skema nyaris identik.
   Lebar kolom vector tetap (`RAG_EMBEDDING_DIM`, default 1536 mengikuti
   OpenAI `text-embedding-3-small`); ganti provider/model embedding ke
   dimensi lain butuh re-index ke tabel baru, bukan sekadar ubah config.
3. **`rag/embeddings.py` & `rag/knowledge_store.py` jadi primitif bersama** —
   `memory/vector_memory.py` kini bergantung pada `rag/` (bukan sebaliknya)
   supaya cosine-search dan embedder tidak dua kali diimplementasikan.
   `VectorMemory.__init__` tetap dependency-free secara default (`embedder`/
   `store` opsional, default hashed-BOW + `InMemoryKnowledgeStore` — Bab 12)
   — hanya `memory_manager.build_memory_manager()` yang membaca settings
   untuk memasang embedder/store nyata. `VectorMemory.count()`/`.clear()`
   berubah dari sync ke async (satu-satunya perubahan kontrak — perlu untuk
   delegasi ke store yang kini async semua; `add`/`search` tak berubah).
4. **Embedding tanpa fallback silang-provider** — beda dari Fallback Strategy
   generate (Bab 54) yang boleh pindah provider, `rag/embeddings.py` sengaja
   TIDAK mencoba provider cloud lain saat satu gagal (dimensi vektor beda2:
   OpenAI 1536, Gemini `gemini-embedding-001` 3072) — provider yang tak aktif
   jatuh ke placeholder hashed-BOW yang deterministik, bukan provider lain
   yang akan mengotori index dengan dimensi/skala berbeda.
5. **Hybrid search tanpa dependency baru** — BM25 diimplementasikan manual di
   `hybrid_search.py`, dihitung di atas kandidat hasil semantic search itu
   sendiri (bukan indeks terbalik penuh atas seluruh korpus) — pendekatan
   praktis yang tetap menaikkan dokumen dengan istilah teknis persis (nomor
   sertifikat, kode IUP) sesuai Bab 29 rule 2, tanpa `rank_bm25` atau
   dependency lain.
6. **Reranker dua tingkat** — `rerank()` (default, selalu aktif via
   `RAG_RERANK_ENABLED`): heuristik boost token mirip-kode, murah & tanpa
   panggilan LLM. `llm_rerank()`: opsional, panggil role `critic` untuk
   menilai ulang shortlist — tidak otomatis dipasang di pipeline default
   karena menambah biaya/latensi per query (semangat Bab 27, walau Cost
   Tracking sungguhan baru Tahap 6); pemanggil yang memilih memakainya.
7. **`Retriever.index_document()`** — satu-satunya jalur resmi memasukkan
   dokumen utuh: memaksa lewat `chunker.py` (Bab 29 rule 1) dan menandai tiap
   chunk dengan `chunk_index`/`start_char`/`end_char` untuk sitasi akurat
   (rule 3). RAG tidak menggantikan `core/document/`/`core/gis/` (rule 4) —
   ini murni lapisan pengaya konteks di atasnya.

## Alternatif yang Dipertimbangkan

- **Tetap in-memory/Redis untuk vector index, tunda pgvector lagi** — ditolak
  oleh Boss secara eksplisit; API key sudah aktif dan Postgres sudah bisa
  di-rebuild, jadi tak ada alasan menunda lagi.
- **Tabel terpisah untuk memory-tier vs korpus RAG** — ditolak: skema identik
  (namespace + text + embedding + metadata); satu tabel dengan `namespace`
  lebih sederhana untuk dirawat dan cukup diindeks satu kolom.
- **Cross-encoder untuk reranker** — ditolak (Bab 45.3); heuristik + opsi
  LLM-based cukup dan tak menambah dependency model besar.
- **Wiring otomatis RAG ke setiap dispatch Orchestrator** — ditolak untuk
  sekarang: tidak semua task butuh RAG context, dan Bab 29 rule 4 menegaskan
  RAG adalah lapisan pengaya opsional. Pemanggil (workflow/agent tertentu)
  yang memilih memakai `Retriever`/`build_context` di prompt-nya secara
  eksplisit; hook otomatis di Orchestrator bisa menyusul kalau polanya jelas
  dibutuhkan.

## Trade-off

- BM25 di atas kandidat semantic (bukan indeks terbalik penuh) berarti
  dokumen relevan yang gagal masuk shortlist semantic tidak pernah
  dipertimbangkan keyword-nya — diterima karena `RAG_TOP_K`/over-fetch bisa
  diperbesar per kasus, dan menghindari kebutuhan indeks terbalik terpisah.
- Ganti dimensi embedding (mis. pindah provider) butuh re-index manual ke
  tabel/kembali ke `memory` sementara — diterima karena ini kendala pgvector
  itu sendiri (kolom vector punya lebar tetap), bukan sesuatu yang bisa
  dihindari oleh desain apa pun.
- `llm_rerank()` tidak otomatis aktif berarti kualitas ranking default
  bergantung pada heuristik + BM25 saja — diterima sebagai default yang
  cepat/murah; pemanggil yang butuh akurasi lebih tinggi mengaktifkannya
  sendiri per kasus.

## Konsekuensi

- Exit criteria Tahap 5 terpenuhi: pipeline penuh (chunk→embed→store→
  retrieve→hybrid→rerank→context) diverifikasi live — embedding OpenAI nyata,
  pgvector nyata (`cosine_distance` via `<=>`), dokumen dengan nomor
  sertifikat spesifik naik peringkat lewat hybrid+rerank persis seperti
  dirancang. 166/166 test lulus (25 baru).
- **Ditemukan, di luar cakupan Tahap 5**: tabel `documents` (dibuat oleh
  `scripts/init_db.sql` versi lama dengan `id UUID`) tidak cocok dengan
  `db.models.Document.id` (`String(36)`) — INSERT lewat SQLAlchemy ORM gagal
  `DatatypeMismatchError`. Ini bug lama yang tak tersentuh Tahap 1-4 (baru
  ketahuan saat mencoba mengindeks row `Document` sungguhan untuk verifikasi
  RAG); perbaikan (migrasi kolom atau ganti tipe model) sengaja tidak
  dilakukan di sini karena di luar lingkup RAG — dicatat untuk sesi
  berikutnya.
- Tahap 6 (Observability/Cost) bisa langsung memakai `consensus.decided`/
  event lain yang sudah mengalir, dan menambah cost tracking di sekitar
  panggilan embedding (`rag/embeddings.py`) serta `llm_rerank()` tanpa
  mengubah kontraknya.
