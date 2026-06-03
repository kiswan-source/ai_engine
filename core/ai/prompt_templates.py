"""
Prompt templates optimised for Gemma 4:26B instruction format.
Gemma uses <start_of_turn>user / <start_of_turn>model convention.
"""
from enum import Enum
from string import Template


class PromptTemplate(str, Enum):
    """Pre-built prompts for common AI Engine tasks."""

    # ── GIS / Mining ──────────────────────────────────────────────────────────
    GEOLOGICAL_SUMMARY = (
        "Berikan ringkasan geologi profesional berdasarkan data berikut.\n"
        "Gunakan bahasa teknis pertambangan Indonesia.\n\n"
        "Data: $data\n\n"
        "Format output:\n"
        "1. Formasi Geologi\n"
        "2. Litologi Dominan\n"
        "3. Struktur Geologi\n"
        "4. Potensi Sumber Daya\n"
        "5. Rekomendasi Eksplorasi"
    )

    WIUP_AREA_ANALYSIS = (
        "Analisis area WIUP berikut untuk keperluan perizinan Minerba.\n\n"
        "Koordinat: $coordinates\n"
        "Luas: $area_ha Ha\n"
        "Lokasi: $location\n\n"
        "Hasilkan:\n"
        "1. Deskripsi batas wilayah\n"
        "2. Estimasi kesesuaian kawasan\n"
        "3. Potensi tumpang tindih\n"
        "4. Rekomendasi teknis"
    )

    # ── Document Processing ───────────────────────────────────────────────────
    DOCUMENT_SUMMARIZE = (
        "Ringkas dokumen berikut secara profesional.\n"
        "Ekstrak poin-poin kunci, keputusan penting, dan tindak lanjut yang diperlukan.\n\n"
        "Dokumen:\n$text\n\n"
        "Panjang ringkasan: maksimum $max_words kata."
    )

    DOCUMENT_EXTRACT_ENTITIES = (
        "Ekstrak semua entitas penting dari dokumen berikut.\n"
        "Kembalikan dalam format JSON dengan keys: "
        "persons, organizations, locations, dates, numbers, legal_refs.\n\n"
        "Dokumen:\n$text"
    )

    # ── Report Generation ─────────────────────────────────────────────────────
    FIELD_INSPECTION_REPORT = (
        "Buat laporan pemeriksaan lapangan profesional berdasarkan data berikut.\n\n"
        "Lokasi: $location\n"
        "Tanggal: $date\n"
        "Temuan: $findings\n"
        "Foto/Observasi: $observations\n\n"
        "Format: Laporan teknis formal Bahasa Indonesia."
    )

    # ── General ───────────────────────────────────────────────────────────────
    QA_WITH_CONTEXT = (
        "Jawab pertanyaan berikut berdasarkan konteks yang diberikan.\n"
        "Jika tidak ada dalam konteks, katakan 'Informasi tidak tersedia'.\n\n"
        "Konteks:\n$context\n\n"
        "Pertanyaan: $question"
    )

    TRANSLATE_TO_ENGLISH = (
        "Translate the following Indonesian technical text to professional English:\n\n$text"
    )

    CLASSIFY_DOCUMENT = (
        "Klasifikasikan dokumen berikut ke dalam kategori:\n"
        "[PERIZINAN, GEOLOGI, KEUANGAN, HUKUM, OPERASIONAL, LAINNYA]\n\n"
        "Dokumen: $text\n\n"
        "Jawab hanya dengan nama kategori."
    )


def render(template: PromptTemplate, **kwargs) -> str:
    """Render a prompt template with given variables."""
    return Template(template.value).safe_substitute(**kwargs)


GEMMA_SYSTEM_MINING = """Anda adalah AI asisten ahli pertambangan dan geologi Indonesia.
Anda memiliki keahlian mendalam dalam:
- Regulasi pertambangan Indonesia (UU Minerba, PP terkait)
- Geologi regional Kalimantan, Jawa, Sulawesi
- Proses perizinan WIUP, IUP Eksplorasi, IUP Operasi Produksi
- Teknik eksplorasi mineral (batubara, bauksit, nikel, andesit, emas)
- Sistem informasi geospasial untuk pertambangan

Gunakan terminologi teknis yang tepat dan bahasa Indonesia formal."""

GEMMA_SYSTEM_GIS = """Anda adalah AI asisten ahli sistem informasi geografis.
Anda memahami: koordinat geodetik, proyeksi peta, analisis spasial,
format data GIS (KML, Shapefile, GeoJSON), dan regulasi tata ruang Indonesia."""

GEMMA_SYSTEM_GENERAL = """Anda adalah AI asisten profesional yang membantu
dengan analisis data, pembuatan dokumen, dan pemrosesan informasi teknis.
Selalu berikan jawaban yang akurat, terstruktur, dan dapat ditindaklanjuti."""
