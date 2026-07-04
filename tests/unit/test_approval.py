"""Unit tests for the Human Approval gate (Bab 61)."""
import pytest

from workflows.approval import HumanApprovalGate


@pytest.mark.asyncio
async def test_request_then_approve():
    gate = HumanApprovalGate(sla_seconds=3600)
    req = await gate.request("t1", reason="low_confidence")
    assert req.trace_id == "t1"
    assert not req.decided
    assert gate.pending() == [req]

    decided = await gate.decide("t1", approved=True, decided_by="rudy", reason="looks fine")
    assert decided.decided
    assert decided.approved is True
    assert decided.decided_by == "rudy"
    assert gate.pending() == []


@pytest.mark.asyncio
async def test_reject_records_reason():
    gate = HumanApprovalGate(sla_seconds=3600)
    await gate.request("t1", reason="high_risk_domain")
    decided = await gate.decide("t1", approved=False, decided_by="rudy", reason="not accurate enough")
    assert decided.approved is False
    assert decided.decision_reason == "not accurate enough"


@pytest.mark.asyncio
async def test_decide_unknown_trace_id_raises():
    gate = HumanApprovalGate()
    with pytest.raises(KeyError):
        await gate.decide("missing", approved=True, decided_by="rudy")


@pytest.mark.asyncio
async def test_overdue_flags_requests_past_sla():
    gate = HumanApprovalGate(sla_seconds=0)
    req = await gate.request("t1", reason="low_confidence")
    assert req.overdue
    assert gate.overdue() == [req]


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_trace_id():
    gate = HumanApprovalGate()
    assert gate.get("missing") is None
