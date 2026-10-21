"""Judging of RAG answers: shared-password judge sessions, runs, score sheets.

``/judge/*`` routes accept only the judge cookie (no app account); a judge sees
evaluation runs and writes score sheets, nothing else. ``POST /eval-runs`` is
how ``scripts/rag_eval.py`` publishes a run; it needs a reviewer session.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine

from ..auth.deps import engine, require_role
from ..auth.service import Principal
from ..core.db import transaction
from ..core.errors import AppError
from ..judging import service
from ..judging.service import COOKIE, COOKIE_PATH, Judge
from .health import envelope
from .schemas import COMMON_ERRORS, Envelope, permission, problem_responses

router = APIRouter(tags=['judging'])
JUDGE_ERRORS = problem_responses(401, 404, 422, 500)


def _cookie_path(settings) -> str:
    """The judge routes as the browser addresses them (under the public base path)."""
    return settings.public_base_path.rstrip('/') + COOKIE_PATH


def current_judge(request: Request) -> Judge:
    judge = service.judge_from(request.app.state.settings, request.cookies.get(COOKIE))
    if judge is None:
        raise AppError(401, 'AUTH_REQUIRED', 'Judge sign-in required')
    return judge


class JudgeSignIn(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=80, pattern=r'^[^\x00-\x1f<>]+$')


class JudgeMe(BaseModel):
    name: str
    expires_at: int


@router.post('/judge/session', response_model=Envelope[JudgeMe],
             responses={**COMMON_ERRORS, **problem_responses(401, 429, 503)},
             openapi_extra=permission('public + rate limit'))
def judge_sign_in(body: JudgeSignIn, request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    limiter = request.app.state.login_limiter
    key = f"judge:{request.client.host if request.client else 'unknown'}"
    if wait := limiter.retry_after(key):
        raise AppError(429, 'RATE_LIMITED', 'Too many failed attempts',
                       headers={'Retry-After': str(wait)})
    try:
        token = service.sign_in(settings, body.password, body.name.strip())
    except AppError as exc:
        if exc.status == 401:
            limiter.failure(key)
        raise
    limiter.success(key)
    response.set_cookie(COOKIE, token, httponly=True, samesite='strict',
                        secure=settings.cookie_secure, path=_cookie_path(settings),
                        max_age=settings.judge_session_hours * 3600)
    judge = service.judge_from(settings, token)
    return envelope({'name': judge.name, 'expires_at': judge.expires})


@router.delete('/judge/session', status_code=204, responses=JUDGE_ERRORS,
                openapi_extra=permission('judge'))
def judge_sign_out(request: Request, response: Response) -> Response:
    response.status_code = 204
    response.delete_cookie(COOKIE, path=_cookie_path(request.app.state.settings))
    return response


@router.get('/judge/me', response_model=Envelope[JudgeMe], responses=JUDGE_ERRORS,
            openapi_extra=permission('judge'))
def judge_me(judge: Judge = Depends(current_judge)) -> dict:
    return envelope({'name': judge.name, 'expires_at': judge.expires})


class RunSummary(BaseModel):
    id: str
    label: str
    created_at: datetime
    settings: dict
    versions: dict
    results: int
    scored_by_me: int
    judges: int


@router.get('/judge/runs', response_model=Envelope[list[RunSummary]], responses=JUDGE_ERRORS,
            openapi_extra=permission('judge'))
def judge_runs(judge: Judge = Depends(current_judge), db_engine: Engine = Depends(engine)) -> dict:
    with transaction(db_engine) as conn:
        return envelope(service.list_runs(conn, judge.name))


class ResultSummary(BaseModel):
    id: str
    ordinal: int
    question_key: str
    question: str
    status: str
    latency_ms: int | None
    scored_by_me: bool
    scores: int


@router.get('/judge/runs/{run_id}/results', response_model=Envelope[list[ResultSummary]],
            responses=JUDGE_ERRORS, openapi_extra=permission('judge'))
def judge_results(run_id: uuid.UUID, judge: Judge = Depends(current_judge),
                  db_engine: Engine = Depends(engine)) -> dict:
    with transaction(db_engine) as conn:
        return envelope(service.list_results(conn, run_id, judge.name))


class MyScore(BaseModel):
    scores: dict[str, Any]
    chunk_labels: dict[str, Any]
    notes: str
    updated_at: datetime


class ResultDetail(BaseModel):
    id: str
    run_id: str
    ordinal: int
    question_key: str
    question: str
    status: str
    latency_ms: int | None
    payload: dict = Field(description='the full /ask response captured by the run')
    my_score: MyScore | None


@router.get('/judge/results/{result_id}', response_model=Envelope[ResultDetail],
            responses=JUDGE_ERRORS, openapi_extra=permission('judge'))
def judge_result(result_id: uuid.UUID, judge: Judge = Depends(current_judge),
                 db_engine: Engine = Depends(engine)) -> dict:
    with transaction(db_engine) as conn:
        return envelope(service.get_result(conn, result_id, judge.name))


class ChunkLabel(BaseModel):
    relevance: Literal['relevant', 'partial', 'irrelevant'] | None = None
    suggest_rule: bool = False


class ScoreSheet(BaseModel):
    scores: dict[str, int | bool | None] = Field(default_factory=dict, max_length=20)
    chunk_labels: dict[str, ChunkLabel] = Field(default_factory=dict, max_length=50)
    notes: str = Field(default='', max_length=5000)


class ScoreSaved(BaseModel):
    saved: bool
    rule_suggestions: int


@router.put('/judge/results/{result_id}/score', response_model=Envelope[ScoreSaved],
            responses=JUDGE_ERRORS, openapi_extra=permission('judge'))
def judge_score(result_id: uuid.UUID, body: ScoreSheet, judge: Judge = Depends(current_judge),
                db_engine: Engine = Depends(engine)) -> dict:
    with transaction(db_engine) as conn:
        return envelope(service.save_score(conn, result_id, judge.name, {
            'scores': body.scores, 'notes': body.notes,
            'chunk_labels': {k: v.model_dump() for k, v in body.chunk_labels.items()}}))


@router.get('/judge/runs/{run_id}/scores.csv', responses={**JUDGE_ERRORS, 200: {
    'content': {'text/csv': {}}, 'description': 'all judges\' score sheets of the run'}},
    openapi_extra=permission('judge'))
def judge_scores_csv(run_id: uuid.UUID, judge: Judge = Depends(current_judge),
                     db_engine: Engine = Depends(engine)) -> Response:
    with transaction(db_engine) as conn:
        body = service.scores_csv(conn, run_id)
    return Response('﻿' + body, media_type='text/csv; charset=utf-8', headers={
        'Content-Disposition': f'attachment; filename="scores-{run_id}.csv"'})


class EvalResultIn(BaseModel):
    ordinal: int = Field(ge=1)
    question_key: str = Field(min_length=1, max_length=40)
    question: str = Field(min_length=1, max_length=4000)
    latency_ms: int | None = None
    payload: dict


class EvalRunIn(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    questions_file: str | None = Field(default=None, max_length=300)
    settings: dict = Field(default_factory=dict)
    versions: dict = Field(default_factory=dict)
    results: list[EvalResultIn] = Field(min_length=1, max_length=500)


class EvalRunCreated(BaseModel):
    id: str
    results: int


@router.post('/eval-runs', status_code=201, response_model=Envelope[EvalRunCreated],
             responses={**COMMON_ERRORS, **problem_responses(401, 403)},
             openapi_extra=permission('V'))
def create_eval_run(body: EvalRunIn, principal: Principal = Depends(require_role('reviewer')),
                    db_engine: Engine = Depends(engine)) -> dict:
    with transaction(db_engine, principal.user_id) as conn:
        return envelope(service.create_run(conn, principal.user_id, body.model_dump()))
