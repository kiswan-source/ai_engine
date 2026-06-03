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

    # Ollama / Gemma
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
