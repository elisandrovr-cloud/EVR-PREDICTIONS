"""Base HTTP provider with retries, latency tracking and source-status reporting."""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logging import get_logger

logger = get_logger(__name__)


class ProviderError(RuntimeError):
    pass


class BaseProvider:
    """All outbound data providers inherit from this adapter."""

    source_name: str = "base"
    base_url: str = ""
    timeout: float = 15.0

    def __init__(self) -> None:
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout, follow_redirects=True)
        self.last_latency_ms: float | None = None
        self.last_error: str | None = None
        self.last_success: datetime | None = None

    @property
    def enabled(self) -> bool:
        return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            resp = self._client.get(path, params=params)
            resp.raise_for_status()
            self.last_latency_ms = (time.perf_counter() - started) * 1000
            self.last_success = datetime.now(timezone.utc)
            self.last_error = None
            return resp.json()
        except httpx.HTTPError as exc:
            self.last_error = str(exc)
            logger.warning("provider request failed", extra={"source": self.source_name, "error": str(exc)})
            raise

    def report_status(self) -> dict[str, Any]:
        if not self.enabled:
            status = "disabled"
        elif self.last_error and not self.last_success:
            status = "down"
        elif self.last_error:
            status = "degraded"
        elif self.last_success:
            status = "ok"
        else:
            status = "unknown"
        return {
            "source": self.source_name,
            "status": status,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "latency_ms": self.last_latency_ms,
        }

    def close(self) -> None:
        self._client.close()
