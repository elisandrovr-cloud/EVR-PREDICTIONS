"""Test fixtures: isolated SQLite DB + FastAPI test client."""
from __future__ import annotations

import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="evr-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:63790/0")  # unreachable on purpose: code must fail open
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("MODELS_STORE_DIR", f"{_tmpdir}/models")
os.environ.setdefault("MONTE_CARLO_ITERATIONS", "2000")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.infrastructure.db.models import Base
from app.infrastructure.db import session as session_module


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture()
def db(engine):
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.rollback()
        # wipe all rows between tests for isolation
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()


@pytest.fixture()
def client(engine, db, monkeypatch):
    from app.main import app
    from app.infrastructure.db.session import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(session_module, "engine", engine)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
