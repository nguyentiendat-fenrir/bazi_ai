"""Shared response contracts (docs/10 · Quy ước): envelopes, problems, common DTOs."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
import uuid

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar('T')


class Meta(BaseModel):
    request_id: str | None


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: Meta


class Page(BaseModel):
    next_cursor: str | None = None
    has_more: bool = False


class ListEnvelope(BaseModel, Generic[T]):
    data: list[T]
    page: Page = Field(default_factory=Page)
    meta: Meta


class FieldError(BaseModel):
    path: str
    message: str


class Problem(BaseModel):
    """application/problem+json (RFC 9457) with a stable ``code``."""
    type: str
    title: str
    status: int
    code: str
    detail: str | None
    request_id: str | None
    field_errors: list[FieldError] = []


def problem_responses(*statuses: int) -> dict:
    return {status: {'model': Problem, 'content': {'application/problem+json': {}}}
            for status in statuses}


# Errors any route can return; routes add their specific ones.
COMMON_ERRORS = problem_responses(422, 500)
AUTHENTICATED_ERRORS = problem_responses(401, 403, 422, 500)


FeedbackCategory = Literal['wrong_source', 'missing_source', 'wrong_school', 'calculation',
                           'too_certain', 'unclear', 'other']


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    rating: Literal[-1, 0, 1] = Field(description='1 helpful, -1 not helpful, 0 withdraws')
    categories: list[FeedbackCategory] = Field(default=[], max_length=7)
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackDTO(BaseModel):
    rating: Literal[-1, 0, 1]
    categories: list[FeedbackCategory]
    comment: str | None
    updated_at: datetime


IDEMPOTENCY_PARAMETER = {
    'name': 'Idempotency-Key', 'in': 'header', 'required': True,
    'description': 'one logical mutation; reuse it when retrying (docs/10)',
    'schema': {'type': 'string', 'minLength': 1, 'maxLength': 128, 'pattern': '^[\x21-\x7E]+$'}}
IF_MATCH_PARAMETER = {
    'name': 'If-Match', 'in': 'header', 'required': True,
    'description': 'the ETag (revision) the change is based on; missing 428, stale 412',
    'schema': {'type': 'string', 'minLength': 1, 'maxLength': 200}}


def permission(level: str, *, idempotent: bool = False, if_match: bool = False) -> dict:
    """OpenAPI extension documenting docs/10 permission letters (R/V/A/O/public), plus the
    headers a route reads itself so generated clients type them."""
    extra: dict = {'x-permission': level}
    parameters = ([IDEMPOTENCY_PARAMETER] if idempotent else []) + ([IF_MATCH_PARAMETER] if if_match else [])
    if parameters:
        extra['parameters'] = parameters
    return extra


Role = Literal['admin', 'reviewer', 'reader']


class UserDTO(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    enabled: bool
    locale: str
    created_at: datetime
    updated_at: datetime


class MeDTO(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    capabilities: list[str]


class LoginResult(BaseModel):
    user: MeDTO
    csrf_token: str


class LiveStatus(BaseModel):
    status: Literal['ok']


class CheckDTO(BaseModel):
    name: str
    essential: bool
    status: Literal['ok', 'degraded', 'fail']
    code: str


class ReadyStatus(BaseModel):
    status: Literal['ok', 'degraded', 'fail']
    checks: list[CheckDTO]


class SettingDTO(BaseModel):
    scope: Literal['system', 'user']
    key: str
    value: Any
    revision: int
    updated_at: datetime


class RuntimeConfigDTO(BaseModel):
    """Redacted runtime facts: which providers are configured, never their secrets."""
    app_env: str
    storage_backend: str
    llm_provider: str
    llm_configured: bool
    embedding_configured: bool


class SettingsView(BaseModel):
    runtime: RuntimeConfigDTO
    settings: list[SettingDTO]
