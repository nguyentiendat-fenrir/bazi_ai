"""Ontology, school scopes and review decisions (docs/10 · Tri thức và mệnh lệ)."""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency
from ..core.errors import AppError
from ..core.logging import request_id_var
from ..knowledge import decisions, ontology, scopes
from .health import envelope
from .schemas import (AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission,
                      problem_responses)

router = APIRouter(tags=['knowledge'])
NOT_FOUND = problem_responses(404)
CONFLICT = problem_responses(404, 409)
State = Literal['draft', 'in_review', 'approved', 'rejected', 'revoked']
AliasKind = Literal['same_concept', 'translation_variant', 'related', 'contrasts_with']


class SchoolDTO(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    parent_id: uuid.UUID | None
    description: str


class SchoolInput(BaseModel):
    key: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None
    description: str = Field(default='', max_length=5000)


class TopicDTO(BaseModel):
    id: uuid.UUID
    key: str
    label: str
    parent_id: uuid.UUID | None


class TopicInput(BaseModel):
    key: str = Field(min_length=2, max_length=40)
    label: str = Field(min_length=1, max_length=200)
    parent_id: uuid.UUID | None = None


class MethodDTO(BaseModel):
    id: uuid.UUID
    school_id: uuid.UUID
    school_key: str
    key: str
    revision: int
    description: str
    state: State
    created_at: datetime


class MethodInput(BaseModel):
    school_id: uuid.UUID
    key: str = Field(min_length=2, max_length=40)
    description: str = Field(min_length=1, max_length=5000)


class MethodRevisionInput(BaseModel):
    base_revision: int = Field(ge=1)
    description: str = Field(min_length=1, max_length=5000)
    reason: str = Field(min_length=3, max_length=500)


class TermDTO(BaseModel):
    id: uuid.UUID
    concept_id: uuid.UUID
    form: str
    form_folded: str
    language: str
    alias_kind: Literal['canonical', 'same_concept', 'translation_variant', 'related',
                        'contrasts_with']
    state: State
    evidence_id: uuid.UUID | None
    created_at: datetime


class ConceptRef(BaseModel):
    canonical_key: str
    label: str
    revision: int
    state: State
    school_id: uuid.UUID
    school_key: str


class TermHit(TermDTO):
    concept: ConceptRef


class ConceptDTO(BaseModel):
    id: uuid.UUID
    school_id: uuid.UUID
    school_key: str
    canonical_key: str
    label: str
    description: str
    revision: int
    state: State
    created_at: datetime


class KnowledgeRevisionRef(BaseModel):
    id: uuid.UUID
    revision: int
    state: State


class ReviewRecord(BaseModel):
    decision: Literal['approve', 'reject', 'revoke']
    reason: str
    base_revision: int
    reviewer_id: uuid.UUID
    created_at: datetime


class ConceptDetail(ConceptDTO):
    terms: list[TermDTO]
    revisions: list[KnowledgeRevisionRef]
    reviews: list[ReviewRecord]


class ConceptInput(BaseModel):
    school_id: uuid.UUID
    canonical_key: str = Field(min_length=1, max_length=200)
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    han: str | None = Field(default=None, max_length=50, description='chữ Hán, a zh alias')


class ConceptRevisionInput(BaseModel):
    base_revision: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    reason: str = Field(min_length=3, max_length=500)


class TermInput(BaseModel):
    concept_id: uuid.UUID
    form: str = Field(min_length=1, max_length=200)
    language: str = Field(default='vi', pattern=r'^[a-z]{2,3}$')
    alias_kind: AliasKind
    evidence_id: uuid.UUID | None = None


class ReviewInput(BaseModel):
    entity_kind: Literal['method', 'concept', 'term', 'school_scope', 'assertion',
                         'assertion_relation', 'rule', 'case_revision']
    entity_id: uuid.UUID
    decision: Literal['submit', 'return', 'approve', 'reject', 'revoke']
    base_revision: int = Field(ge=1, description='the revision reviewed (1 for terms, scopes,'
                                                 ' relations)')
    reason: str = Field(min_length=3, max_length=500)


class ReviewResult(BaseModel):
    entity_kind: str
    entity_id: uuid.UUID
    state: State
    review_id: uuid.UUID | None
    terms_approved: int | None = None
    rebuild: str | None = Field(default=None, description='school scopes: queued or why not')
    job_id: uuid.UUID | None = None
    analyses_stale: int | None = Field(default=None, description='revoke: answers marked stale')


class ScopeDTO(BaseModel):
    id: uuid.UUID
    book_version_id: uuid.UUID
    school_id: uuid.UUID
    school_key: str
    first_page: int | None
    last_page: int | None
    state: State
    reason: str
    created_by: uuid.UUID
    created_at: datetime


class ScopeInput(BaseModel):
    school_id: uuid.UUID
    first_page: int | None = Field(default=None, ge=1)
    last_page: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=3, max_length=500)


def _offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None


def _paged(items: list, limit: int, offset: int) -> dict:
    more = len(items) > limit
    return {**envelope(items[:limit]), 'page': {
        'next_cursor': base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
        if more else None, 'has_more': more}}


# ---- schools, topics, methods ------------------------------------------------------

