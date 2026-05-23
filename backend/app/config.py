"""CortexFlow application settings — all config via environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────────
    APP_NAME: str = "CortexFlow"
    APP_ENV: Literal["development", "staging", "production", "test"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 60

    # ── Database — PostgreSQL ─────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://cortex:cortex@localhost:5432/cortexflow"

    # ── Database — Redis ──────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    REDIS_PASSWORD: str = ""

    # ── Database — Qdrant ─────────────────────────────────────────────────────
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""

    # ── Database — Neo4j ──────────────────────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "cortexflow"

    # ── AI Models ─────────────────────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # ── Integrations ──────────────────────────────────────────────────────────
    GITHUB_WEBHOOK_SECRET: str = ""   # HMAC secret for GitHub webhook verification

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ── Observability ─────────────────────────────────────────────────────────
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    PROMETHEUS_PORT: int = 9090


@lru_cache
def get_settings() -> Settings:
    return Settings()
