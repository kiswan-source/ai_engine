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
