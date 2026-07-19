"""Redis-backed sliding-window rate limiting middleware."""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings
from app.infrastructure.cache.redis_client import get_redis


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP sliding window limiter. Fails open if Redis is unreachable."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in ("/api/v1/health", "/openapi.json"):
            return await call_next(request)
        client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        key = f"ratelimit:{client_ip}"
        now = time.time()
        window = 60.0
        try:
            r = get_redis()
            pipe = r.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {f"{now}": now})
            pipe.zcard(key)
            pipe.expire(key, int(window) + 1)
            _, _, count, _ = pipe.execute()
            if int(count) > settings.RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Try again shortly."},
                    headers={"Retry-After": "10"},
                )
        except Exception:  # noqa: BLE001 — availability over strictness
            pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Helmet-style hardening headers on every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Cache-Control", "no-store")
        return response
