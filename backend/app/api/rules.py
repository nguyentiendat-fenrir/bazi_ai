"""Knowledge rules (docs/10 · Tri thức và mệnh lệ): DSL drafts, revisions, fixtures."""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..core.errors import AppError
from ..knowledge import rules
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['knowledge'])
State = Literal['draft', 'in_review', 'approved', 'rejected', 'revoked']
Status = Literal['fired', 'not_matched', 'pending', 'blocked_exception', 'dependency_blocked']


class RuleDTO(BaseModel):
    id: uuid.UUID
    rule_key: str
    revision: int
    school_id: uuid.UUID
    school_key: str
    method_id: uuid.UUID
    method_key: str
    assertion_id: uuid.UUID | None
    dsl: dict
    dsl_hash: str
    fact_schema_version: str
    state: State
    author_id: uuid.UUID
    created_at: datetime


class RuleSource(BaseModel):
    evidence_id: uuid.UUID
    physical_page_number: int
    book_version_id: uuid.UUID
    page_revision_id: uuid.UUID
    quote: str


class Fixture(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.-]+$')
    facts: dict
    fired_rules: list[str] | None = Field(default=None, max_length=500)
    expect: Status


class RuleReview(BaseModel):
    decision: Literal['approve', 'reject', 'revoke']
    reason: str
    base_revision: int
    reviewer_id: uuid.UUID
    created_at: datetime


class RuleDetail(RuleDTO):
    sources: list[RuleSource]
    requires: list[uuid.UUID]
    fixtures: list[Fixture]
    reviews: list[RuleReview]


class RuleInput(BaseModel):
    dsl: dict = Field(description='a bazi-rule/1 document (docs/08)')
    assertion_id: uuid.UUID | None = None


class RuleRevisionInput(BaseModel):
    base_revision: int = Field(ge=1)
    dsl: dict
    reason: str = Field(min_length=3, max_length=500)


class ValidateInput(BaseModel):
    fixtures: list[Fixture] = Field(default=[], max_length=100,
                                    description='replaces the stored fixtures of a draft')


class FixtureResult(BaseModel):
    name: str
    expect: Status
    status: Status
    passed: bool


class DslProblem(BaseModel):
    path: str
    message: str


class ValidationResult(BaseModel):
    rule_id: uuid.UUID
    valid: bool
    errors: list[DslProblem]
    results: list[FixtureResult]
    approvable_fixtures: bool
    problem: str | None = Field(description='what still blocks approval, if anything')


def _offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None


@router.get('/rules', response_model=ListEnvelope[RuleDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_rules(state: State | None = None, school_id: uuid.UUID | None = None,
               method_id: uuid.UUID | None = None, limit: int = Query(default=50, ge=1, le=200),
               cursor: str | None = None, principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    offset = _offset(cursor)
    items = rules.list_rules(conn, principal, state, school_id, method_id, limit + 1, offset)
    more = len(items) > limit
    return {**envelope(items[:limit]), 'page': {
        'next_cursor': base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
        if more else None, 'has_more': more}}


@router.post('/rules', status_code=201, response_model=Envelope[RuleDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V'))
def create_rule(body: RuleInput, principal: Principal = Depends(require_role('reviewer')),
                conn: Connection = Depends(db)) -> dict:
    return envelope(rules.create_rule(conn, principal, body.dsl, body.assertion_id))


@router.get('/rules/{rule_id}', response_model=Envelope[RuleDetail],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('R'))
def get_rule(rule_id: uuid.UUID, principal: Principal = Depends(current_principal),
             conn: Connection = Depends(db)) -> dict:
    return envelope(rules.get_rule(conn, principal, rule_id))


@router.post('/rules/{rule_id}/revisions', status_code=201, response_model=Envelope[RuleDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 412)},
             openapi_extra=permission('V'))
def revise_rule(rule_id: uuid.UUID, body: RuleRevisionInput,
                principal: Principal = Depends(require_role('reviewer')),
                conn: Connection = Depends(db)) -> dict:
    return envelope(rules.revise_rule(conn, principal, rule_id, body.base_revision, body.dsl))


@router.post('/rules/{rule_id}/validate', response_model=Envelope[ValidationResult],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 409)},
             openapi_extra=permission('V'))
def validate_rule(rule_id: uuid.UUID, body: ValidateInput,
                  principal: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(rules.validate_rule(conn, principal, rule_id,
                                        [f.model_dump() for f in body.fixtures]))
