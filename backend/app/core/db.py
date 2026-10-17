"""Database access: one engine per app, one transaction per request.

``transaction(engine, user_id)`` sets ``app.user_id`` with ``SET LOCAL`` semantics
so row-level security (M008) sees the authenticated principal and nothing leaks
to the next transaction on a pooled connection. Code never trusts a user id
from headers; it comes from the session lookup.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, URL

from .config import Settings
from .health import CheckResult, ReadinessCheck


def make_engine(url: URL) -> Engine:
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)


@contextmanager
def transaction(engine: Engine, user_id: uuid.UUID | None = None) -> Iterator[Connection]:
    with engine.begin() as conn:
        # set_config(..., true) is transaction-local; '' keeps owner-scoped rows hidden.
        conn.execute(text("SELECT set_config('app.user_id', :uid, true)"),
                     {'uid': str(user_id) if user_id else ''})
        yield conn


def database_check(engine: Engine) -> ReadinessCheck:
    async def run() -> CheckResult:
        from starlette.concurrency import run_in_threadpool

        def ping() -> None:
            with engine.connect() as conn:
                conn.execute(text('SELECT 1'))
        await run_in_threadpool(ping)
        return CheckResult('ok', 'REACHABLE')
    return ReadinessCheck('database', essential=True, run=run)


def runtime_role_check(engine: Engine, settings: Settings) -> ReadinessCheck:
    """The API must not connect as a role that bypasses row-level security."""
    async def run() -> CheckResult:
        from starlette.concurrency import run_in_threadpool

        def inspect() -> bool:
            with engine.connect() as conn:
                # Table owners also skip RLS (policies are not FORCEd).
                return conn.execute(text(
                    'SELECT rolsuper OR rolbypassrls OR EXISTS (SELECT 1 FROM pg_tables'
                    " WHERE schemaname = 'public' AND tableowner = current_user)"
                    ' FROM pg_roles WHERE rolname = current_user')).scalar_one()
        bypasses = await run_in_threadpool(inspect)
        if not bypasses:
            return CheckResult('ok', 'RLS_ENFORCED')
        # Dev may run as the owner for convenience; production must not.
        return CheckResult('fail' if settings.app_env == 'production' else 'degraded',
                           'RLS_BYPASS_ROLE')
    return ReadinessCheck('database_role', essential=True, run=run)
