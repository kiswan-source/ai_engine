"""Task & Workflow state machine + tracker (MASTER_INSTRUCTION.md Bab 49).

Tasks and workflows share the same set of states (Bab 49.1). The manager tracks
each tracked id's current state and full transition history end-to-end
(roadmap Tahap 2 exit criteria), and enforces the legal transitions from the
Bab 49.2 diagram — illegal jumps raise instead of silently corrupting state.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from core.utils.logger import get_logger

logger = get_logger(__name__)


class State(str, Enum):
    """Task/Workflow lifecycle states (Bab 49.1)."""

    PENDING = "pending"
    PLANNING = "planning"
    RESEARCH = "research"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    RETRY = "retry"
    ROLLBACK = "rollback"


# Legal transitions per the Bab 49.2 state diagram.
_ALLOWED: dict[State, frozenset[State]] = {
    State.PENDING: frozenset({State.PLANNING, State.EXECUTING, State.CANCELLED}),
    State.PLANNING: frozenset({State.RESEARCH, State.EXECUTING, State.FAILED}),
    State.RESEARCH: frozenset({State.EXECUTING, State.FAILED}),
    State.EXECUTING: frozenset({State.REVIEWING, State.COMPLETED, State.FAILED, State.CANCELLED}),
    State.REVIEWING: frozenset({State.APPROVED, State.RETRY, State.CANCELLED}),
    State.APPROVED: frozenset({State.COMPLETED}),
    State.FAILED: frozenset({State.RETRY, State.ROLLBACK}),
    State.RETRY: frozenset({State.EXECUTING}),
    State.ROLLBACK: frozenset({State.PENDING}),
    State.COMPLETED: frozenset(),
    State.CANCELLED: frozenset(),
}

TERMINAL_STATES = frozenset({State.COMPLETED, State.CANCELLED})


class IllegalTransitionError(Exception):
    """Raised when an unsupported state transition is attempted."""


def can_transition(src: State, dst: State) -> bool:
    return dst in _ALLOWED.get(src, frozenset())


@dataclass
class TaskRecord:
    """Tracks one task/workflow's state and history."""

    tracked_id: str
    state: State = State.PENDING
    history: list[tuple[State, float]] = field(default_factory=list)
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.history:
            self.history.append((self.state, time.time()))

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES


class TaskStore(ABC):
    """Persistence seam for task records (Tahap 3): in-memory or Redis."""

    @abstractmethod
    def load(self, tracked_id: str) -> TaskRecord | None: ...

    @abstractmethod
    def save(self, record: TaskRecord) -> None: ...


class InMemoryTaskStore(TaskStore):
    """Process-local store — dev/CI default (no services, Bab 12)."""

    def __init__(self) -> None:
        self._records: dict[str, TaskRecord] = {}

    def load(self, tracked_id: str) -> TaskRecord | None:
        return self._records.get(tracked_id)

    def save(self, record: TaskRecord) -> None:
        self._records[record.tracked_id] = record


class RedisTaskStore(TaskStore):
    """Redis-backed store so task state survives restarts and is shared
    across orchestrator instances (Bab 18.2 — horizontally scalable).

    Uses the *sync* redis client: the TaskManager contract is synchronous and
    callers (the async orchestrator) must not gain awaits from a backend swap.

    Args:
        client: Optional pre-built ``redis.Redis`` (injected in tests).
    """

    _PREFIX = "task_state:"

    def __init__(self, client=None, ttl: int | None = None) -> None:
        if client is None:
            import redis

            from api.config import settings

            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        if ttl is None:
            from api.config import settings

            ttl = settings.TASK_STATE_TTL
        self._redis = client
        self._ttl = ttl

    def load(self, tracked_id: str) -> TaskRecord | None:
        raw = self._redis.get(self._PREFIX + tracked_id)
        if not raw:
            return None
        data = json.loads(raw)
        return TaskRecord(
            tracked_id=data["tracked_id"],
            state=State(data["state"]),
            history=[(State(s), ts) for s, ts in data["history"]],
            error=data.get("error"),
        )

    def save(self, record: TaskRecord) -> None:
        payload = json.dumps(
            {
                "tracked_id": record.tracked_id,
                "state": record.state.value,
                "history": [(s.value, ts) for s, ts in record.history],
                "error": record.error,
            }
        )
        self._redis.setex(self._PREFIX + record.tracked_id, self._ttl, payload)


def _default_store() -> TaskStore:
    from api.config import settings

    if settings.TASK_STATE_BACKEND.lower() == "redis":
        return RedisTaskStore()
    return InMemoryTaskStore()


class TaskManager:
    """Tracker for tasks and workflows over a pluggable :class:`TaskStore`.

    State lives in the store (not process globals) so the orchestrator stays
    stateless per Bab 18.2. The public contract is unchanged from Tahap 2 —
    swapping in Redis (``TASK_STATE_BACKEND=redis``) is config-only.
    """

    def __init__(self, store: TaskStore | None = None) -> None:
        self._store = store or _default_store()

    def track(self, tracked_id: str, initial: State = State.PENDING) -> TaskRecord:
        record = self._store.load(tracked_id)
        if record is not None:
            return record
        record = TaskRecord(tracked_id=tracked_id, state=initial)
        self._store.save(record)
        logger.info("task.track", tracked_id=tracked_id, state=initial.value)
        return record

    def transition(self, tracked_id: str, dst: State, error: str | None = None) -> TaskRecord:
        """Move a tracked id to ``dst``, validating the transition (Bab 49.2)."""
        record = self._store.load(tracked_id) or self.track(tracked_id)
        if record.state == dst:
            return record
        if not can_transition(record.state, dst):
            raise IllegalTransitionError(
                f"{tracked_id}: {record.state.value} -> {dst.value} is not allowed"
            )
        record.state = dst
        record.error = error
        record.history.append((dst, time.time()))
        self._store.save(record)
        logger.info("task.transition", tracked_id=tracked_id, to=dst.value, error=error)
        return record

    def get(self, tracked_id: str) -> TaskRecord | None:
        return self._store.load(tracked_id)

    def state_of(self, tracked_id: str) -> State | None:
        record = self._store.load(tracked_id)
        return record.state if record else None
