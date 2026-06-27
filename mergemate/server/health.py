"""
MergeMate health-check server.

Provides liveness (``GET /health``) and readiness (``GET /ready``) endpoints
suitable for container orchestrators.

Security: when ``MERGEMATE_HEALTH_TOKEN`` is set, requests must include an
``X-MergeMate-Token`` header matching that value.
"""

from __future__ import annotations

import os

from fastapi import Depends, FastAPI, Header, HTTPException

APP_VERSION = "1.0.0"

HEALTH_TOKEN = os.environ.get("MERGEMATE_HEALTH_TOKEN", "")


async def _verify_health_token(
    x_mergemate_token: str | None = Header(default=None, alias="X-MergeMate-Token"),
) -> None:
    """Raise 401 if a health token is configured and the request doesn't match."""
    if HEALTH_TOKEN and x_mergemate_token != HEALTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid or missing health token")


app = FastAPI(
    title="MergeMate Health",
    version=APP_VERSION,
    dependencies=[Depends(_verify_health_token)] if HEALTH_TOKEN else [],
)


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
