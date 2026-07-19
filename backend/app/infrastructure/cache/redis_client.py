"""Shared Redis connection pool + tiny JSON cache helpers."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

import redis

from app.core.config import settings


@lru_cache
def get_redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=3)


def cache_get(key: str) -> Any | None:
    try:
        raw = get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def cache_set(key: str, value: Any, ttl_seconds: int = 120) -> None:
    try:
        get_redis().setex(key, ttl_seconds, json.dumps(value, default=str))
    except Exception:  # noqa: BLE001
        pass
