"""FastAPI application factory.

Run with ``uvicorn backend.app.main:create_app --factory``. There is no
module-level app so importing this module never reads the environment.
"""
from __future__ import annotations

from fastapi import FastAPI

from .api import health
from .core.config import Settings, load_settings
from .core.errors import install_error_handlers
from .core.health import ReadinessCheck, default_checks
from .core.logging import configure_logging
from .core.middleware import RequestContextMiddleware

API_PREFIX = '/api/v1'


def create_app(settings: Settings | None = None,
               readiness_checks: list[ReadinessCheck] | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level, settings.secret_values())
    public_docs = settings.app_env != 'production'
    app = FastAPI(
        title='BAZI AI',
        openapi_url=f'{API_PREFIX}/openapi.json' if public_docs else None,
        docs_url=f'{API_PREFIX}/docs' if public_docs else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.readiness_checks = (readiness_checks if readiness_checks is not None
                                  else default_checks(settings))
    install_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(health.router, prefix=API_PREFIX)
    return app
