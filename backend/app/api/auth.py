"""Session login/logout and the current user (docs/10 · Routes xác thực và cấu hình).

There is no public registration: accounts are created by an admin (``/users``)
or, for the first admin, by the local bootstrap CLI.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy.engine import Engine

from ..auth.deps import SESSION_COOKIE, current_principal, engine
from ..auth.erasure import erase
from ..auth.service import Principal, authenticate, create_session, revoke_session
from ..core.db import transaction
from ..core.errors import AppError
from ..core.logging import request_id_var
from .health import envelope
from .schemas import (AUTHENTICATED_ERRORS, COMMON_ERRORS, Envelope, LoginResult, MeDTO,
                      permission, problem_responses)

router = APIRouter(prefix='/auth', tags=['auth'])
# Shape check only; deliverability is irrelevant for local accounts.
Email = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254,
                                         pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]+$')]


class LoginInput(BaseModel):
    email: Email
    password: str = Field(min_length=1, max_length=1024)


def user_dto(principal: Principal) -> dict:
    return {'id': str(principal.user_id), 'email': principal.email, 'role': principal.role,
            'capabilities': principal.capabilities}


@router.post('/login', response_model=Envelope[LoginResult],
             responses={**COMMON_ERRORS, **problem_responses(401, 403, 429)},
             openapi_extra=permission('public + rate limit'))
def login(body: LoginInput, request: Request, response: Response,
          db_engine: Engine = Depends(engine)) -> dict:
    settings = request.app.state.settings
    limiter = request.app.state.login_limiter
    email = body.email
    client = request.client.host if request.client else 'unknown'
    keys = (f'ip:{client}', f'email:{email}')
    if wait := limiter.retry_after(*keys):
        raise AppError(429, 'RATE_LIMITED', 'Too many failed sign-in attempts',
                       headers={'Retry-After': str(wait)})
    with transaction(db_engine) as conn:
        user = authenticate(conn, email, body.password)
        session = (create_session(conn, user, timedelta(hours=settings.session_ttl_hours))
                   if user else None)
    if session is None:
        limiter.failure(*keys)
        # One message for unknown email, wrong password and disabled account.
        raise AppError(401, 'AUTH_REQUIRED', 'Invalid email or password')
    limiter.success(*keys)
    response.set_cookie(SESSION_COOKIE, session.token, httponly=True, samesite='strict',
                        secure=settings.cookie_secure, path='/',
                        max_age=settings.session_ttl_hours * 3600)
    return envelope({'user': user_dto(session.principal), 'csrf_token': session.csrf_token})


@router.post('/logout', status_code=204, responses=AUTHENTICATED_ERRORS,
             openapi_extra=permission('R'))
def logout(response: Response, principal: Principal = Depends(current_principal),
           db_engine: Engine = Depends(engine)) -> Response:
    with transaction(db_engine, principal.user_id) as conn:
        revoke_session(conn, principal.session_id)
    response.status_code = 204
    response.delete_cookie(SESSION_COOKIE, path='/')
    return response


@router.get('/me', response_model=Envelope[MeDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def me(principal: Principal = Depends(current_principal)) -> dict:
    return envelope(user_dto(principal))


class ErasureInput(BaseModel):
    confirm: str = Field(min_length=1, max_length=254, description='the account email')
    delete_account: bool = False


class SelfErasureInput(ErasureInput):
    password: str = Field(min_length=1, max_length=1024)


class ErasureResult(BaseModel):
    user_id: str
    account_deleted: bool
    counts: dict[str, int] = Field(description='rows removed per kind; no content')


@router.post('/erasure', response_model=Envelope[ErasureResult],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('O'))
def erase_own_data(body: SelfErasureInput, response: Response,
                   principal: Principal = Depends(current_principal),
                   db_engine: Engine = Depends(engine)) -> dict:
    """Hard-delete the caller's charts, profiles, conversations, private cases and settings;
    with ``delete_account`` also sign-in. Library content and reviewed knowledge stay."""
    with transaction(db_engine, principal.user_id) as conn:
        result = erase(conn, principal.user_id, principal.user_id, body.confirm,
                       body.delete_account, body.password, request_id_var.get() or '')
    if body.delete_account:
        response.delete_cookie(SESSION_COOKIE, path='/')
    return envelope(result)
