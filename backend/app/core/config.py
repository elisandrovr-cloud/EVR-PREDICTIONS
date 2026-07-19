"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DB_URL = "postgresql+psycopg2://evr:evr_secret_change_me@localhost:5432/evr_mlb"


def to_sqlalchemy_url(url: str) -> str:
    """Accept the connection strings Neon / Vercel Postgres / Supabase hand out
    (``postgres://…`` or ``postgresql://…``, often with ``?sslmode=require``) and
    return the psycopg2-qualified form SQLAlchemy needs. Idempotent."""
    if not url:
        return url
    if url.startswith("postgresql+"):  # already qualified (e.g. +psycopg2)
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg2://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg2://" + url[len("postgres://"):]
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    PROJECT_NAME: str = "EVR MLB AI PRO"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # Database / cache
    DATABASE_URL: str = _DEFAULT_DB_URL
    # Vercel's Neon/Postgres integration injects POSTGRES_URL; used as a fallback
    # when DATABASE_URL was not set explicitly.
    POSTGRES_URL: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # Security
    SECRET_KEY: str = "change_me_to_a_64_char_random_hex_string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    RATE_LIMIT_PER_MINUTE: int = 120
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost", "http://localhost:3000"]
    # Shared secret Vercel Cron (or any scheduler) must send as `Authorization:
    # Bearer <CRON_SECRET>` to trigger the /cron/* jobs. Empty ⇒ endpoint disabled.
    CRON_SECRET: str = ""

    # OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    OAUTH_REDIRECT_BASE: str = "http://localhost/api/v1/auth/oauth"

    # External providers
    ODDS_API_KEY: str = ""
    OPENWEATHER_API_KEY: str = ""
    MLB_STATS_API_BASE: str = "https://statsapi.mlb.com/api/v1"
    ODDS_API_BASE: str = "https://api.the-odds-api.com/v4"
    OPENWEATHER_API_BASE: str = "https://api.openweathermap.org/data/2.5"

    # Engine
    DATA_REFRESH_SECONDS: int = 120
    # Serverless self-seeding: when the DB is empty, read requests populate today's
    # slate on demand (no always-on worker needed). Disable on the container host
    # where Celery keeps data fresh.
    AUTO_SEED: bool = True
    MONTE_CARLO_ITERATIONS: int = 10_000
    MODELS_STORE_DIR: str = "models_store"
    MIN_EDGE_FOR_VALUE_BET: float = 0.03
    KELLY_FRACTION: float = 0.25

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("DATABASE_URL", "POSTGRES_URL", mode="before")
    @classmethod
    def _normalize_db_url(cls, v: object) -> object:
        return to_sqlalchemy_url(v) if isinstance(v, str) else v

    @model_validator(mode="after")
    def _fallback_to_postgres_url(self) -> "Settings":
        # If DATABASE_URL wasn't set (still the localhost default) but the platform
        # injected POSTGRES_URL (Vercel + Neon), use that instead.
        if self.DATABASE_URL == _DEFAULT_DB_URL and self.POSTGRES_URL:
            object.__setattr__(self, "DATABASE_URL", self.POSTGRES_URL)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
