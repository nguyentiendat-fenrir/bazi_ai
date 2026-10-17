"""Admin user management (docs/10). The last active admin is protected in the DB."""
from __future__ import annotations

from typing import Literal
import uuid

from fastapi import APIRouter, Depends
from psycopg import errors as pg_errors
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

from ..auth.deps import db, require_role
from ..auth.passwords import MAX_LENGTH, MIN_LENGTH
from ..auth.service import create_user, list_users, update_user
from ..core.errors import AppError
from .auth import Email
from .health import envelope

router = APIRouter(prefix='/users', tags=['users'], dependencies=[Depends(require_role('admin'))])
Role = Literal['admin', 'reviewer', 'reader']


class UserCreate(BaseModel):
    email: Email
    password: str = Field(min_length=MIN_LENGTH, max_length=MAX_LENGTH)
    role: Role


class UserPatch(BaseModel):
    role: Role | None = None
    enabled: bool | None = None


def user_dto(row: dict) -> dict:
    return {'id': str(row['id']), 'email': row['email'], 'role': row['role'],
            'enabled': row['enabled'], 'locale': row['locale'],
            'created_at': row['created_at'].isoformat(),
            'updated_at': row['updated_at'].isoformat()}


def _db_conflict(exc: DBAPIError) -> AppError | None:
    if isinstance(exc.orig, pg_errors.UniqueViolation):
        return AppError(409, 'CONFLICT', 'A user with this email already exists')
    if isinstance(exc.orig, pg_errors.CheckViolation) and 'last active admin' in str(exc.orig):
        return AppError(409, 'LAST_ADMIN', 'The last active admin cannot be disabled or demoted')
    return None


@router.get('')
def users(conn: Connection = Depends(db)) -> dict:
    return envelope([user_dto(r) for r in list_users(conn)])


@router.post('', status_code=201)
def create(body: UserCreate, conn: Connection = Depends(db)) -> dict:
    try:
        with conn.begin_nested():
            row = create_user(conn, body.email, body.password, body.role)
    except DBAPIError as exc:
        raise _db_conflict(exc) or exc
    return envelope(user_dto(row))


@router.patch('/{user_id}')
def patch(user_id: uuid.UUID, body: UserPatch, conn: Connection = Depends(db)) -> dict:
    try:
        with conn.begin_nested():
            row = update_user(conn, user_id, body.model_dump())
    except DBAPIError as exc:
        raise _db_conflict(exc) or exc
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'User not found')
    return envelope(user_dto(row))
