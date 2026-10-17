"""Settings (docs/10): redacted runtime facts plus allowlisted, typed DB settings.

Values are validated per key; secrets never live here (environment references
only). Every PATCH carries If-Match with the key's revision ("0" to create).
"""
from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..core.concurrency import etag, require_if_match
from ..core.errors import AppError
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, SettingDTO, SettingsView, permission, \
    problem_responses

router = APIRouter(prefix='/settings', tags=['settings'])

RIGHTS = Literal['unknown', 'private_reference', 'licensed', 'public_domain', 'restricted']
ALLOWED: dict[str, dict[str, Any]] = {
    'user': {
        'ui.locale': Literal['vi', 'en'],
        'ui.theme': Literal['light', 'dark', 'system'],
        'chat.default_mode': Literal['research', 'chart_analysis', 'comparison'],
    },
    'system': {
        'budget.daily_limit_usd': Annotated[float, Field(ge=0, le=100000)],
        'retention.log_days': Annotated[int, Field(ge=1, le=3650)],
        'library.default_rights_status': RIGHTS,
        'library.external_processing_default': bool,
    },
}


class SettingPatch(BaseModel):
    scope: Literal['system', 'user']
    key: str = Field(max_length=100)
    value: Any


def _row_dto(row) -> dict:
    return {'scope': row['scope'], 'key': row['key'], 'value': row['value'],
            'revision': row['revision'], 'updated_at': row['updated_at']}


@router.get('', response_model=Envelope[SettingsView], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def get_settings(request: Request, conn: Connection = Depends(db)) -> dict:
    config = request.app.state.settings
    # RLS returns system rows plus only the caller's own user rows.
    rows = conn.execute(text('SELECT scope, key, value, revision, updated_at FROM settings'
                             ' ORDER BY scope, key')).mappings()
    runtime = {'app_env': config.app_env, 'storage_backend': config.storage_backend,
               'llm_provider': config.llm_provider, 'llm_configured': config.llm_configured,
               'embedding_configured': bool(config.embedding_model)}
    return envelope({'runtime': runtime, 'settings': [_row_dto(r) for r in rows]})


@router.patch('', response_model=Envelope[SettingDTO],
              responses={**AUTHENTICATED_ERRORS, **problem_responses(412, 428)},
              openapi_extra=permission('R (own user scope) / A (system)', if_match=True))
def patch_setting(body: SettingPatch, request: Request, response: Response,
                  principal: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    if body.scope == 'system' and not principal.has_role('admin'):
        raise AppError(403, 'FORBIDDEN', 'System settings require the admin role')
    value_type = ALLOWED[body.scope].get(body.key)
    if value_type is None:
        raise AppError(422, 'VALIDATION_ERROR', 'Unknown setting key',
                       field_errors=[{'path': 'body.key', 'message': 'not an allowed setting'}])
    try:
        value = TypeAdapter(value_type).validate_python(body.value)
    except ValidationError as exc:
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid setting value',
                       field_errors=[{'path': 'body.value', 'message': e['msg']}
                                     for e in exc.errors(include_input=False)]) from None
    owner = principal.user_id if body.scope == 'user' else None
    params = {'scope': body.scope, 'owner': owner, 'key': body.key, 'value': json.dumps(value)}
    current = conn.execute(text(
        'SELECT revision FROM settings WHERE scope = :scope AND owner_id IS NOT DISTINCT FROM'
        ' :owner AND key = :key FOR UPDATE'), params).scalar()
    require_if_match(request, current or 0)
    if current is None:
        row = conn.execute(text(
            'INSERT INTO settings (scope, owner_id, key, value) VALUES (:scope, :owner, :key,'
            ' CAST(:value AS jsonb)) ON CONFLICT DO NOTHING'
            ' RETURNING scope, key, value, revision, updated_at'), params).mappings().first()
        if row is None:  # a concurrent writer created it first
            raise AppError(412, 'REVISION_MISMATCH', 'The setting was created concurrently')
    else:
        row = conn.execute(text(
            'UPDATE settings SET value = CAST(:value AS jsonb), revision = revision + 1'
            ' WHERE scope = :scope AND owner_id IS NOT DISTINCT FROM :owner AND key = :key'
            ' RETURNING scope, key, value, revision, updated_at'), params).mappings().one()
    response.headers['ETag'] = etag(row['revision'])
    return envelope(_row_dto(row))