@router.get('/schools', response_model=ListEnvelope[SchoolDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_schools(principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    return {**envelope(ontology.list_schools(conn)), 'page': {}}


@router.post('/schools', status_code=201, response_model=Envelope[SchoolDTO],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT}, openapi_extra=permission('V'))
def create_school(body: SchoolInput, principal: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.create_school(conn, body.key, body.label, body.parent_id,
                                           body.description))


@router.get('/schools/{school_id}', response_model=Envelope[SchoolDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_school(school_id: uuid.UUID, principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.get_school(conn, school_id))


@router.get('/topics', response_model=ListEnvelope[TopicDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_topics(principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return {**envelope(ontology.list_topics(conn)), 'page': {}}


@router.post('/topics', status_code=201, response_model=Envelope[TopicDTO],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT}, openapi_extra=permission('V'))
def create_topic(body: TopicInput, principal: Principal = Depends(require_role('reviewer')),
                 conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.create_topic(conn, body.key, body.label, body.parent_id))


@router.get('/methods', response_model=ListEnvelope[MethodDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_methods(school_id: uuid.UUID | None = None, state: State | None = None,
                 principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    return {**envelope(ontology.list_methods(conn, school_id, state)), 'page': {}}


@router.post('/methods', status_code=201, response_model=Envelope[MethodDTO],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT}, openapi_extra=permission('V'))
def create_method(body: MethodInput, principal: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.create_method(conn, body.school_id, body.key, body.description))


@router.get('/methods/{method_id}', response_model=Envelope[MethodDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_method(method_id: uuid.UUID, principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.get_method(conn, method_id))


@router.post('/methods/{method_id}/revisions', status_code=201,
             response_model=Envelope[MethodDTO],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(412)},
             openapi_extra=permission('V'))
def revise_method(method_id: uuid.UUID, body: MethodRevisionInput,
                  principal: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.revise_method(conn, method_id, body.base_revision, body.description))


# ---- concepts and terms ------------------------------------------------------------

@router.get('/concepts', response_model=ListEnvelope[ConceptDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_concepts(school_id: uuid.UUID | None = None, state: State | None = None,
                  q: str | None = Query(default=None, max_length=200),
                  limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
                  principal: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    offset = _offset(cursor)
    return _paged(ontology.list_concepts(conn, school_id, state, q, limit + 1, offset),
                  limit, offset)


@router.post('/concepts', status_code=201, response_model=Envelope[ConceptDetail],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT}, openapi_extra=permission('V'))
def create_concept(body: ConceptInput, principal: Principal = Depends(require_role('reviewer')),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.create_concept(conn, body.school_id, body.canonical_key, body.label,
                                            body.description, body.han))


@router.get('/concepts/{concept_id}', response_model=Envelope[ConceptDetail],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_concept(concept_id: uuid.UUID, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.get_concept(conn, concept_id))


@router.post('/concepts/{concept_id}/revisions', status_code=201,
             response_model=Envelope[ConceptDetail],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(412)},
             openapi_extra=permission('V'))
def revise_concept(concept_id: uuid.UUID, body: ConceptRevisionInput,
                   principal: Principal = Depends(require_role('reviewer')),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.revise_concept(conn, concept_id, body.base_revision, body.label,
                                            body.description))


@router.get('/terms', response_model=ListEnvelope[TermHit], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def search_terms(q: str | None = Query(default=None, max_length=200),
                 school_id: uuid.UUID | None = None, concept_id: uuid.UUID | None = None,
                 state: State | None = None, limit: int = Query(default=50, ge=1, le=200),
                 principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    return {**envelope(ontology.search_terms(conn, q, school_id, concept_id, state, limit)),
            'page': {}}


@router.post('/terms', status_code=201, response_model=Envelope[TermDTO],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT}, openapi_extra=permission('V'))
def create_term(body: TermInput, principal: Principal = Depends(require_role('reviewer')),
                conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.create_term(conn, body.concept_id, body.form, body.language,
                                         body.alias_kind, body.evidence_id))


@router.get('/terms/{term_id}', response_model=Envelope[TermDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_term(term_id: uuid.UUID, principal: Principal = Depends(current_principal),
             conn: Connection = Depends(db)) -> dict:
    return envelope(ontology.get_term(conn, term_id))


# ---- school scopes and reviews -----------------------------------------------------

@router.get('/book-versions/{version_id}/school-scopes', response_model=ListEnvelope[ScopeDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def list_scopes(version_id: uuid.UUID, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return {**envelope(scopes.list_scopes(conn, principal, version_id)), 'page': {}}


@router.post('/book-versions/{version_id}/school-scopes', status_code=201,
             response_model=Envelope[ScopeDTO],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT}, openapi_extra=permission('V'))
def create_scope(version_id: uuid.UUID, body: ScopeInput,
                 principal: Principal = Depends(require_role('reviewer')),
                 conn: Connection = Depends(db)) -> dict:
    return envelope(scopes.create_scope(conn, principal, version_id, body.school_id,
                                        body.first_page, body.last_page, body.reason))


@router.post('/reviews', response_model=Envelope[ReviewResult],
             responses={**AUTHENTICATED_ERRORS, **CONFLICT, **problem_responses(412)},
             openapi_extra=permission('V', idempotent=True))
def review(body: ReviewInput, request: Request, response: Response,
           principal: Principal = Depends(require_role('reviewer')),
           conn: Connection = Depends(db)) -> dict:
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /reviews',
                             body.model_dump(mode='json'))
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    result = envelope(decisions.decide(conn, principal, body.entity_kind, body.entity_id,
                                       body.decision, body.base_revision, body.reason,
                                       request_id_var.get()))
    slot.complete(200, result)
    return result
