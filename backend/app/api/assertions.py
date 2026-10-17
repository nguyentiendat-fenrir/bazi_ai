"""Assertions (docs/10 · Tri thức và mệnh lệ): read side; candidates arrive as drafts."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..knowledge import assertions
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['knowledge'])
State = Literal['draft', 'in_review', 'approved', 'rejected', 'revoked']
Speaker = Literal['original_author', 'commentator', 'translator', 'editor', 'unknown']
Origin = Literal['source_explicit', 'editor_interpretation', 'ai_inferred']


class AssertionDTO(BaseModel):
    id: uuid.UUID
    assertion_key: str
    revision: int
    school_id: uuid.UUID
    school_key: str
    method_id: uuid.UUID | None
    concept_id: uuid.UUID | None
    statement: str
    applicability: dict
    exception_text: str | None
    origin: Origin
    state: State
    author_id: uuid.UUID
    created_at: datetime


class SourceDTO(BaseModel):
    evidence_id: uuid.UUID
    relation: Literal['states', 'supports', 'contrasts']
    book_version_id: uuid.UUID
    page_revision_id: uuid.UUID
    page_id: uuid.UUID
    physical_page_number: int
    block_id: uuid.UUID
    start_offset: int
    end_offset: int
    speaker_layer: Speaker
    origin: Origin
    quote: str


class RelationDTO(BaseModel):
    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    relation: str
    state: State


class AssertionDetail(AssertionDTO):
    sources: list[SourceDTO]
    relations: list[RelationDTO]


@router.get('/assertions', response_model=ListEnvelope[AssertionDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R'))
def list_assertions(state: State | None = None, school_id: uuid.UUID | None = None,
                    book_version_id: uuid.UUID | None = None,
                    q: str | None = Query(default=None, max_length=200),
                    limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
                    principal: Principal = Depends(current_principal),
                    conn: Connection = Depends(db)) -> dict:
    items, next_cursor = assertions.list_assertions(conn, principal, state, school_id,
                                                    book_version_id, q, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.get('/assertions/{assertion_id}', response_model=Envelope[AssertionDetail],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('R'))
def get_assertion(assertion_id: uuid.UUID, principal: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(assertions.get_assertion(conn, principal, assertion_id))
