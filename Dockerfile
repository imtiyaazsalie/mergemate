# ── Base stage ──────────────────────────────────────────────
FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install --no-install-recommends -y git curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies in a cached layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Prod stage ──────────────────────────────────────────────
FROM base AS prod

# Create non-root user
RUN groupadd -r mergemate && useradd -r -g mergemate mergemate

# Copy application code
COPY --chown=mergemate:mergemate mergemate/ mergemate/

USER mergemate

ENV PYTHONPATH=/app

ENTRYPOINT ["python", "-m", "mergemate.cli"]
