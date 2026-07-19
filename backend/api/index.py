"""Vercel Python (serverless) entrypoint.

The @vercel/python runtime imports the module-level ``app`` object and serves it
as an ASGI application. We add the backend package root to sys.path so
``app.main`` resolves regardless of the function's working directory.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app  # noqa: E402

__all__ = ["app"]
