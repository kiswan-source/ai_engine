-- Initialize extensions only. Table schemas are owned exclusively by
-- db/models.py, created via init_db()'s Base.metadata.create_all() on app
-- startup (CLAUDE.md: "No Alembic migrations ... schema changes require
-- manual migration or init_db() re-run") — this script must never define a
-- table, or a fresh volume gets that table from here (verbatim SQL, whatever
-- types were written by hand) while every other table (conversation_messages,
-- memory_entries, vector_embeddings, ...) comes from the ORM models, and the
-- two silently drift apart. That already happened once: this file used to
-- create gis_projects/ai_jobs/documents with `id UUID`, while db.models
-- declares `id String(36)` for all tables — create_all()'s CREATE TABLE IF
-- NOT EXISTS is a no-op when the table already exists, so the mismatch was
-- permanent until manually fixed (ALTER COLUMN id TYPE VARCHAR(36) on the
-- running DB, 2026-07-05; gis_projects' unused `geom` PostGIS column +
-- GIST index were dropped with it — nothing in the codebase reads them, the
-- ORM model stores geometry as `geojson JSON` instead).
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector; -- pgvector (Bab 29, Tahap 5)

SELECT PostGIS_Version();
