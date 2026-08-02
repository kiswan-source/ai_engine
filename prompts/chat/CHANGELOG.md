# Changelog — chat

| Versi | Tanggal | Perubahan | Alasan |
|---|---|---|---|
| v1 | 2026-06-03 | Versi awal | Baseline (dipindahkan dari `core/chat/engine.py::SYSTEM_PROMPT`, Tahap 37, tanpa perubahan isi) |
| v1 | 2026-08-02 | Tambah panduan paginasi (`has_more`/`offset`), batch read (`read_many_files`/`workspace_read_many_files`), dan jangan langsung menyerah saat tool gagal | Fase 15, DCF v5 mandate — bulk/large-file capability + failure recovery |
