"""Calculation policies, birth profiles and charts (docs/10 · lá số).

Every user owns their profiles and charts (row-level security: another user's id is a
404). Birth input is encrypted at rest; chart facts are immutable once computed.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..calc.timebase import BirthInput
from ..charts import service
from ..core.concurrency import etag
from ..core.errors import AppError
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['charts'])
NOT_FOUND = problem_responses(404)


# ---- ChartFacts chart-facts/1 (docs/08) ---------------------------------------------------

class HiddenStem(BaseModel):
    stem: str
    rank: Literal['main', 'middle', 'residual']
    ten_god: str


class Pillar(BaseModel):
    stem: str
    branch: str
    stem_label: str
    branch_label: str
    cycle_index: int
    # Absent only when the day pillar itself is uncertain (no day master).
    stem_element: str | None = None
    branch_element: str | None = None
    polarity: Literal['yang', 'yin'] | None = None
    ten_god: str | None = Field(default=None, description='null for the day pillar (day master)')
    hidden_stems: list[HiddenStem] = []
    growth_stage: str | None = None
    na_yin: str | None = None
    na_yin_label: str | None = None
    na_yin_element: str | None = None
    void: bool | None = None


class Pillars(BaseModel):
    year: Pillar | None
    month: Pillar | None
    day: Pillar | None
    hour: Pillar | None


class SolarTerm(BaseModel):
    key: str
    instant_utc: str
    source_version: str


class NormalizedTime(BaseModel):
    birth_instant_utc: str
    civil_local: str
    pillar_clock_local: str
    utc_offset_seconds: int
    fold: int
    eot_minutes: float | None
    longitude_correction_minutes: float | None
    previous_jie: SolarTerm
    next_jie: SolarTerm
    clock_basis: Literal['civil', 'apparent_solar']
    time_accuracy: Literal['minute', 'hour', 'unknown']
    interval_utc: list[str] | None


class Relation(BaseModel):
    type: str
    positions: list[str]
    members: list[str]
    completeness: Literal['full', 'partial']
    conditions_evaluated: bool
    element: str | None = None


class StartAge(BaseModel):
    years: int
    months: int
    days: int
    hours: int


class DaYun(BaseModel):
    index: int
    stem: str
    branch: str
    start: str | None
    end: str | None


class LiuNian(BaseModel):
    solar_term_year: int
    stem: str
    branch: str
    start_instant: str
    end_instant: str


class Cycles(BaseModel):
    direction: Literal['forward', 'backward'] | None
    start_method: str
    start_age_components: StartAge | None
    start_instant: str | None
    start_range_utc: list[str] | None
    da_yun: list[DaYun] | None
    liu_nian: list[LiuNian]


class ChartWarning(BaseModel):
    code: str
    positions: list[str]
    detail: str


class VariantReason(BaseModel):
    position: str
    cause: str


class Variant(BaseModel):
    from_utc: str
    to_utc: str
    reasons: list[VariantReason]
    pillars: dict[str, dict[str, str]]


class ChartFacts(BaseModel):
    schema_version: str
    chart_id: str
    computed_at: str
    input_snapshot: BirthInput
    normalized_time: NormalizedTime
    policy_snapshot: dict
    engine_manifest: dict
    pillars: Pillars
    relations: list[Relation]
    cycles: Cycles | None
    auxiliary: dict
    warnings: list[ChartWarning]
    variants: list[Variant]
    facts_hash: str


class ChartSummary(BaseModel):
    id: uuid.UUID
    profile_id: uuid.UUID | None
    profile_label: str | None
    profile_revision: int | None
    policy_id: str
    validation_status: Literal['valid', 'partial']
    pillars: dict[str, str | None] = Field(description='e.g. {"year": "jia-chen", "hour": null}')
    facts_hash: str
    created_at: datetime


class ChartDTO(ChartSummary):
    facts: ChartFacts


class ChartInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    birth_input: BirthInput | None = None
    profile_id: uuid.UUID | None = None
    profile_revision: int | None = Field(default=None, ge=1)
    policy_id: str | None = Field(default=None, description='overrides the input policy')

    @model_validator(mode='after')
    def one_source(self) -> 'ChartInput':
        if (self.birth_input is None) == (self.profile_id is None):
            raise ValueError('give either birth_input or profile_id')
        return self


# ---- profiles ------------------------------------------------------------------------------

class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str = Field(min_length=1, max_length=200)
    birth_input: BirthInput


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    label: str | None = Field(default=None, min_length=1, max_length=200)
    birth_input: BirthInput | None = None

    @model_validator(mode='after')
    def something(self) -> 'ProfilePatch':
        if self.label is None and self.birth_input is None:
            raise ValueError('nothing to change')
        return self


class ProfileSummary(BaseModel):
    id: uuid.UUID
    label: str
    revision: int
    charts_count: int
    created_at: datetime
    updated_at: datetime


class ProfileDTO(ProfileSummary):
    birth_input: BirthInput


class ProfileDeleted(BaseModel):
    profile_id: uuid.UUID
    charts_deleted: int
    charts_kept: int


class PolicyCatalog(BaseModel):
    policies: list[dict]
    calendars: list[str]
    range: dict[str, int]
    time_accuracy: list[str]
    max_uncertainty_minutes: int


def _cipher(request: Request):
    return service.require_cipher(request.app.state.cipher)


def _if_match(request: Request) -> int:
    value = request.headers.get('If-Match')
    if value is None:
        raise AppError(428, 'PRECONDITION_REQUIRED', 'If-Match header with the revision is required')
    try:
        return int(value.strip().strip('"'))
    except ValueError:
        raise AppError(412, 'REVISION_MISMATCH', 'If-Match must be the profile revision') from None


@router.get('/calculation-policies', response_model=Envelope[PolicyCatalog],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R'))
def calculation_policies(_: Principal = Depends(current_principal)) -> dict:
    return envelope(service.policy_catalog())


@router.get('/birth-profiles', response_model=ListEnvelope[ProfileSummary],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R/O'))
def list_profiles(limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
                  _: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    items, next_cursor = service.list_profiles(conn, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.post('/birth-profiles', status_code=201, response_model=Envelope[ProfileDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(503)},
             openapi_extra=permission('R/O'))
def create_profile(body: ProfileInput, request: Request, response: Response,
                   principal: Principal = Depends(current_principal),
                   conn: Connection = Depends(db)) -> dict:
    profile = service.create_profile(conn, principal, _cipher(request), body.label,
                                     body.birth_input)
    response.headers['ETag'] = etag(profile['revision'])
    return envelope(profile)


@router.get('/birth-profiles/{profile_id}', response_model=Envelope[ProfileDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409, 503)},
            openapi_extra=permission('O'))
def get_profile(profile_id: uuid.UUID, request: Request, response: Response,
                principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    profile = service.get_profile(conn, principal, _cipher(request), profile_id)
    response.headers['ETag'] = etag(profile['revision'])
    return envelope(profile)


@router.patch('/birth-profiles/{profile_id}', response_model=Envelope[ProfileDTO],
              responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(412, 428, 503)},
              openapi_extra=permission('O'))
def update_profile(profile_id: uuid.UUID, body: ProfilePatch, request: Request,
                   response: Response, principal: Principal = Depends(current_principal),
                   conn: Connection = Depends(db)) -> dict:
    """A new revision; charts made earlier keep their own input and facts."""
    profile = service.update_profile(conn, principal, _cipher(request), profile_id,
                                     _if_match(request), body.label, body.birth_input)
    response.headers['ETag'] = etag(profile['revision'])
    return envelope(profile)


@router.delete('/birth-profiles/{profile_id}', response_model=Envelope[ProfileDeleted],
               responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
               openapi_extra=permission('O'))
def delete_profile(profile_id: uuid.UUID, delete_linked_charts: bool = False,
                   _: Principal = Depends(current_principal),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(service.delete_profile(conn, profile_id, delete_linked_charts))


@router.post('/charts', status_code=201, response_model=Envelope[ChartDTO],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409, 503)},
             openapi_extra=permission('R'))
def create_chart(body: ChartInput, request: Request,
                 principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    """422 with the code (NONEXISTENT_TIME, AMBIGUOUS_TIME, UNSUPPORTED_RANGE, ...) and field."""
    return envelope(service.create_chart(conn, principal, _cipher(request), body.birth_input,
                                         body.profile_id, body.profile_revision, body.policy_id))


@router.get('/charts', response_model=ListEnvelope[ChartSummary], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R/O'))
def list_charts(q: str | None = Query(default=None, max_length=100),
                limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
                _: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    items, next_cursor = service.list_charts(conn, q, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.get('/charts/{chart_id}', response_model=Envelope[ChartDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409, 503)},
            openapi_extra=permission('O'))
def get_chart(chart_id: uuid.UUID, request: Request,
              principal: Principal = Depends(current_principal),
              conn: Connection = Depends(db)) -> dict:
    return envelope(service.get_chart(conn, principal, _cipher(request), chart_id))


@router.delete('/charts/{chart_id}', status_code=204,
               responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
               openapi_extra=permission('O'))
def delete_chart(chart_id: uuid.UUID, _: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> Response:
    if not service.delete_chart(conn, chart_id):
        raise AppError(404, 'NOT_FOUND', 'Chart not found')
    return Response(status_code=204)
