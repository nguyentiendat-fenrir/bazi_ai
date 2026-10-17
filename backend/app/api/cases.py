"""Case library (docs/10 · Tri thức và mệnh lệ): book cases, user cases, revisions."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..knowledge import cases
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['knowledge'])
State = Literal['draft', 'in_review', 'approved', 'rejected', 'revoked']
Origin = Literal['book_case', 'user_case', 'synthetic_test']


class CaseDTO(BaseModel):
    id: uuid.UUID
    case_key: str
    owner_id: uuid.UUID | None
    origin: Origin
    visibility: Literal['private', 'library']
    revision_id: uuid.UUID
    revision: int
    school_id: uuid.UUID
    school_key: str
    method_id: uuid.UUID | None
    chart_payload: dict = Field(description='book-case/1: pillars, sex_for_luck, luck_pillars')
    narrative: str
    claimed_events: list = Field(description="the source's account, not verified outcomes")
    state: State
    quality: dict
    created_at: datetime


class CaseSource(BaseModel):
    evidence_id: uuid.UUID
    physical_page_number: int
    book_version_id: uuid.UUID
    page_revision_id: uuid.UUID
    quote: str


class CaseRevisionRef(BaseModel):
    id: uuid.UUID
    revision: int
    state: State


class CaseDetail(CaseDTO):
    sources: list[CaseSource]
    revisions: list[CaseRevisionRef]


class CaseInput(BaseModel):
    origin: Origin
    school_id: uuid.UUID
    method_id: uuid.UUID | None = None
    chart_payload: dict
    narrative: str = Field(default='', max_length=20000)
    claimed_events: list = Field(default=[], max_length=200)
    evidence_ids: list[uuid.UUID] = Field(default=[], max_length=50)
    case_key: str | None = Field(default=None, max_length=200)


class CaseRevisionInput(BaseModel):
    base_revision: int = Field(ge=1)
    school_id: uuid.UUID | None = None
    method_id: uuid.UUID | None = None
    chart_payload: dict | None = None
    narrative: str | None = Field(default=None, max_length=20000)
    claimed_events: list | None = Field(default=None, max_length=200)
    evidence_ids: list[uuid.UUID] | None = Field(default=None, max_length=50)
    reason: str = Field(min_length=3, max_length=500)


@router.get('/cases', response_model=ListEnvelope[CaseDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_cases(school_id: uuid.UUID | None = None, state: State | None = None,
               origin: Origin | None = None, book_version_id: uuid.UUID | None = None,
               limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
               principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    items, next_cursor = cases.list_cases(conn, principal, school_id, state, origin,
                                          book_version_id, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.post('/cases', status_code=201, response_model=Envelope[CaseDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V/O'))
def create_case(body: CaseInput, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return envelope(cases.create_case(conn, principal, body.origin, body.school_id,
                                      body.chart_payload, body.narrative, body.claimed_events,
                                      body.evidence_ids, body.method_id, body.case_key))


@router.get('/cases/{case_id}', response_model=Envelope[CaseDetail],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('R'))
def get_case(case_id: uuid.UUID, principal: Principal = Depends(current_principal),
             conn: Connection = Depends(db)) -> dict:
    return envelope(cases.get_case(conn, principal, case_id))


@router.post('/cases/{case_id}/revisions', status_code=201, response_model=Envelope[CaseDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 412)},
             openapi_extra=permission('V/O'))
def revise_case(case_id: uuid.UUID, body: CaseRevisionInput,
                principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    changes = body.model_dump(exclude={'base_revision', 'reason'})
    return envelope(cases.revise_case(conn, principal, case_id, body.base_revision, changes))


@router.delete('/cases/{case_id}', status_code=204, response_class=Response,
               responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
               openapi_extra=permission('V/O'))
def delete_case(case_id: uuid.UUID, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> Response:
    cases.delete_case(conn, principal, case_id)
    return Response(status_code=204)
