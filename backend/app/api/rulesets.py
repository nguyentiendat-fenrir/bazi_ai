"""Rulesets and rule analyses of charts (docs/10 · rulesets, analyses; docs/08 · B)."""
from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..charts import analyses
from ..knowledge import rulesets
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['rulesets'])
NOT_FOUND = problem_responses(404)


class RulesetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    school_id: uuid.UUID
    method_id: uuid.UUID
    version: str = Field(pattern=r'^[a-z0-9][a-z0-9._-]{0,63}$')
    rule_revision_ids: list[uuid.UUID] | None = Field(
        default=None, max_length=5000,
        description='default: the latest approved revision of every rule of the method')


class ActivateInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_current_id: uuid.UUID | None = Field(
        description='the ruleset the caller saw active (null when none)')


class RulesetMember(BaseModel):
    revision_id: uuid.UUID
    rule_key: str
    ordinal: int


class RulesetDTO(BaseModel):
    id: uuid.UUID
    school_id: uuid.UUID
    school_key: str
    method_id: uuid.UUID
    method_key: str
    version: str
    state: Literal['building', 'published', 'retired']
    manifest_hash: str | None
    members_count: int
    created_at: datetime


class RulesetDetail(RulesetDTO):
    members: list[RulesetMember]


class ActivateResult(RulesetDetail):
    analyses_stale: int


class AnalysisInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    school_id: uuid.UUID | None = None
    method_id: uuid.UUID | None = None
    ruleset_id: uuid.UUID | None = Field(default=None, description='default: the active one')
    as_of: str | None = Field(default=None, description='YYYY-MM-DD the question is about')

    @field_validator('as_of')
    @classmethod
    def date_only(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError('YYYY-MM-DD')
        return value


class Claim(BaseModel):
    claim_key: str
    value: str | int | float | bool
    kind: str
    rule_revision_id: uuid.UUID
    rule_key: str
    evidence_ids: list[uuid.UUID]
    explanation: str


class ConflictValue(BaseModel):
    value: str | int | float | bool
    rule_revision_ids: list[uuid.UUID]
    evidence_ids: list[uuid.UUID]


class Conflict(BaseModel):
    claim_key: str
    values: list[ConflictValue]


class AnalysisAnswer(BaseModel):
    kind: Literal['rules']
    status: Literal['complete', 'resource_limit']
    as_of: str | None
    facts_hash: str
    ruleset: dict
    claims: list[Claim]
    conflicts: list[Conflict]
    counters: dict[str, int]
    narrative: str | None


class AnalysisDTO(BaseModel):
    id: uuid.UUID
    chart_id: uuid.UUID
    ruleset_id: uuid.UUID | None
    status: Literal['pending', 'completed', 'failed', 'stale', 'withdrawn']
    stale_reason: str | None
    answer: AnalysisAnswer | None
    created_at: datetime
    updated_at: datetime


class RuleTraceDTO(BaseModel):
    revision_id: uuid.UUID
    rule_key: str
    revision: int
    rule_state: str
    status: Literal['true', 'false', 'unknown', 'conflict', 'skipped']
    detail: dict
    emissions: list[dict]
    conflicts: list[dict]


class ClaimChange(BaseModel):
    claim_key: str
    value: str | int | float | bool


class Reevaluation(BaseModel):
    analysis: AnalysisDTO
    previous_id: uuid.UUID
    diff: dict[str, list[ClaimChange] | int]


@router.get('/rulesets', response_model=Envelope[list[RulesetDTO]], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def list_rulesets(school_id: uuid.UUID | None = None, method_id: uuid.UUID | None = None,
                  state: Literal['building', 'published', 'retired'] | None = None,
                  _: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    return envelope(rulesets.list_rulesets(conn, school_id, method_id, state))


@router.post('/rulesets', status_code=201, response_model=Envelope[RulesetDetail],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V'))
def build_ruleset(body: RulesetInput, _: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    """A frozen snapshot (state building) of approved revisions; activate separately."""
    return envelope(rulesets.build(conn, body.school_id, body.method_id, body.version,
                                   body.rule_revision_ids))


@router.get('/rulesets/{ruleset_id}', response_model=Envelope[RulesetDetail],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_ruleset(ruleset_id: uuid.UUID, _: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return envelope(rulesets.get_ruleset(conn, ruleset_id))


@router.post('/rulesets/{ruleset_id}/activate', response_model=Envelope[ActivateResult],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('V'))
def activate_ruleset(ruleset_id: uuid.UUID, body: ActivateInput,
                     _: Principal = Depends(require_role('reviewer')),
                     conn: Connection = Depends(db)) -> dict:
    """Compare-and-swap; the replaced ruleset retires and its analyses become stale."""
    return envelope(rulesets.activate(conn, ruleset_id, body.expected_current_id))


@router.post('/charts/{chart_id}/analyses', status_code=202, response_model=Envelope[AnalysisDTO],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('O'))
def analyse_chart(chart_id: uuid.UUID, body: AnalysisInput,
                  principal: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    """Rule evaluation is done when this returns; the model narrative arrives with T039."""
    return envelope(analyses.run_analysis(conn, principal, chart_id, body.school_id,
                                          body.method_id, body.ruleset_id, body.as_of))


@router.get('/charts/{chart_id}/analyses', response_model=Envelope[list[AnalysisDTO]],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def chart_analyses(chart_id: uuid.UUID, _: Principal = Depends(current_principal),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(analyses.list_analyses(conn, chart_id))


@router.get('/analyses/{analysis_id}', response_model=Envelope[AnalysisDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def get_analysis(analysis_id: uuid.UUID, _: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    return envelope(analyses.get_analysis(conn, analysis_id))


@router.get('/analyses/{analysis_id}/trace', response_model=ListEnvelope[RuleTraceDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('O'))
def analysis_trace(analysis_id: uuid.UUID, limit: int = Query(default=100, ge=1, le=500),
                   cursor: str | None = None, _: Principal = Depends(current_principal),
                   conn: Connection = Depends(db)) -> dict:
    items, next_cursor = analyses.trace(conn, analysis_id, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.post('/analyses/{analysis_id}/reevaluate', status_code=201,
             response_model=Envelope[Reevaluation],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('O'))
def reevaluate(analysis_id: uuid.UUID,
               principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    """Same chart facts, the active ruleset now; the old analysis stays as history."""
    return envelope(analyses.reevaluate(conn, principal, analysis_id))
