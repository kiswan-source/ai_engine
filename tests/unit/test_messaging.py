"""Unit tests for the messaging layer (Bab 23) — no live Redis (Bab 12.3)."""
import pytest

from messaging import (
    AgentMessage,
    Event,
    EventBus,
    InMemoryBroker,
    MessageBus,
    QueuedTask,
    RedisBroker,
    TaskQueue,
)
from messaging.events import AGENT_RUNNING, WORKFLOW_COMPLETED, agent_event, workflow_event


# ─── Test doubles ─────────────────────────────────────────────────────────────

class FakeAsyncRedis:
    """Minimal async stand-in for redis.asyncio.Redis (lists + publish)."""

    def __init__(self):
        self.published = []
        self.lists = {}

    async def publish(self, channel, data):
        self.published.append((channel, data))
        return 1

    async def rpush(self, key, value):
        self.lists.setdefault(key, []).append(value)

    async def lpop(self, key):
        items = self.lists.get(key) or []
        return items.pop(0) if items else None

    async def blpop(self, key, timeout):
        value = await self.lpop(key)
        return (key, value) if value else None

    async def llen(self, key):
        return len(self.lists.get(key, []))


# ─── Schemas (Bab 17.3 contract) ─────────────────────────────────────────────

def test_agent_message_has_bab_17_3_contract_fields():
    msg = AgentMessage(sender_agent="planner", target_agent="research", task_id="t1")
    data = msg.model_dump()
    for field in ("message_id", "sender_agent", "target_agent", "task_id", "payload", "trace_id", "timestamp"):
        assert field in data
    assert msg.timestamp.endswith("+00:00")  # iso8601 UTC


def test_event_and_queued_task_roundtrip_json():
    event = Event(event_type=WORKFLOW_COMPLETED, source="orchestrator", trace_id="tr")
    assert Event.model_validate_json(event.model_dump_json()) == event
    qt = QueuedTask(kind="generate_pdf", payload={"path": "a.pdf"})
    assert QueuedTask.model_validate_json(qt.model_dump_json()) == qt


def test_event_name_helpers():
    assert agent_event("Running") == AGENT_RUNNING
    assert workflow_event("completed") == WORKFLOW_COMPLETED


# ─── InMemoryBroker ──────────────────────────────────────────────────────────

async def test_inmemory_broker_pubsub_with_glob_pattern():
    broker = InMemoryBroker()
    got = []

    async def handler(data):
        got.append(data)

    await broker.subscribe("evt.agent.*", handler)
    delivered = await broker.publish("evt.agent.running", "x")
    await broker.publish("evt.workflow.completed", "y")  # no match
    assert delivered == 1
    assert got == ["x"]


async def test_inmemory_broker_bad_handler_does_not_break_publish():
    broker = InMemoryBroker()
    got = []

    async def bad(data):
        raise RuntimeError("boom")

    async def good(data):
        got.append(data)

    await broker.subscribe("ch", bad)
    await broker.subscribe("ch", good)
    await broker.publish("ch", "x")
    assert got == ["x"]  # good handler still ran


async def test_inmemory_broker_queue_fifo_and_timeout():
    broker = InMemoryBroker()
    await broker.push("q", "1")
    await broker.push("q", "2")
    assert await broker.queue_length("q") == 2
    assert await broker.pop("q") == "1"
    assert await broker.pop("q") == "2"
    assert await broker.pop("q") is None  # empty, no wait
    assert await broker.pop("q", timeout=0.01) is None  # empty, timed wait


# ─── MessageBus ──────────────────────────────────────────────────────────────

async def test_message_bus_point_to_point_and_broadcast():
    bus = MessageBus(InMemoryBroker())
    inbox_research, inbox_writer = [], []

    async def to_research(msg):
        inbox_research.append(msg)

    async def to_writer(msg):
        inbox_writer.append(msg)

    await bus.subscribe("research", to_research)
    await bus.subscribe("writer", to_writer)

    await bus.send(AgentMessage(sender_agent="planner", target_agent="research", payload={"q": 1}))
    assert [m.payload for m in inbox_research] == [{"q": 1}]
    assert inbox_writer == []

    await bus.send(AgentMessage(sender_agent="planner", target_agent="*"))
    assert len(inbox_research) == 2 and len(inbox_writer) == 1


# ─── EventBus ────────────────────────────────────────────────────────────────

async def test_event_bus_pattern_subscription():
    bus = EventBus(InMemoryBroker())
    seen = []

    async def on_agent(event):
        seen.append(event.event_type)

    await bus.subscribe("agent.*", on_agent)
    await bus.emit(AGENT_RUNNING, source="writer-agent", trace_id="tr")
    await bus.emit(WORKFLOW_COMPLETED, source="orchestrator", trace_id="tr")
    assert seen == [AGENT_RUNNING]


async def test_event_bus_publish_is_best_effort():
    class BrokenBroker(InMemoryBroker):
        async def publish(self, channel, data):
            raise ConnectionError("redis down")

    bus = EventBus(BrokenBroker())
    # Must not raise (Bab 10 — telemetry path never breaks the caller).
    assert await bus.emit(AGENT_RUNNING) == 0


# ─── TaskQueue ───────────────────────────────────────────────────────────────

async def test_task_queue_roundtrip():
    queue = TaskQueue("docs", InMemoryBroker())
    await queue.enqueue(QueuedTask(kind="generate_pdf", payload={"n": 1}))
    await queue.enqueue(QueuedTask(kind="generate_pdf", payload={"n": 2}))
    assert await queue.size() == 2
    first = await queue.dequeue()
    assert first.payload == {"n": 1}  # FIFO
    assert (await queue.dequeue()).payload == {"n": 2}
    assert await queue.dequeue() is None


# ─── RedisBroker (fake client, no live Redis) ────────────────────────────────

async def test_redis_broker_publish_and_queue_use_namespaced_keys():
    fake = FakeAsyncRedis()
    broker = RedisBroker(client=fake)

    await broker.publish("evt.agent.running", "data")
    assert fake.published == [("ai_engine:evt.agent.running", "data")]

    await broker.push("queue.docs", "job1")
    assert await broker.queue_length("queue.docs") == 1
    assert await broker.pop("queue.docs") == "job1"
    await broker.push("queue.docs", "job2")
    assert await broker.pop("queue.docs", timeout=1) == "job2"  # blpop path
