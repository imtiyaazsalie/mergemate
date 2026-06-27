"""
MergeMate health-check server.

Provides liveness (``GET /health``) and readiness (``GET /ready``) endpoints
suitable for container orchestrators.
"""

from __future__ import annotations

from fastapi import FastAPI

APP_VERSION = "1.0.0"

app = FastAPI(title="MergeMate Health", version=APP_VERSION)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe — always returns ok when the process is running."""
    return {"status": "ok", "version": APP_VERSION}


@app.get("/ready")
async def ready() -> dict[str, str | bool]:
    """Readiness probe — verifies the configuration subsystem can load."""
    try:
        from mergemate.config_loader import get_settings  # noqa: PLC0415

        get_settings()
        return {"status": "ready", "config_loaded": True}
    except Exception:
        return {"status": "not ready", "config_loaded": False}
