"""Unit tests for PII Detection & Redaction (Bab 30)."""
from security.pii_detector import detect, redact


def test_detects_email():
    matches = detect("Hubungi saya di budi@example.com untuk info lebih lanjut.")
    assert [m.category for m in matches] == ["EMAIL"]
    assert matches[0].text == "budi@example.com"


def test_detects_indonesian_phone():
    matches = detect("Nomor saya 08123456789 aktif 24 jam.")
    assert any(m.category == "PHONE_ID" for m in matches)


def test_detects_nik():
    matches = detect("NIK saya adalah 3201012345678901.")
    assert any(m.category == "NIK_ID" for m in matches)


def test_detects_credit_card():
    matches = detect("Kartu: 4111-1111-1111-1111")
    assert any(m.category == "CREDIT_CARD" for m in matches)


def test_detects_ipv4():
    matches = detect("Server ada di 192.168.1.100 kalau perlu dicek.")
    assert any(m.category == "IPV4" for m in matches)


def test_no_false_positive_on_plain_text():
    assert detect("Laporan wilayah tambang seluas 450 hektare.") == []


def test_redact_replaces_all_matches():
    text = "Email: budi@example.com, HP: 08123456789"
    redacted = redact(text)
    assert "budi@example.com" not in redacted
    assert "08123456789" not in redacted
    assert "[EMAIL_REDACTED]" in redacted
    assert "[PHONE_ID_REDACTED]" in redacted


def test_redact_with_category_filter():
    text = "Email: budi@example.com, HP: 08123456789"
    redacted = redact(text, categories=("EMAIL",))
    assert "[EMAIL_REDACTED]" in redacted
    assert "08123456789" in redacted  # phone untouched, not in the filter


def test_redact_no_matches_returns_original():
    text = "Tidak ada data pribadi di sini."
    assert redact(text) == text
