"""The ASGI entry point.

Separate from `app.py` so `create_app` stays a plain factory a test can call with its own
settings, while deployment has one stable import path with no arguments to get wrong:

    python -m uvicorn skutruth.api.asgi:app --app-dir backend --port 8000
"""

from __future__ import annotations

from .app import create_app

app = create_app()

__all__ = ["app"]
