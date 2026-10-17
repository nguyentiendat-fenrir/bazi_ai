"""Review queue (docs/10 · Sách, upload, jobs và nguồn)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency
from ..core.logging import request_id_var
from ..documents import reviews
from .health import envelope
from .schemas import (AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission,
                      problem_responses)

router = APIRouter(tags=['reviews'])


class ReviewItemDTO(BaseModel):
    id: uuid.UUID
    generation_id: uuid.UUID | None
    page_revision_id: uuid.UUID | None
    page_id: uuid.UUID | None
    physical_page_number: int | None
    book_version_id: uuid.UUID | None
    book_title: str | None
    entity_kind: str | None
    entity_id: uuid.UUID | None
    reason_code: str
    severity: Literal['info', 'low', 'medium', 'high', 'critical']
    state: Literal['open', 'in_progress', 'resolved', 'dismissed']
    resolution: dict
    created_at: datetime
    updated_at: datetime


class ReviewResolveInput(BaseModel):
    action: Literal['accept', 'exclude', 'retry', 'dismiss']
    reason: str = Field(min_length=3, max_length=500)
    base_revision_id: uuid.UUID | None = Field(
        default=None, description="the page revision reviewed (required except for dismiss)")

    @model_validator(mode='after')
    def revision_for_page_actions(self) -> 'ReviewResolveInput':
        if self.action != 'dismiss' and self.base_revision_id is None:
            raise ValueError('base_revision_id is required for accept, exclude and retry')
        return self


class ReviewResolveResult(BaseModel):
    item: ReviewItemDTO
    job_id: uuid.UUID | None
    generation_id: uuid.UUID | None
    coalesced: bool


@router.get('/review-items', response_model=ListEnvelope[ReviewItemDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def list_items(state: Literal['open', 'in_progress', 'resolved', 'dismissed'] | None = 'open',
               reason: str | None = Query(default=None, max_length=100),
               book_version_id: uuid.UUID | None = None, generation_id: uuid.UUID | None = None,
               scope: Literal['page', 'knowledge'] | None = Query(
                   default=None, description='page: source pages (OCR, quality); knowledge:'
                                             ' candidates and changed sources of entities'),
               limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
               principal: Principal = Depends(require_role('reviewer')),
               conn: Connection = Depends(db)) -> dict:
    items, next_cursor = reviews.list_items(conn, state, reason, book_version_id, generation_id,
                                            limit, cursor, scope)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.get('/review-items/{item_id}', response_model=Envelope[ReviewItemDTO],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('V'))
def get_item(item_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
             conn: Connection = Depends(db)) -> dict:
    return envelope(reviews.get_item(conn, item_id))


@router.post('/review-items/{item_id}/resolve', response_model=Envelope[ReviewResolveResult],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 409, 412)},
             openapi_extra=permission('V', idempotent=True))
def resolve(item_id: uuid.UUID, body: ReviewResolveInput, request: Request, response: Response,
            principal: Principal = Depends(require_role('reviewer')),
            conn: Connection = Depends(db)) -> dict:
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /review-items/{id}/resolve',
                             {'item_id': str(item_id), **body.model_dump(mode='json')})
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    result = envelope(reviews.resolve(conn, principal, item_id, body.action, body.reason,
                                      body.base_revision_id, request_id_var.get()))
    slot.complete(200, result)
    return result
