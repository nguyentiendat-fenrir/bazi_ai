"""Ingestion batches and per-file uploads (docs/10).

The client creates a batch, then uploads each file in its own request with its
own Idempotency-Key (concurrency 2 in the UI); one bad file is recorded as a
rejected item and never fails the others.
"""
from __future__ import annotations

import hashlib
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import db, engine, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency
from ..core.errors import AppError
from ..documents.uploads import (RIGHTS, UploadForm, UploadRejected, accept_upload, batch_view,
                                 create_batch, record_rejection)
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, permission, problem_responses

router = APIRouter(tags=['uploads'])
Rights = Literal['unknown', 'private_reference', 'licensed', 'public_domain', 'restricted']
assert set(Rights.__args__) == set(RIGHTS)


class BatchInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    pipeline_profile_id: uuid.UUID | None = None
    auto_publish: bool = False


class BatchItem(BaseModel):
    id: uuid.UUID
    display_name: str
    outcome: Literal['accepted', 'duplicate', 'rejected']
    error_code: str | None
    sha256: str | None
    size_bytes: int | None
    version_id: uuid.UUID | None
    duplicate_of: uuid.UUID | None
    job_id: uuid.UUID | None


class BatchDTO(BaseModel):
    id: uuid.UUID
    name: str
    state: str
    pipeline_profile_id: uuid.UUID | None
    auto_publish: bool
    counters: dict[str, int]
    items: list[BatchItem]


class UploadResult(BaseModel):
    outcome: Literal['accepted', 'duplicate']
    display_name: str
    sha256: str
    size_bytes: int
    book_id: uuid.UUID
    version_id: uuid.UUID | None = None
    job_id: uuid.UUID | None = None
    duplicate_of: uuid.UUID | None = None


@router.post('/ingestion-batches', status_code=201, response_model=Envelope[BatchDTO],
             responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def new_batch(body: BatchInput, principal: Principal = Depends(require_role('reviewer')),
              conn: Connection = Depends(db)) -> dict:
    batch = create_batch(conn, principal, body.name, body.pipeline_profile_id, body.auto_publish)
    return envelope(batch_view(conn, batch['id']))


@router.get('/ingestion-batches/{batch_id}', response_model=Envelope[BatchDTO],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('V'))
def get_batch(batch_id: uuid.UUID, _: Principal = Depends(require_role('reviewer')),
              conn: Connection = Depends(db)) -> dict:
    return envelope(batch_view(conn, batch_id))


def _file_digest(upload: UploadFile) -> str:
    digest = hashlib.sha256()
    while chunk := upload.file.read(1024 * 1024):
        digest.update(chunk)
    upload.file.seek(0)
    return digest.hexdigest()


@router.post('/uploads', status_code=201, response_model=Envelope[UploadResult],
             responses={200: {'model': Envelope[UploadResult], 'description': 'duplicate_of'},
                        **AUTHENTICATED_ERRORS, **problem_responses(404, 409, 413, 415)},
             openapi_extra=permission('V'))
def upload(request: Request, response: Response,
           file: UploadFile = File(...), batch_id: uuid.UUID = Form(...),
           rights_status: Rights = Form(...), edition_label: str = Form('v1', max_length=200),
           external_processing_allowed: bool = Form(False),
           book_id: uuid.UUID | None = Form(None), title: str | None = Form(None, max_length=500),
           language: str = Form('vi', pattern=r'^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$'),
           principal: Principal = Depends(require_role('reviewer')),
           conn: Connection = Depends(db), db_engine=Depends(engine)) -> dict:
    form = UploadForm(batch_id, edition_label, rights_status, external_processing_allowed,
                      book_id, title, language)
    payload = {**form.__dict__, 'sha256': _file_digest(file)}
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /uploads', payload)
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    try:
        result = accept_upload(conn, request.app.state.store, principal, form, file.file,
                               file.filename)
    except UploadRejected as exc:
        record_rejection(db_engine, principal, batch_id, file.filename, exc.code)
        raise AppError(exc.status, exc.code, str(exc)) from None
    body = envelope(result)
    response.status_code = 201 if result['outcome'] == 'accepted' else 200
    slot.complete(response.status_code, body)
    return body
