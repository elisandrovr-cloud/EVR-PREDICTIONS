"""Vercel entrypoint for the native FastAPI runtime.

Vercel's Python/FastAPI framework imports this module and serves the ASGI
``app`` object directly. The real application lives in ``app.main``; this file
is the conventional top-level ``main.py`` entrypoint Vercel looks for (declared
as the backend service's ``entrypoint`` in vercel.json).
"""
from app.main import app

__all__ = ["app"]
