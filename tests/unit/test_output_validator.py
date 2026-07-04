"""Unit tests for Output Validation (Bab 30, 28)."""
from security.output_validator import validate


def test_clean_output_scores_one():
    result = validate("Ini adalah jawaban yang jelas dan lengkap.")
    assert result.score == 1.0
    assert result.ok


def test_empty_output_flagged():
    result = validate("")
    assert "empty_or_too_short" in result.violations
    assert not result.ok
    assert result.score < 1.0


def test_whitespace_only_output_flagged():
    result = validate("   ")
    assert "empty_or_too_short" in result.violations


def test_truncated_finish_reason_flagged():
    result = validate("jawaban yang terpotong di tengah", finish_reason="length")
    assert "truncated" in result.violations


def test_max_tokens_finish_reason_flagged():
    result = validate("truncated gemini-style", finish_reason="MAX_TOKENS")
    assert "truncated" in result.violations


def test_unresolved_template_artifact_flagged():
    result = validate("Halo {{nama}}, terima kasih.")
    assert "unresolved_template_artifact" in result.violations


def test_pii_leak_flagged():
    result = validate("Hubungi saya di budi@example.com untuk detail.")
    assert "pii_leak" in result.violations


def test_multiple_violations_compound_penalty():
    result = validate("", finish_reason="length")
    assert len(result.violations) >= 2
    assert result.score <= 0.4


def test_score_floors_at_zero():
    result = validate("", finish_reason="length")
    # empty text also can't match template/PII patterns, but confirm score never goes negative
    assert result.score >= 0.0
