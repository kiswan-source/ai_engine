"""Unit tests for the Continuous Improvement Engine's ledger (Fase 7, DCF
v5 mandate) — hash-chain tamper-evidence, same technique as
security/audit_log.py (SEC-8)."""
from improvement.ledger import read_recent, record_recommendation, record_action_applied, verify_chain
from improvement.models import ImprovementAction, ImprovementRecommendation


def test_record_recommendation_then_read_recent():
    rec = ImprovementRecommendation(category="confidence_threshold", suggestion="naikkan ambang")
    record_recommendation(rec)

    entries = read_recent()
    assert len(entries) == 1
    assert entries[0].record_type == "recommendation"
    assert entries[0].payload["id"] == rec.id


def test_chain_verifies_ok_across_multiple_entries():
    record_recommendation(ImprovementRecommendation(category="a"))
    record_action_applied(ImprovementAction(setting="CONFIDENCE_THRESHOLD_DEFAULT", old_value=0.6, new_value=0.65))
    record_recommendation(ImprovementRecommendation(category="b"))

    ok, problems = verify_chain()
    assert ok is True
    assert problems == []


def test_tampered_entry_breaks_the_chain():
    from api.config import settings

    record_recommendation(ImprovementRecommendation(category="a"))
    record_recommendation(ImprovementRecommendation(category="b"))

    with open(settings.IMPROVEMENT_LEDGER_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    import json

    tampered = json.loads(lines[0])
    tampered["payload"]["category"] = "tampered"
    lines[0] = json.dumps(tampered) + "\n"
    with open(settings.IMPROVEMENT_LEDGER_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    ok, problems = verify_chain()
    assert ok is False
    assert any("tidak cocok" in p or "menyambung" in p for p in problems)


def test_missing_ledger_file_is_not_an_error():
    ok, problems = verify_chain()
    assert ok is True
    assert problems == []
    assert read_recent() == []
