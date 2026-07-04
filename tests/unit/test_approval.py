"""Unit tests for the Human Approval gate (Bab 61)."""
import pytest

from memory.stores import InMemoryHashStore, RedisHashStore
from workflows.approval import HumanApprovalGate, _default_store


class FakeAsyncRedis:
    """Minimal async stand-in for redis.asyncio.Redis (hash ops only)."""

    def __init__(self):
        self.hashes = {}

    async def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    async def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)

    async def delete(self, key):
        self.hashes.pop(key, None)

    async def expire(self, key, ttl):
        pass


@pytest.mark.asyncio
async def test_request_then_approve():
    gate = HumanApprovalGate(sla_seconds=3600)
    req = await gate.request("t1", reason="low_confidence")
    assert req.trace_id == "t1"
    assert not req.decided
    assert await gate.pending() == [req]

    decided = await gate.decide("t1", approved=True, decided_by="rudy", reason="looks fine")
    assert decided.decided
    assert decided.approved is True
    assert decided.decided_by == "rudy"
    assert await gate.pending() == []


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
    assert await gate.overdue() == [req]


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_trace_id():
    gate = HumanApprovalGate()
    assert await gate.get("missing") is None


# ─── Tahap 8: statelessness (Bab 38 rule 1) ───────────────────────────────────

@pytest.mark.asyncio
async def test_default_store_is_in_memory_by_default(monkeypatch):
    monkeypatch.setattr("api.config.settings.APPROVAL_STATE_BACKEND", "memory")
    assert isinstance(_default_store(), InMemoryHashStore)


@pytest.mark.asyncio
async def test_default_store_is_redis_when_configured(monkeypatch):
    monkeypatch.setattr("api.config.settings.APPROVAL_STATE_BACKEND", "redis")
    assert isinstance(_default_store(), RedisHashStore)


@pytest.mark.asyncio
async def test_redis_backed_gate_shares_state_across_instances():
    """Two HumanApprovalGate instances over the same Redis backend must see
    each other's writes — the whole point of Bab 38 rule 1 (stateless
    services, state in Redis not process memory)."""
    fake = FakeAsyncRedis()
    gate1 = HumanApprovalGate(store=RedisHashStore("approvals-test", client=fake))
    await gate1.request("t1", reason="low_confidence")

    gate2 = HumanApprovalGate(store=RedisHashStore("approvals-test", client=fake))
    pending = await gate2.pending()
    assert [r.trace_id for r in pending] == ["t1"]

    decided = await gate2.decide("t1", approved=True, decided_by="rudy")
    assert decided.approved is True

    # gate1 must see the decision made via gate2 — same underlying store.
    req = await gate1.get("t1")
    assert req.decided
    assert req.decided_by == "rudy"


@pytest.mark.asyncio
async def test_redis_backed_gate_pending_excludes_decided():
    fake = FakeAsyncRedis()
    store = RedisHashStore("approvals-test2", client=fake)
    gate = HumanApprovalGate(store=store)
    await gate.request("t1", reason="low_confidence")
    await gate.request("t2", reason="cost_budget_exceeded")
    await gate.decide("t1", approved=True, decided_by="rudy")

    pending = await gate.pending()
    assert [r.trace_id for r in pending] == ["t2"]
