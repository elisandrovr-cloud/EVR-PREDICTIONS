"""EVR MLB AI PRO — FastAPI application entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimitMiddleware, SecurityHeadersMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    # Create schema on boot (Alembic owns migrations in production upgrades;
    # create_all is a no-op for existing tables and makes first boot turnkey).
    from app.infrastructure.db.models import Base
    from app.infrastructure.db.session import engine

    Base.metadata.create_all(bind=engine)
    logger.info("startup complete", extra={"env": settings.ENVIRONMENT})
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=__version__,
    description=(
        "AI-driven MLB betting analytics: daily probabilities for every market, "
        "value-bet detection, auto-generated parlays and a self-learning ensemble engine."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
