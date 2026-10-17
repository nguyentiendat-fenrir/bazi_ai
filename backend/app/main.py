"""FastAPI application factory.

Run with ``uvicorn backend.app.main:create_app --factory``. There is no
module-level app so importing this module never reads the environment.
"""
from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from .api import (assertions, auth, books, health, jobs, knowledge, pages, releases, reviews,
                  rules, settings as settings_api, uploads, users)
from .auth.ratelimit import LoginLimiter
from .core.config import Settings, load_settings
from .core.db import database_check, make_engine, runtime_role_check
from .core.errors import install_error_handlers
from .core.health import ReadinessCheck, default_checks
from .core.logging import configure_logging
from .core.middleware import OriginGuardMiddleware, RequestContextMiddleware
from .storage import ObjectStore, build_store, storage_check

API_PREFIX = '/api/v1'


def create_app(settings: Settings | None = None,
               readiness_checks: list[ReadinessCheck] | None = None,
               engine: Engine | None = None, store: ObjectStore | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level, settings.secret_values())
    public_docs = settings.app_env != 'production'
    app = FastAPI(
        title='BAZI AI',
        openapi_url=f'{API_PREFIX}/openapi.json' if public_docs else None,
        docs_url=f'{API_PREFIX}/docs' if public_docs else None,
        redoc_url=None,
    )
    engine = engine or make_engine(settings.runtime_database_url)  # lazy: no connect yet
    app.state.settings = settings
    app.state.engine = engine
    app.state.store = store = store or build_store(settings)
    app.state.login_limiter = LoginLimiter(settings.login_max_failures,
                                           settings.login_window_seconds)
    app.state.readiness_checks = (readiness_checks if readiness_checks is not None else
                                  [database_check(engine), runtime_role_check(engine, settings),
                                   storage_check(store), *default_checks(settings)])
    install_error_handlers(app)
    # Added last runs first: request context wraps everything, origin guard inside it.
    app.add_middleware(OriginGuardMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(RequestContextMiddleware)
    for router in (health.router, auth.router, users.router, settings_api.router, books.router,
                   uploads.router, pages.router, releases.router, jobs.router, reviews.router,
                   knowledge.router, assertions.router, rules.router):
        app.include_router(router, prefix=API_PREFIX)
    return app
