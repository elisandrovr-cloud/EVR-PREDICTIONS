"""SQLAlchemy engine/session factory."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

_schema_ready = False


def ensure_schema() -> None:
    """Create tables if they don't exist. Idempotent and cheap after the first
    call (guarded per process), so it can be invoked lazily on serverless
    platforms where the ASGI lifespan startup may not run."""
    global _schema_ready
    if _schema_ready:
        return
    from app.infrastructure.db.models import Base

    Base.metadata.create_all(bind=engine)
    _schema_ready = True


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
