-- Initialize PostGIS extensions and base schema
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- GIS Projects with geometry column
CREATE TABLE IF NOT EXISTS gis_projects (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(256) NOT NULL,
    location    VARCHAR(512),
    commodity   VARCHAR(128),
    area_ha     DOUBLE PRECISION,
    geom        GEOMETRY(MULTIPOLYGON, 4326),
    status      VARCHAR(32) DEFAULT 'draft',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gis_projects_geom ON gis_projects USING GIST(geom);

-- AI Jobs log
CREATE TABLE IF NOT EXISTS ai_jobs (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type      VARCHAR(64) NOT NULL,
    status        VARCHAR(32) DEFAULT 'queued',
    prompt        TEXT,
    result        TEXT,
    error         TEXT,
    model         VARCHAR(64) DEFAULT 'gemma3:27b',
    duration_ms   INTEGER,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    completed_at  TIMESTAMPTZ
);

-- Documents store
CREATE TABLE IF NOT EXISTS documents (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename      VARCHAR(512) NOT NULL,
    doc_type      VARCHAR(64),
    content_text  TEXT,
    summary       TEXT,
    entities      JSONB,
    word_count    INTEGER,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

SELECT PostGIS_Version();
