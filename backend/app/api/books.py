"""Library catalog routes (docs/10 · Sách, upload, jobs và nguồn)."""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..core.concurrency import etag, require_if_match
from ..core.errors import AppError
from ..core.logging import request_id_var
from ..documents import catalog
from .health import envelope
from .schemas import (AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission,
                      problem_responses)

router = APIRouter(tags=['books'])
NOT_FOUND = problem_responses(404)


class AuthorRef(BaseModel):
    id: uuid.UUID
    name: str
    role: str


class BookDTO(BaseModel):
    id: uuid.UUID
    title: str
    language: str
    description: str | None
    authors: list[AuthorRef]
    versions_count: int
    active_coverage: dict | None
    revision: int


class Coverage(BaseModel):
    total: int
    accepted: int
    excluded: int
    failed: int


class VersionDTO(BaseModel):
    id: uuid.UUID
    book_id: uuid.UUID
    edition_label: str
    version_no: int
    sha256: str
    size_bytes: int
    mime: str
    status: Literal['active', 'withdrawn']
    rights_status: str
    external_processing_allowed: bool
    coverage: Coverage
    current_generation_id: uuid.UUID | None


class AuthorInput(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    role: Literal['author', 'commentator', 'translator', 'editor'] = 'author'


class BookInput(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    language: str = Field(default='vi', pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$')
    description: str | None = Field(default=None, max_length=5000)
    authors: list[AuthorInput] = Field(default=[], max_length=20)


class BookPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    language: str | None = Field(default=None, pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$')
    description: str | None = Field(default=None, max_length=5000)


class Grant(BaseModel):
    user_id: uuid.UUID | None = None
    role_scope: Literal['reader', 'reviewer', 'admin'] | None = None
    permission: Literal['read', 'review', 'manage']

    @model_validator(mode='after')
    def one_grantee(self) -> 'Grant':
        if (self.user_id is None) == (self.role_scope is None):
            raise ValueError('exactly one of user_id or role_scope')
        return self


class AccessInput(BaseModel):
    grants: list[Grant] = Field(max_length=200)


def _cursor(created_at: datetime, book_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f'{created_at.isoformat()}|{book_id}'.encode()).decode()


def _parse_cursor(cursor: str | None) -> tuple | None:
    if not cursor:
        return None
    try:
        stamp, book_id = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
        return datetime.fromisoformat(stamp), uuid.UUID(book_id)
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None


@router.get('/books', response_model=ListEnvelope[BookDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_books(q: str | None = Query(default=None, max_length=200),
               limit: int = Query(default=20, ge=1, le=100), cursor: str | None = None,
               principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    rows = catalog.list_books(conn, principal, q, limit + 1, _parse_cursor(cursor))
    page, more = rows[:limit], len(rows) > limit
    return {**envelope(catalog.book_dtos(conn, page)),
            'page': {'next_cursor': _cursor(page[-1]['created_at'], page[-1]['id'])
                     if more else None, 'has_more': more}}


@router.post('/books', status_code=201, response_model=Envelope[BookDTO],
             responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def create_book(body: BookInput, response: Response,
                principal: Principal = Depends(require_role('reviewer')),
                conn: Connection = Depends(db)) -> dict:
    book_id = catalog.create_book(conn, principal, body.title, body.language, body.description,
                                  [a.model_dump() for a in body.authors])
    book = catalog.get_book(conn, principal, book_id)
    response.headers['ETag'] = etag(book['revision'])
    return envelope(book)


@router.get('/books/{book_id}', response_model=Envelope[BookDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_book(book_id: uuid.UUID, response: Response,
             principal: Principal = Depends(current_principal),
             conn: Connection = Depends(db)) -> dict:
    book = catalog.get_book(conn, principal, book_id)
    response.headers['ETag'] = etag(book['revision'])
    return envelope(book)


@router.patch('/books/{book_id}', response_model=Envelope[BookDTO],
              responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(412, 428)},
              openapi_extra=permission('V'))
def patch_book(book_id: uuid.UUID, body: BookPatch, request: Request, response: Response,
               principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    current = catalog.book_revision(conn, book_id)
    if current is None:
        raise AppError(404, 'NOT_FOUND', 'Book not found')
    require_if_match(request, current)
    catalog.update_book(conn, book_id, body.model_dump())
    book = catalog.get_book(conn, principal, book_id)
    response.headers['ETag'] = etag(book['revision'])
    return envelope(book)


@router.get('/books/{book_id}/access', response_model=Envelope[list[Grant]],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def get_access(book_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    catalog.get_book(conn, principal, book_id)
    return envelope(catalog.list_access(conn, book_id))


@router.patch('/books/{book_id}/access', response_model=Envelope[list[Grant]],
              responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(412, 428)},
              openapi_extra=permission('A'))
def put_access(book_id: uuid.UUID, body: AccessInput, request: Request,
               principal: Principal = Depends(require_role('admin')),
               conn: Connection = Depends(db)) -> dict:
    current = catalog.book_revision(conn, book_id)
    if current is None:
        raise AppError(404, 'NOT_FOUND', 'Book not found')
    require_if_match(request, current)
    catalog.replace_access(conn, principal, book_id,
                           [g.model_dump(mode='json') for g in body.grants], request_id_var.get())
    return envelope(catalog.list_access(conn, book_id))


@router.get('/books/{book_id}/versions', response_model=ListEnvelope[VersionDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def versions(book_id: uuid.UUID, principal: Principal = Depends(current_principal),
             conn: Connection = Depends(db)) -> dict:
    catalog.get_book(conn, principal, book_id)
    return {**envelope(catalog.list_versions(conn, book_id)),
            'page': {'next_cursor': None, 'has_more': False}}


@router.get('/book-versions/{version_id}', response_model=Envelope[VersionDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_version(version_id: uuid.UUID, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return envelope(catalog.get_version(conn, principal, version_id))
