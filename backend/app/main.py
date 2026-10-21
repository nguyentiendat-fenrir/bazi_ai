"""FastAPI application factory.

Run with ``uvicorn backend.app.main:create_app --factory``. There is no
module-level app so importing this module never reads the environment.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from .api import (ask, assertions, auth, books, cases, charts, chat, evaluation, health, jobs,
                  judge, knowledge, models, ontology, openapi, operations, pages, pipelines,
                  releases, reviews, rules, rulesets, search, settings as settings_api, sources,
                  uploads, users)
from .auth.ratelimit import LoginLimiter
from .core.config import Settings, load_settings
from .core.crypto import FieldCipher
from .core.db import database_check, make_engine, runtime_role_check
from .core.errors import install_error_handlers
from .core.health import ReadinessCheck, default_checks
from .core.logging import configure_logging
from .core.middleware import OriginGuardMiddleware, RequestContextMiddleware
from .mcpserver import http as mcp_http
from .rag import deps as rag_deps
from .storage import ObjectStore, build_store, storage_check

API_PREFIX = '/api/v1'


def create_app(settings: Settings | None = None,
               readiness_checks: list[ReadinessCheck] | None = None,
               engine: Engine | None = None, store: ObjectStore | None = None,
               mcp_backend=None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level, settings.secret_values())
    public_docs = settings.app_env != 'production'

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Shared clients and CPU models live for the process, never per request (docs/09).
        await rag_deps.install(app, settings)
        async with mcp_http.lifespan(app):
            yield
        await rag_deps.uninstall(app)

    app = FastAPI(
        lifespan=lifespan,
        title='BAZI AI',
        openapi_url=f'{API_PREFIX}/openapi.json' if public_docs else None,
        docs_url=f'{API_PREFIX}/docs' if public_docs else None,
        redoc_url=None,
    )
    engine = engine or make_engine(settings.runtime_database_url)  # lazy: no connect yet
    app.state.settings = settings
    app.state.engine = engine
    app.state.store = store = store or build_store(settings)
    # Birth data is stored only when a field-encryption key is configured.
    app.state.cipher = (FieldCipher(settings.field_encryption_key.get_secret_value())
                        if settings.field_encryption_key else None)
    app.state.login_limiter = LoginLimiter(settings.login_max_failures,
                                           settings.login_window_seconds)
    app.state.readiness_checks = (readiness_checks if readiness_checks is not None else
                                  [database_check(engine), runtime_role_check(engine, settings),
                                   storage_check(store), *default_checks(settings),
                                   rag_deps.readiness(app)])
    install_error_handlers(app)
    # Added last runs first: request context wraps everything, origin guard inside it.
    app.add_middleware(OriginGuardMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(RequestContextMiddleware)
    for router in (health.router, auth.router, users.router, settings_api.router, books.router,
                   uploads.router, pages.router, releases.router, jobs.router, reviews.router,
                   knowledge.router, assertions.router, rules.router, cases.router,
                   ontology.router, search.router, evaluation.router, models.router,
                   pipelines.router, charts.router, rulesets.router, chat.router,
                   operations.router, ask.router, judge.router, sources.router):
        app.include_router(router, prefix=API_PREFIX)
    openapi.install(app)
    # MCP server of the RAG at /api/v1/mcp/ (bearer token), off unless configured.
    mcp_http.install(app, settings, API_PREFIX, mcp_backend)
    return app
