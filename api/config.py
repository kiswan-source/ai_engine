"""Application configuration via environment variables."""
from typing import List
from pydantic_settings import BaseSettings


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

    # ─── Provider Layer (MASTER_INSTRUCTION.md Bab 16) ───────────────────────
    # Shared timeout (seconds) for cloud provider HTTP calls (Bab 9 — timeout
    # mandatory on every external call).
    PROVIDER_TIMEOUT: int = 120
    # Fallback Strategy (Bab 54): retries on the same provider before switching.
    PROVIDER_MAX_RETRIES: int = 2
    PROVIDER_RETRY_BACKOFF: float = 1.0  # base seconds for exponential backoff

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
    GEMINI_EMBED_MODEL: str = "text-embedding-004"

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

settings = Settings()
