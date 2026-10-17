"""Model profiles and usage (docs/10 · Hệ thống, auth và cài đặt; docs/09 · budget)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ..auth.deps import current_principal, db, engine, require_role
from ..auth.service import Principal
from ..core.db import transaction
from ..core.errors import AppError
from ..core.logging import request_id_var
from ..llm import budget, service
from ..retrieval.embedding import SECRET_REFS, EmbeddingError, build_embedder, checked
from ..retrieval.models import (FORBIDDEN_CONFIG_KEYS, RegistryError, load_profile,
                                profile_hash, register_profile)
from ..retrieval.rerank import RerankError, RerankProfile, build as build_reranker
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['models'])
Kind = Literal['llm', 'embedding', 'reranker']
PROVIDERS = {'llm': ('openai_compatible', 'fixture-scripted'),
             'embedding': ('openai_compatible', 'fixture-hashing'),
             'reranker': ('openai_compatible', 'fixture-overlap')}


class ProfileInput(BaseModel):
    kind: Kind
    provider: str = Field(min_length=1, max_length=40)
    model_name: str = Field(min_length=1, max_length=200)
    model_revision: str = Field(min_length=1, max_length=200)
    dimension: int | None = Field(default=None, ge=8, le=4096)
    config: dict = Field(default_factory=dict, description='no secrets; base_url, timeout,'
                         ' locality, json_mode, prices, daily_budget…')
    secret_ref: str | None = Field(default=None, description='name of an allowlisted env var')


class ProfileDTO(BaseModel):
    id: uuid.UUID
    kind: Kind
    provider: str
    model_name: str
    model_revision: str
    dimension: int | None
    config: dict
    secret_ref: str | None
    enabled: bool
    active: bool
    is_fixture: bool
    created_at: datetime


class TestInput(BaseModel):
    max_tokens: int = Field(default=16, ge=1, le=64)
    check_json: bool = False


class TestResult(BaseModel):
    kind: Kind
    latency_ms: int
    model: str
    is_fixture: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    reply: str | None = None
    json_ok: bool | None = None
    dimension: int | None = None


class UsageRow(BaseModel):
    profile_id: uuid.UUID
    currency: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost: float


class BudgetRow(BaseModel):
    profile_id: uuid.UUID
    daily_budget: float
    currency: str
    spent_today: float


class UsageDTO(BaseModel):
    from_: datetime = Field(alias='from')
    to: datetime
    own: list[UsageRow]
    all: list[UsageRow] | None = Field(default=None, description='admins: totals of everyone')
    budgets: list[BudgetRow]

    model_config = {'populate_by_name': True}


class Pong(BaseModel):
    ok: bool


def _dto(row) -> dict:
    return {'id': str(row['id']), 'kind': row['kind'], 'provider': row['provider'],
            'model_name': row['model_name'], 'model_revision': row['model_revision'],
            'dimension': row['dimension'], 'config': row['config'] or {},
            'secret_ref': row['secret_ref'], 'enabled': row['enabled'], 'active': row['active'],
            'is_fixture': row['provider'].startswith('fixture'), 'created_at': row['created_at']}


SELECT = ('SELECT p.*, coalesce(p.id = (SELECT x.id FROM model_profiles x WHERE x.kind = p.kind'
          ' AND x.enabled ORDER BY x.created_at DESC LIMIT 1), false) AS active'
          ' FROM model_profiles p')


@router.get('/model-profiles', response_model=ListEnvelope[ProfileDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R'))
def list_profiles(kind: Kind | None = None, principal: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    rows = conn.execute(text(f'{SELECT} WHERE (CAST(:k AS text) IS NULL OR p.kind = :k)'
                             ' ORDER BY p.kind, p.created_at DESC'), {'k': kind}).mappings()
    return {**envelope([_dto(r) for r in rows]), 'page': {}}


@router.post('/model-profiles', status_code=201, response_model=Envelope[ProfileDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('A'))
def create_profile(body: ProfileInput, principal: Principal = Depends(require_role('admin')),
                   conn: Connection = Depends(db)) -> dict:
    if body.provider not in PROVIDERS[body.kind]:
        raise AppError(422, 'VALIDATION_ERROR', f'provider must be one of {PROVIDERS[body.kind]}')
    if any(FORBIDDEN_CONFIG_KEYS.search(key) for key in body.config):
        raise AppError(422, 'VALIDATION_ERROR', 'secrets belong in an env var named by secret_ref')
    if body.secret_ref and body.secret_ref not in SECRET_REFS:
        raise AppError(422, 'VALIDATION_ERROR', f'secret_ref must be one of {sorted(SECRET_REFS)}')
    if (body.kind == 'embedding') != (body.dimension is not None):
        raise AppError(422, 'VALIDATION_ERROR', 'dimension is for embedding profiles only')
    if body.kind == 'embedding':
        # Same identity as the CLI registry, so a profile is never registered twice.
        if conn.execute(text("SELECT 1 FROM model_profiles WHERE profile_hash = :h"),
                        {'h': profile_hash(body.provider, body.model_name, body.model_revision,
                                           body.dimension, body.config, body.secret_ref)}).first():
            raise AppError(409, 'CONFLICT', 'an identical profile exists')
        try:
            row = register_profile(conn, body.provider, body.model_name, body.model_revision,
                                   body.dimension, body.config, body.secret_ref).id
        except RegistryError as exc:
            raise AppError(422, 'VALIDATION_ERROR', str(exc)) from None
    else:
        digest = profile_hash(body.provider, body.model_name, body.model_revision, 0,
                              {**body.config, 'kind': body.kind}, body.secret_ref)
        row = conn.execute(text(
            'INSERT INTO model_profiles (kind, provider, model_name, model_revision, config,'
            ' secret_ref, profile_hash) VALUES (:k, :p, :m, :r, CAST(:c AS jsonb), :s, :h)'
            ' ON CONFLICT (profile_hash) DO NOTHING RETURNING id'),
            {'k': body.kind, 'p': body.provider, 'm': body.model_name, 'r': body.model_revision,
             'c': json.dumps(body.config), 's': body.secret_ref, 'h': digest}).scalar()
        if row is None:
            raise AppError(409, 'CONFLICT', 'an identical profile exists')
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id, redacted_diff,"
        " outcome) VALUES (:a, 'model_profile.create', 'model_profile', :t, :tr, CAST(:d AS jsonb),"
        " 'success')"),
        {'a': principal.user_id, 't': row, 'tr': request_id_var.get() or '',
         'd': json.dumps({'kind': body.kind, 'provider': body.provider, 'model': body.model_name})})
    return envelope(_dto(conn.execute(text(f'{SELECT} WHERE p.id = :i'), {'i': row}).mappings().one()))


@router.post('/model-profiles/{profile_id}/activate', response_model=Envelope[ProfileDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
             openapi_extra=permission('A'))
def activate(profile_id: uuid.UUID, principal: Principal = Depends(require_role('admin')),
             conn: Connection = Depends(db)) -> dict:
    row = conn.execute(text('SELECT kind FROM model_profiles WHERE id = :i FOR UPDATE'),
                       {'i': profile_id}).scalar()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Model profile not found')
    if row == 'embedding':
        raise AppError(422, 'VALIDATION_ERROR', 'switching the embedding profile needs a full'
                       ' re-embedded corpus release; provision and publish through the pipeline')
    conn.execute(text('UPDATE model_profiles SET enabled = (id = :i) WHERE kind = :k'),
                 {'i': profile_id, 'k': row})
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id, redacted_diff,"
        " outcome) VALUES (:a, 'model_profile.activate', 'model_profile', :t, :tr, '{}', 'success')"),
        {'a': principal.user_id, 't': profile_id, 'tr': request_id_var.get() or ''})
    return envelope(_dto(conn.execute(text(f'{SELECT} WHERE p.id = :i'),
                                      {'i': profile_id}).mappings().one()))


@router.post('/model-profiles/{profile_id}/test', response_model=Envelope[TestResult],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 429, 502, 503)},
             openapi_extra=permission('A'))
def test_profile(profile_id: uuid.UUID, body: TestInput, request: Request,
                 principal: Principal = Depends(require_role('admin')),
                 db_engine: Engine = Depends(engine)) -> dict:
    state = request.app.state
    with transaction(db_engine, principal.user_id) as conn:
        row = conn.execute(text('SELECT * FROM model_profiles WHERE id = :i'),
                           {'i': profile_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Model profile not found')
    fixture = row['provider'].startswith('fixture')
    if row['kind'] == 'llm':
        messages = [{'role': 'system', 'content': 'Bạn là bộ kiểm tra kết nối.'},
                    {'role': 'user', 'content': 'Trả lời đúng một từ: OK'}]
        result, _ = service.generate(db_engine, principal, messages, body.max_tokens, None,
                                     state.settings.app_env, getattr(state, 'llm_transport', None),
                                     profile_id)
        json_ok = None
        if body.check_json:
            check = [{'role': 'user', 'content': 'Trả về JSON {"ok": true} và không gì khác.'}]
            try:
                service.generate(db_engine, principal, check, 32, Pong, state.settings.app_env,
                                 getattr(state, 'llm_transport', None), profile_id)
                json_ok = True
            except AppError as exc:
                if exc.code not in ('SCHEMA_INVALID', 'PROVIDER_REJECTED'):
                    raise
                json_ok = False
        return envelope({'kind': 'llm', 'latency_ms': result.latency_ms, 'model': result.model,
                         'is_fixture': fixture, 'input_tokens': result.input_tokens,
                         'output_tokens': result.output_tokens, 'reply': result.text[:200],
                         'json_ok': json_ok})
    started = datetime.now(timezone.utc)
    try:
        if row['kind'] == 'embedding':
            with transaction(db_engine, principal.user_id) as conn:
                profile = load_profile(conn, profile_id)
            vectors = checked(build_embedder(profile, state.settings.app_env,
                                             getattr(state, 'embedding_transport', None))
                              .embed(['kiểm tra kết nối']), profile)
            extra = {'dimension': len(vectors[0])}
        else:
            reranker = build_reranker(RerankProfile(str(row['id']), row['provider'],
                                                    row['model_name'], row['config'] or {},
                                                    row['secret_ref']),
                                      state.settings.app_env, getattr(state, 'rerank_transport', None))
            reranker.rerank('kiểm tra', ['kiểm tra kết nối', 'không liên quan'])
            extra = {}
    except (EmbeddingError, RerankError) as exc:
        raise AppError(503, 'PROVIDER_UNAVAILABLE', str(exc)[:300]) from None
    latency = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    return envelope({'kind': row['kind'], 'latency_ms': latency, 'model': row['model_name'],
                     'is_fixture': fixture, **extra})


@router.get('/usage', response_model=Envelope[UsageDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('R'))
def usage(from_: date | None = Query(default=None, alias='from'), to: date | None = None,
          profile_id: uuid.UUID | None = None, principal: Principal = Depends(current_principal),
          conn: Connection = Depends(db)) -> dict:
    today = datetime.now(timezone.utc).date()
    since = datetime.combine(from_ or today, time(), timezone.utc)
    until = datetime.combine(to or today, time(), timezone.utc) + timedelta(days=1)
    return envelope(budget.summary(conn, principal.user_id, since, until, profile_id,
                                   aggregate=principal.has_role('admin')))
