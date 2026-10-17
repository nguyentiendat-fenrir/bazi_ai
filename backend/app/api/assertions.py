"""Assertions, relations and evidence spans (docs/10 · Tri thức và mệnh lệ).

Everything written here is a draft; approval goes through ``POST /reviews``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..knowledge import assertions, evidence
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


class AssertionInput(BaseModel):
    school_id: uuid.UUID
    statement: str = Field(min_length=3, max_length=5000)
    origin: Origin
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    method_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    applicability: dict = Field(default_factory=dict)
    exception_text: str | None = Field(default=None, max_length=5000)
    assertion_key: str | None = Field(default=None, max_length=200)


class AssertionRevisionInput(BaseModel):
    base_revision: int = Field(ge=1)
    statement: str | None = Field(default=None, min_length=3, max_length=5000)
    origin: Origin | None = None
    evidence_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=50)
    method_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    applicability: dict | None = None
    exception_text: str | None = Field(default=None, max_length=5000)
    reason: str = Field(min_length=3, max_length=500)


class RelationInput(BaseModel):
    from_id: uuid.UUID
    to_id: uuid.UUID
    relation: Literal['supports', 'disputes', 'qualifies', 'exception_to', 'derives_from']


class EvidenceInput(BaseModel):
    page_revision_id: uuid.UUID
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=1)
    origin: Origin = 'source_explicit'


class EvidenceDTO(BaseModel):
    id: uuid.UUID
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


@router.post('/assertions', status_code=201, response_model=Envelope[AssertionDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V'))
def create_assertion(body: AssertionInput,
                     principal: Principal = Depends(require_role('reviewer')),
                     conn: Connection = Depends(db)) -> dict:
    return envelope(assertions.create_assertion(
        conn, principal, body.school_id, body.statement, body.origin, body.evidence_ids,
        body.method_id, body.concept_id, body.applicability, body.exception_text,
        body.assertion_key))


@router.post('/assertions/{assertion_id}/revisions', status_code=201,
             response_model=Envelope[AssertionDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 412)},
             openapi_extra=permission('V'))
def revise_assertion(assertion_id: uuid.UUID, body: AssertionRevisionInput,
                     principal: Principal = Depends(require_role('reviewer')),
                     conn: Connection = Depends(db)) -> dict:
    changes = body.model_dump(exclude={'base_revision', 'reason'})
    return envelope(assertions.revise_assertion(conn, principal, assertion_id,
                                                body.base_revision, changes))


@router.post('/assertion-relations', status_code=201, response_model=Envelope[RelationDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V'))
def create_relation(body: RelationInput, principal: Principal = Depends(require_role('reviewer')),
                    conn: Connection = Depends(db)) -> dict:
    return envelope(assertions.create_relation(conn, body.from_id, body.to_id, body.relation))


@router.post('/evidence', status_code=201, response_model=Envelope[EvidenceDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
             openapi_extra=permission('V'))
def create_evidence(body: EvidenceInput, principal: Principal = Depends(require_role('reviewer')),
                    conn: Connection = Depends(db)) -> dict:
    return envelope(evidence.create_evidence(conn, principal, body.page_revision_id,
                                             body.start_offset, body.end_offset, body.origin))


@router.get('/evidence/{evidence_id}', response_model=Envelope[EvidenceDTO],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('R'))
def get_evidence(evidence_id: uuid.UUID, principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    return envelope(evidence.get_evidence(conn, principal, evidence_id))
