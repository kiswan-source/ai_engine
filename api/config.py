"""Application configuration.

Non-secret parameters (thresholds, budgets, timeouts, active models,
feature flags) are centralized as versionable YAML under config/ (Bab 68
Backlog Prioritas 7, Configuration Center) — edit those files and restart
to change behavior without touching .env. Secrets (API keys, DB/Redis
connection strings) stay in .env / the deployment's secrets mechanism
(Bab 58 Secrets Management) and are never written to config/. Priority,
highest to lowest: init kwargs > env vars > .env > config/*.yaml >
the class-body default below (a fallback if config/ is ever missing).
"""
from pathlib import Path
from typing import List, Optional, Tuple, Type

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Engine"
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me"
    DEBUG: bool = True
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://aiuser:aipassword@localhost:5432/ai_engine"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    RQ_QUEUE_AI: str = "ai_queue"
    RQ_QUEUE_GIS: str = "gis_queue"
    RQ_QUEUE_PIPELINE: str = "pipeline_queue"

    # ─── Messaging & Memory (MASTER_INSTRUCTION.md Bab 22–23, Tahap 3) ──────
    # Physical broker for Message Bus / Event Bus / Task Queue (Bab 23):
    # "memory" (in-process; dev/CI) or "redis" (production, multi-process).
    MESSAGE_BROKER: str = "memory"
    # Volatile memory tiers — working/summary/reflection: "memory" or "redis".
    MEMORY_BACKEND: str = "memory"
    # Durable memory tiers — conversation/long-term: "memory" or "postgres".
    MEMORY_PERSISTENT_BACKEND: str = "memory"
    # Working Memory scope TTL in seconds (Bab 22 — volatile by design).
    WORKING_MEMORY_TTL: int = 3600
    # Task/Workflow state tracking (Bab 49): "memory" or "redis" (survives restarts).
    TASK_STATE_BACKEND: str = "memory"
    TASK_STATE_TTL: int = 86400

    # ─── Reflection / Consensus / Confidence / Human Approval (Bab 25-28, 57, 61, Tahap 4) ──
    # Reflection Engine (Bab 25): max self-review rounds before escalating.
    REFLECTION_MAX_ITERATIONS: int = 3
    # Confidence Scoring (Bab 28): per-domain thresholds — high-risk domains are stricter.
    CONFIDENCE_THRESHOLD_DEFAULT: float = 0.6
    CONFIDENCE_THRESHOLD_HIGH_RISK: float = 0.85
    # Consensus Engine (Bab 26): structured-debate rounds before arbitration.
    CONSENSUS_DEBATE_ROUNDS: int = 1
    # Feature flags (Bab 57).
    ENABLE_CONSENSUS_VOTING: bool = True
    ENABLE_HUMAN_APPROVAL: bool = True
    # Human In The Loop (Bab 61.3): SLA before a pending approval counts as overdue.
    APPROVAL_SLA_SECONDS: int = 3600
    # Pending-approval state (Bab 38 rule 1 — services must be stateless):
    # "memory" (dev/CI, single instance) or "redis" (survives pod restarts,
    # shared across replicas).
    APPROVAL_STATE_BACKEND: str = "memory"

    # ─── Provider Layer (MASTER_INSTRUCTION.md Bab 16) ───────────────────────
    # Shared timeout (seconds) for cloud provider HTTP calls (Bab 9 — timeout
    # mandatory on every external call).
    PROVIDER_TIMEOUT: int = 120
    # Fallback Strategy (Bab 54): retries on the same provider before switching.
    PROVIDER_MAX_RETRIES: int = 2
    PROVIDER_RETRY_BACKOFF: float = 1.0  # base seconds for exponential backoff

    # ─── Circuit Breaker (Bab 55, Tahap 9) ───────────────────────────────────
    ENABLE_CIRCUIT_BREAKER: bool = True
    # Defaults for providers without a per-provider override below.
    CIRCUIT_FAILURE_THRESHOLD: int = 5  # consecutive failures before Open
    CIRCUIT_RECOVERY_TIMEOUT: float = 30.0  # seconds Open before Half-Open
    CIRCUIT_TRIAL_REQUESTS: int = 1  # probes allowed in Half-Open
    # Per-provider tuning (Bab 55's rule: params must not be one-size-fits-all):
    # "openai:3/60/1,gemini:5/30/2" = threshold/recovery_seconds/trials.
    CIRCUIT_PROVIDER_OVERRIDES: str = ""
    # Breaker state: "memory" (per-process, dev/CI) or "redis" (shared across
    # replicas — Bab 38 rule 1, same pattern as APPROVAL_STATE_BACKEND).
    CIRCUIT_STATE_BACKEND: str = "memory"

    # OpenAI (ChatGPT) — orchestration, planning, review, QA.
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_EMBED_MODEL: str = "text-embedding-3-small"

    # Anthropic (Claude) — analysis, writing, coding, critique.
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_VERSION: str = "2023-06-01"
    CLAUDE_MODEL: str = "claude-sonnet-5"

    # Google (Gemini) — research, vision, documents.
    GOOGLE_API_KEY: str = ""
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta"
    GEMINI_MODEL: str = "gemini-pro-latest"
    GEMINI_EMBED_MODEL: str = "gemini-embedding-001"

    # ─── RAG (MASTER_INSTRUCTION.md Bab 29, Tahap 5) ─────────────────────────
    # Which provider's .embed() backs both Vector Memory (Bab 22) and the RAG
    # document corpus: "openai" | "gemini" | "ollama" | "hashed" (dependency-free
    # placeholder, Bab 12 — always available, used when no embedding key is set).
    RAG_EMBEDDING_PROVIDER: str = "openai"
    # Must match RAG_EMBEDDING_PROVIDER's output width (pgvector column is fixed
    # at table-creation time): openai text-embedding-3-small=1536,
    # gemini-embedding-001=3072, hashed placeholder=configurable (this value).
    RAG_EMBEDDING_DIM: int = 1536
    # Vector index backend: "memory" (in-process cosine, dev/CI default, Bab 12)
    # or "pgvector" (production, needs the `vector` extension on Postgres).
    VECTOR_BACKEND: str = "memory"
    # Chunking strategy (Bab 29 rule 1) — characters, not tokens (dependency-free).
    RAG_CHUNK_SIZE: int = 800
    RAG_CHUNK_OVERLAP: int = 100
    RAG_TOP_K: int = 5
    # Hybrid search weight (Bab 29 rule 2): 1.0 = pure semantic, 0.0 = pure keyword.
    RAG_HYBRID_ALPHA: float = 0.5
    RAG_RERANK_ENABLED: bool = True
    # context_builder.py's prompt-injection budget (chars, not tokens — cheap
    # and provider-agnostic; see BaseProvider.count_tokens for the token estimate
    # used elsewhere).
    RAG_MAX_CONTEXT_CHARS: int = 4000

    # ─── Telemetry (MASTER_INSTRUCTION.md Bab 27, 33-35, 56, Tahap 6) ────────
    # Execution timeline spans / cost usage records: "memory" (dev/CI) or
    # "redis" (production, survives restarts, shareable across instances).
    TRACE_BACKEND: str = "memory"
    COST_BACKEND: str = "memory"
    TRACE_MAX_SPANS_PER_TRACE: int = 200
    # In-process latency sample cap per (metric key) — bounds memory, not a
    # correctness knob (percentiles stay accurate enough over a rolling window).
    METRICS_MAX_SAMPLES: int = 2000
    # Cost Optimization (Bab 27 rule 4): budget that, once exceeded, escalates
    # to Human Approval (Bab 61.2) rather than completing silently.
    COST_BUDGET_PER_TASK: float = 5.0
    # Daily budget (Bab 27, 56): exceeding it surfaces as an alert (Bab 35 rule
    # 2), not an automatic block — no task/session context to escalate against.
    COST_BUDGET_DAILY: float = 50.0
    # Alert thresholds (Bab 35 rule 2).
    ALERT_ERROR_RATE_THRESHOLD: float = 0.2
    ALERT_LATENCY_P95_MS: int = 30000

    # ─── Security (MASTER_INSTRUCTION.md Bab 30, 31, 58, Tahap 7) ────────────
    # Prompt Injection detection (Bab 30): "neutralize" per rule 1 — above the
    # suspicious threshold the prompt is sanitized (not blocked); only above
    # the block threshold does the dispatch fail outright.
    ENABLE_PROMPT_GUARD: bool = True
    PROMPT_GUARD_SUSPICIOUS_THRESHOLD: float = 0.4
    PROMPT_GUARD_BLOCK_THRESHOLD: float = 0.8
    # PII redaction before a prompt leaves the system to an external provider
    # (Bab 30 table — "sebelum dikirim ke provider eksternal"; Ollama is local,
    # so it's exempt).
    ENABLE_PII_REDACTION: bool = True
    ENABLE_OUTPUT_VALIDATION: bool = True
    # Append-only audit trail (Bab 30 — distinct from the plain-text `audit.log`
    # this deployment's systemd unit already uses for general stdout capture).
    AUDIT_LOG_PATH: str = "security_audit.log"
    # Fase 1 (SEC-8, DCF_SECURITY_AUDIT_2026-07-11.md temuan #8): rotate
    # before the file grows past this size, keep this many numbered backups
    # (security_audit.log.1 .. .N). Hash-chain continuity is preserved
    # across rotation — see security/audit_log.py.
    AUDIT_LOG_MAX_BYTES: int = 10_000_000
    AUDIT_LOG_BACKUP_COUNT: int = 5
    # Comma-separated valid API keys for security.auth's principal lookup;
    # blank disables the dependency (dev default — matches no existing route
    # requiring auth today, Bab 45 no-big-rewrite).
    API_KEYS: str = ""

    # Automation / Scheduler (Bab 68 Prioritas 5) — in-process tick loop, not
    # a separate worker process; disable for tests/environments that don't
    # want background workflow runs firing on their own.
    ENABLE_SCHEDULER: bool = True
    SCHEDULER_TICK_SECONDS: int = 30

    # MCP — Model Context Protocol client (Bab 60, Bab 57.1 standard flag).
    # Gates `mcp_list_tools`/`mcp_call_tool` (agent/tools/registry.py) at
    # call time — the tools stay registered either way, they just refuse to
    # run when this is off (same pattern as the Bab 59 plugin toggle). Also
    # checked at startup by `mcp_server/server.py` (Tahap 28's MCP *Server*
    # side, the opposite direction) — same flag covers both.
    ENABLE_MCP: bool = True
    # Fixed role the MCP Server process runs as (Tahap 28) — stdio has no
    # per-request caller identity like an HTTP X-API-Key, so every tool call
    # through it is gated as this one role via security/permissions.py.
    # Default "user" is conservative: all read tools stay ungated, every
    # write/convert/generate tool is rejected until an operator explicitly
    # sets this to "operator" in the environment that spawns the server.
    MCP_SERVER_ROLE: str = "user"
    # Workspace access via MCP Server (Tahap 32, Bab 60.1 + 69.5) — same
    # config-bound identity idea as MCP_SERVER_ROLE above, applied to the
    # Project-role-scoped Workspace Permission system instead of the global
    # one. None (default) means workspace_list_files/workspace_read_file/
    # workspace_write_file stay excluded entirely — byte-for-byte Tahap 28's
    # original behavior, fully opt-in. There is no MCP caller identity to
    # look up a real ProjectMember for, so whoever configures this process
    # IS the identity: set to a real Workspace id + the Project role
    # (owner/editor/viewer) that process should be treated as holding.
    MCP_SERVER_WORKSPACE_ID: Optional[str] = None
    MCP_SERVER_WORKSPACE_ROLE: str = "viewer"

    # Domain Skills (Fase 5, DCF v5 mandate "Domain Generalization") — mining/
    # GIS is the platform's first domain skill, not a hard-wired assumption of
    # the core engine. Gates the mining/GIS agent tools
    # (agent/tools/registry.py::register_mining_gis_tools — read_kml,
    # calculate_area, convert_geo, write_geojson, write_shp) and the
    # gis/dokumen/pipeline routers (api/main.py) as one unit. Default True —
    # this deployment's actual domain, no behavior change. Setting it False is
    # what proves (not just claims) that core/orchestrator/agents/workflows/
    # chat don't need this domain — see tests/unit/test_domain_skill_toggle.py.
    ENABLE_MINING_GIS_SKILL: bool = True

    # Ollama / Gemma (local, always available)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    GEMMA_MODEL: str = "gemma4:e2b"
    OLLAMA_TIMEOUT: int = 600
    OLLAMA_MAX_RETRIES: int = 3
    # Context window. Ollama defaults to 4096 tokens when unset, which silently
    # truncates the oldest tokens (system prompt + injected file content) on long
    # turns — making the model appear to "not read" the uploaded file. Set it
    # explicitly; the Gemma models support up to 131072.
    OLLAMA_NUM_CTX: int = 16384

    # Cache TTL (seconds)
    AI_CACHE_TTL: int = 3600
    GIS_CACHE_TTL: int = 86400

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        yaml_file=[
            CONFIG_DIR / "providers.yaml",
            CONFIG_DIR / "agents.yaml",
            CONFIG_DIR / "workflow.yaml",
            CONFIG_DIR / "security.yaml",
            CONFIG_DIR / "memory.yaml",
            CONFIG_DIR / "budget.yaml",
            CONFIG_DIR / "domain_skills.yaml",
        ],
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()
