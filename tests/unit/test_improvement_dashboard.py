"""Unit test for telemetry.monitoring.improvement_dashboard() (Fase 7, DCF
v5 mandate) — sources from improvement/ledger.py, same "one source of
truth" principle audit_dashboard() already follows for security/audit_log.py.
"""
from improvement import ledger
from improvement.models import ImprovementAction, ImprovementRecommendation
from telemetry.monitoring import improvement_dashboard


def test_dashboard_reflects_ledger_contents():
    ledger.record_recommendation(ImprovementRecommendation(category="confidence_threshold_too_strict"))
    action = ImprovementAction(setting="CONFIDENCE_THRESHOLD_DEFAULT", old_value=0.6, new_value=0.55)
    ledger.record_action_applied(action)

    dashboard = improvement_dashboard()

    assert dashboard["total_recommendations"] == 1
    assert dashboard["total_actions_applied"] == 1
    assert dashboard["total_actions_reviewed"] == 0
    assert len(dashboard["pending_review"]) == 1
    assert dashboard["ledger_integrity_ok"] is True
    assert dashboard["ledger_integrity_problems"] == []


def test_dashboard_empty_ledger_is_not_an_error():
    dashboard = improvement_dashboard()

    assert dashboard["total_recommendations"] == 0
    assert dashboard["pending_review"] == []
    assert dashboard["ledger_integrity_ok"] is True
