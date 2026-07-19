"""Config: connection-string normalization for Neon / Vercel / Supabase."""
from __future__ import annotations

from app.core.config import Settings, to_sqlalchemy_url


class TestDatabaseUrlNormalization:
    def test_neon_postgresql_scheme(self) -> None:
        raw = "postgresql://user:pass@ep-cool-name.us-east-2.aws.neon.tech/neondb?sslmode=require"
        out = to_sqlalchemy_url(raw)
        assert out.startswith("postgresql+psycopg2://")
        assert "sslmode=require" in out
        assert "ep-cool-name" in out

    def test_short_postgres_scheme(self) -> None:
        raw = "postgres://user:pass@host/db?sslmode=require&channel_binding=require"
        out = to_sqlalchemy_url(raw)
        assert out.startswith("postgresql+psycopg2://")
        assert "channel_binding=require" in out

    def test_already_qualified_is_unchanged(self) -> None:
        raw = "postgresql+psycopg2://u:p@localhost:5432/db"
        assert to_sqlalchemy_url(raw) == raw

    def test_empty_passthrough(self) -> None:
        assert to_sqlalchemy_url("") == ""

    def test_settings_normalizes_env_value(self) -> None:
        s = Settings(DATABASE_URL="postgres://u:p@ep.neon.tech/db?sslmode=require")
        assert s.DATABASE_URL.startswith("postgresql+psycopg2://")

    def test_settings_falls_back_to_postgres_url(self) -> None:
        # DATABASE_URL at its default, POSTGRES_URL provided (Vercel + Neon).
        # (conftest sets DATABASE_URL in the env, so pass the default explicitly.)
        from app.core.config import _DEFAULT_DB_URL

        s = Settings(
            DATABASE_URL=_DEFAULT_DB_URL,
            POSTGRES_URL="postgresql://u:p@ep.neon.tech/db?sslmode=require",
        )
        assert s.DATABASE_URL.startswith("postgresql+psycopg2://")
        assert "ep.neon.tech" in s.DATABASE_URL

    def test_explicit_database_url_wins_over_postgres_url(self) -> None:
        s = Settings(
            DATABASE_URL="postgresql://a:b@primary/db1",
            POSTGRES_URL="postgresql://c:d@secondary/db2",
        )
        assert "primary" in s.DATABASE_URL
