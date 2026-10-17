"""FastAPI dependencies: principal from the session cookie, roles, CSRF, RLS-scoped DB."""
from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Request
from sqlalchemy.engine import Connection, Engine

from ..core.db import transaction
from ..core.errors import AppError
from .service import Principal, csrf_matches, principal_for

SESSION_COOKIE = 'bazi_session'
CSRF_HEADER = 'X-CSRF-Token'
UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def engine(request: Request) -> Engine:
    return request.app.state.engine


def current_principal(request: Request, db_engine: Engine = Depends(engine)) -> Principal:
    token = request.cookies.get(SESSION_COOKIE)
    principal = None
    if token:
        with transaction(db_engine) as conn:
            principal = principal_for(conn, token)
    if principal is None:
        raise AppError(401, 'AUTH_REQUIRED', 'Sign in required')
    # Cookie-authenticated mutations must also prove they come from our page.
    if request.method in UNSAFE_METHODS and not csrf_matches(
            principal, request.headers.get(CSRF_HEADER)):
        raise AppError(403, 'CSRF_FAILED', 'Missing or invalid CSRF token')
    return principal


def require_role(role: str):
    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.has_role(role):
            raise AppError(403, 'FORBIDDEN', 'Insufficient role')
        return principal
    return dependency


def db(principal: Principal = Depends(current_principal),
       db_engine: Engine = Depends(engine)) -> Iterator[Connection]:
    """One transaction per request with app.user_id set for row-level security."""
    with transaction(db_engine, principal.user_id) as conn:
        yield conn
