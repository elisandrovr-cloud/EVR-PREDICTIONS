"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    PROJECT_NAME: str = "EVR MLB AI PRO"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # Database / cache
    DATABASE_URL: str = "postgresql+psycopg2://evr:evr_secret_change_me@localhost:5432/evr_mlb"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
