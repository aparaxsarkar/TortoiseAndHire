FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libpq5: psycopg's binary wheel still links libpq at runtime on slim.
# curl: the HEALTHCHECK. Then a non-root runtime user.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

COPY pyproject.toml alembic.ini README.md ./
COPY app ./app
COPY migrations ./migrations
COPY config ./config
COPY scripts ./scripts

RUN pip install --no-cache-dir .

USER app
EXPOSE 8000

# Liveness only - readiness (`/health/ready`, which checks the DB) is the
# platform's health check so a DB outage doesn't kill the container.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -fs http://localhost:8000/api/v1/health || exit 1

# Migrations run out-of-band (Render pre-deploy / `make migrate`), never here -
# see ADR-0006.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
