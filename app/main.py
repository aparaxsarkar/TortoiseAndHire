"""FastAPI application factory.

`create_app()` is the composition root: it reads settings, configures logging,
installs middleware, and mounts routers. `app` at module scope is what uvicorn
serves (`uvicorn app.main:app`, matching docker/Dockerfile).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.routes import health, ingestion, jobs
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.core.observability import TimingMiddleware

API_V1_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    log = get_logger("app")

    app = FastAPI(title="TortoiseAndHire", version="0.1.0")
    app.add_middleware(TimingMiddleware)
    install_error_handlers(app)
    for router in (health.router, jobs.router, ingestion.router):
        app.include_router(router, prefix=API_V1_PREFIX)

    log.info("app.created", env=settings.env)
    return app


app = create_app()
