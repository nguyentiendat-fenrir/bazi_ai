"""Evaluation datasets and retrieval runs (docs/10 · Evaluation và operations)."""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..core.errors import AppError
from ..retrieval import evaluate
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['evaluation'])
Split = Literal['dev', 'test', 'holdout']


class RelevantPages(BaseModel):
    book_version_id: uuid.UUID
    pages: list[int] = Field(min_length=1, max_length=200)
    grade: Literal[1, 2] = 1


class ItemExpected(BaseModel):
    relevant: list[RelevantPages] = Field(default=[], max_length=50)
    no_answer: bool = False
    rationale: str | None = Field(default=None, max_length=2000)


class ItemInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    school_ids: list[uuid.UUID] = []
    book_ids: list[uuid.UUID] = []
    book_version_ids: list[uuid.UUID] = []
    topic_ids: list[uuid.UUID] = []


class DatasetItem(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_.-]+$')
    kind: Literal['retrieval', 'no_answer']
    input: ItemInput
    expected: ItemExpected
    split: Split = 'dev'
    source_manifest: dict = Field(default_factory=dict)


class DatasetInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    rights: dict = Field(default_factory=dict)
    items: list[DatasetItem] = Field(min_length=1, max_length=evaluate.MAX_ITEMS)


class DatasetDTO(BaseModel):
    id: uuid.UUID
    name: str
    version: str
    state: Literal['draft', 'approved', 'retired']
    rights: dict
    split_manifest: dict
    items: int
    created_at: datetime


class ItemDTO(BaseModel):
    id: uuid.UUID
    key: str
    kind: str
    input: dict
    expected: dict
    split: Split
    reviewer_id: uuid.UUID | None


class RunInput(BaseModel):
    dataset_id: uuid.UUID
    top_k: int = Field(default=20, ge=1, le=30)
    rerank: bool = True
    split: Split | None = None


class RunResult(BaseModel):
    key: str
    status: Literal['passed', 'failed', 'error', 'skipped']
    scores: dict
    actual: dict
    duration_ms: int


class EvaluationRunDTO(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    config: dict
    status: str
    metrics: dict = Field(description='means of recall@k, hit@k, ndcg@10, mrr@10; latency')
    created_at: datetime
    results: list[RunResult]


@router.get('/evaluation-datasets', response_model=ListEnvelope[DatasetDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def list_datasets(principal: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    return {**envelope(evaluate.list_datasets(conn)), 'page': {}}


@router.post('/evaluation-datasets', status_code=201, response_model=Envelope[DatasetDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V'))
def create_dataset(body: DatasetInput, principal: Principal = Depends(require_role('reviewer')),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(evaluate.create_dataset(conn, body.name, body.version, body.rights,
                                            [i.model_dump(mode='json') for i in body.items]))


@router.get('/evaluation-datasets/{dataset_id}/items', response_model=ListEnvelope[ItemDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def list_items(dataset_id: uuid.UUID, limit: int = Query(default=100, ge=1, le=500),
               cursor: str | None = None,
               principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode()).decode()) if cursor else 0
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None
    items = evaluate.list_items(conn, dataset_id, limit + 1, offset)
    more = len(items) > limit
    return {**envelope(items[:limit]), 'page': {
        'next_cursor': base64.urlsafe_b64encode(str(offset + limit).encode()).decode()
        if more else None, 'has_more': more}}


@router.post('/evaluation-datasets/{dataset_id}/approve', response_model=Envelope[DatasetDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 409)},
             openapi_extra=permission('V'))
def approve_dataset(dataset_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
                    conn: Connection = Depends(db)) -> dict:
    return envelope(evaluate.approve_dataset(conn, principal, dataset_id))


@router.post('/evaluation-runs', status_code=201, response_model=Envelope[EvaluationRunDTO],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
             openapi_extra=permission('V'))
def create_run(body: RunInput, request: Request,
               principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    state = request.app.state
    return envelope(evaluate.run(conn, principal, body.dataset_id, body.top_k, body.rerank,
                                 body.split, state.settings.app_env,
                                 (getattr(state, 'embedding_transport', None),
                                  getattr(state, 'rerank_transport', None))))


@router.get('/evaluation-runs/{run_id}', response_model=Envelope[EvaluationRunDTO],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('V'))
def get_run(run_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
            conn: Connection = Depends(db)) -> dict:
    return envelope(evaluate.get_run(conn, run_id))
