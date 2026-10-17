"""Ingestion jobs and reprocessing (docs/10 · Sách, upload, jobs và nguồn)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency
from ..core.errors import AppError
from ..ingestion import events, jobs
from .health import envelope
from .schemas import (AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission,
                      problem_responses)

router = APIRouter(tags=['jobs'])
NOT_FOUND = problem_responses(404)
JobState = Literal['queued', 'running', 'retry_wait', 'waiting_review', 'cancel_requested',
                   'succeeded', 'partial', 'failed', 'cancelled']


class JobError(BaseModel):
    code: str | None
    message: str | None
    retryable: bool


class JobDTO(BaseModel):
    id: uuid.UUID
    state: JobState
    stage: str | None = Field(description='stage started last')
    counters: dict
    attempt: int | None = Field(description='attempt of the unit waiting to retry')
    retry_at: str | None
    error: JobError | None
    generation_id: uuid.UUID
    book_version_id: uuid.UUID
    book_id: uuid.UUID
    book_title: str
    edition_label: str
    batch_id: uuid.UUID | None
    parent_job_id: uuid.UUID | None
    pipeline_profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class StageProgress(BaseModel):
    stage: str
    units: int
    computed: int
    reused: int
    done: bool


class JobDetail(JobDTO):
    stages: list[StageProgress]
    retried_by: list[uuid.UUID]


class JobEvent(BaseModel):
    seq: int
    level: Literal['debug', 'info', 'warning', 'error']
    code: str
    payload: dict
    created_at: datetime


class RetryInput(BaseModel):
    failed_units_only: bool = Field(
        default=True, description='succeeded units are always reused; use /process to rebuild')


class ProcessInput(BaseModel):
    pipeline_profile_id: uuid.UUID | None = Field(
        default=None, description='defaults to the profile of the latest generation')
    scope: Literal['full'] = Field(
        default='full', description='page-level work goes through corrections and review items')


@router.get('/jobs', response_model=ListEnvelope[JobDTO], responses=AUTHENTICATED_ERRORS,
            openapi_extra=permission('V'))
def list_jobs(state: JobState | None = None, batch_id: uuid.UUID | None = None,
              book_version_id: uuid.UUID | None = None,
              limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
              principal: Principal = Depends(require_role('reviewer')),
              conn: Connection = Depends(db)) -> dict:
    items, next_cursor = jobs.list_jobs(conn, state, batch_id, book_version_id, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.get('/jobs/{job_id}', response_model=Envelope[JobDetail],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def get_job(job_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
            conn: Connection = Depends(db)) -> dict:
    return envelope(jobs.job_view(conn, job_id))


@router.get('/jobs/{job_id}/events', response_model=ListEnvelope[JobEvent],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def job_events(job_id: uuid.UUID, after_seq: int = Query(default=0, ge=0),
               limit: int = Query(default=100, ge=1, le=500),
               principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    jobs.job_view(conn, job_id)                       # 404 for an unknown job
    items = events.read(conn, job_id, after_seq, limit + 1)
    page, more = items[:limit], len(items) > limit
    return {**envelope(page), 'page': {'next_cursor': str(page[-1]['seq']) if more else None,
                                       'has_more': more}}


@router.post('/jobs/{job_id}/retry', status_code=202, response_model=Envelope[JobDetail],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('V'))
def retry_job(job_id: uuid.UUID, body: RetryInput, request: Request, response: Response,
              principal: Principal = Depends(require_role('reviewer')),
              conn: Connection = Depends(db)) -> dict:
    if not body.failed_units_only:
        raise AppError(422, 'VALIDATION_ERROR', 'A retry reuses succeeded units; use'
                       ' POST /book-versions/{id}/process to rebuild everything')
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /jobs/{id}/retry',
                             {'job_id': str(job_id)})
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    result = envelope(jobs.retry_job(conn, principal.user_id, job_id))
    slot.complete(202, result)
    return result


@router.post('/jobs/{job_id}/cancel', status_code=202, response_model=Envelope[JobDetail],
             responses={200: {'model': Envelope[JobDetail], 'description': 'already terminal'},
                        **AUTHENTICATED_ERRORS, **NOT_FOUND},
             openapi_extra=permission('V'))
def cancel_job(job_id: uuid.UUID, response: Response,
               principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    job = jobs.cancel_job(conn, job_id)
    response.status_code = 202 if job['state'] == 'cancel_requested' else 200
    return envelope(job)


@router.post('/book-versions/{version_id}/process', status_code=202,
             response_model=Envelope[JobDetail],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('V'))
def process_version(version_id: uuid.UUID, body: ProcessInput, request: Request,
                    response: Response, principal: Principal = Depends(require_role('reviewer')),
                    conn: Connection = Depends(db)) -> dict:
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /book-versions/{id}/process',
                             {'version_id': str(version_id), **body.model_dump(mode='json')})
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    result = envelope(jobs.process_version(conn, principal.user_id, version_id,
                                           body.pipeline_profile_id))
    slot.complete(202, result)
    return result
