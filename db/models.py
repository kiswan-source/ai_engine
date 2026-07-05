"""SQLAlchemy ORM models."""
import uuid
from datetime import datetime
from sqlalchemy import String, Float, Integer, DateTime, Text, JSON, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from api.config import settings
from db.connection import Base


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    prompt: Mapped[str] = mapped_column(Text)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(64), default="gemma4:26b")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class GISProject(Base):
    __tablename__ = "gis_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(256))
    location: Mapped[str] = mapped_column(String(512))
    commodity: Mapped[str | None] = mapped_column(String(128), nullable=True)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    geojson: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ConversationMessage(Base):
    """One chat message in Conversation Memory (MASTER_INSTRUCTION.md Bab 22)."""

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(32))  # user | assistant | system | tool
    content: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MemoryEntry(Base):
    """One long-term memory fact, keyed by (namespace, key) (Bab 22)."""

    __tablename__ = "memory_entries"
    __table_args__ = (UniqueConstraint("namespace", "key", name="uq_memory_namespace_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    key: Mapped[str] = mapped_column(String(256))
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename: Mapped[str] = mapped_column(String(512))
    doc_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VectorEmbedding(Base):
    """Shared pgvector-backed store (MASTER_INSTRUCTION.md Bab 22 Vector Memory
    tier + Bab 29 RAG document corpus — one table, distinguished by
    ``namespace`` (e.g. ``"memory:writer"`` vs ``"rag:documents"``) rather than
    two near-identical schemas. Requires the Postgres ``vector`` extension
    (``VECTOR_BACKEND=pgvector``; ``CREATE EXTENSION vector`` — see
    scripts/init_db.sql / docker/Dockerfile.postgres).

    The column width is fixed at table-creation time to ``RAG_EMBEDDING_DIM``
    — changing embedding provider/model to a different dimension requires
    re-indexing into a fresh table, not just a config change.
    """

    __tablename__ = "vector_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    namespace: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.RAG_EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Project(Base):
    """Phase 3 entity (PROJECT_SPECIFICATION.md) — a long-lived grouping of
    work (Conversation/Workflow/File), not a replacement for either.

    ``owner_key``/``ProjectMember.principal_key`` hold the API key string
    from ``security.auth.Principal`` rather than a ``user_id`` FK —
    PROJECT_SPECIFICATION.md §3 speaks of ``owner_id (FK → User)``, but
    there is no ``User`` table anywhere in this system today (identity is
    just an API key mapped to a role, `security/auth.py`). Adapted to the
    actual identity primitive that exists, not a literal reading of the
    spec's placeholder schema.

    §6 left soft-delete vs. hard-delete undecided; this picks soft-delete
    (``status="archived"``) — reversible, consistent with Bab 3 "Preserve
    Existing Code" applied to user data, not just code.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_key: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | archived
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ProjectMember(Base):
    """One (project, principal) membership row (PROJECT_SPECIFICATION.md §3)."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "principal_key", name="uq_project_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    principal_key: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32), default="viewer")  # owner | editor | viewer
    added_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScheduledJob(Base):
    """Automation entity (Bab 68 Prioritas 5) — a workflow run on a recurring
    interval, not a one-off request.

    Deliberately simple trigger model for this first pass: a plain
    ``interval_seconds`` ("every N seconds"), not full cron syntax — cron
    parsing/timezone handling is a separate scope decision for later, and an
    interval is enough to prove the whole mechanism (schedule -> fires on
    its own -> records a result) actually works.

    ``owner_key`` mirrors ``Project.owner_key`` — the API key string is the
    only real identity primitive in this system (see that model's
    docstring), not a literal ``user_id`` FK.

    Deletion here is a real hard delete, unlike ``Project``'s soft-delete:
    a schedule definition is closer to a setting than to organizational
    data worth preserving, and ``enabled=False`` already covers "stop this
    without losing the definition" — recreating a deleted one is trivial.
    """

    __tablename__ = "scheduled_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(256))
    prompt: Mapped[str] = mapped_column(Text)
    roles: Mapped[list] = mapped_column(JSON)
    mode: Mapped[str] = mapped_column(String(32), default="sequential")
    interval_seconds: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(default=True)
    owner_key: Mapped[str] = mapped_column(String(128), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)  # success | failed
    last_result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
