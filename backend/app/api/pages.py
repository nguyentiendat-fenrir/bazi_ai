"""Pages, revisions, corrections and generation impact (docs/10 · Sách, upload, jobs và nguồn).

A page's ETag is its latest revision id: a correction must name it both in
If-Match and as ``base_revision_id``, so two reviewers can never overwrite each
other's fix. Offsets are Unicode code points in the revision text (docs/05).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency, etag, require_if_match
from ..core.logging import request_id_var
from ..documents import corrections
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['pages'])
NOT_FOUND = problem_responses(404)
Kind = Literal['paragraph', 'heading', 'table', 'figure', 'caption']
Speaker = Literal['original_author', 'commentator', 'translator', 'editor', 'unknown']
State = Literal['accepted', 'review_required', 'excluded']


class PageSummaryDTO(BaseModel):
    page_id: uuid.UUID
    physical_page_number: int
    page_kind: str
    revision_id: uuid.UUID
    revision_no: int
    state: State
    printed_page_label: str | None
    printed_label_verified: bool
    quality: dict


class BlockDTO(BaseModel):
    id: uuid.UUID
    ordinal: int
    kind: Kind
    bbox: list[float]
    start_offset: int
    end_offset: int
    text: str
    table_cells: list[list[str]] | None
    speaker_layer: Speaker
    attributes: dict


class PageLayout(BaseModel):
    width: float | None
    height: float | None
    rotation: int | None
    page_class: str | None


class PageRevisionDTO(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    book_version_id: uuid.UUID
    physical_page_number: int
    page_kind: str
    revision_no: int
    base_revision_id: uuid.UUID | None
    latest_revision_id: uuid.UUID
    is_latest: bool
    state: State
    printed_page_label: str | None
    printed_label_verified: bool
    quality: dict
    layout: PageLayout
    text: str
    created_at: datetime
    blocks: list[BlockDTO]


class BlockChange(BaseModel):
    ordinal: int = Field(ge=0)
    text: str | None = Field(default=None, min_length=1, max_length=20000)
    kind: Kind | None = None
    level: int | None = Field(default=None, ge=1, le=6)
    speaker_layer: Speaker | None = None
    role: Literal['body', 'header', 'footer', 'folio', 'toc'] | None = Field(
        default=None, description='body removes the page-furniture role')
    table_cells: list[list[str]] | None = Field(default=None, max_length=500)

    @model_validator(mode='after')
    def changes_something(self) -> 'BlockChange':
        if all(getattr(self, f) is None for f in ('text', 'kind', 'level', 'speaker_layer',
                                                   'role', 'table_cells')):
            raise ValueError('a change needs at least one of text, kind, level, speaker_layer,'
                             ' role, table_cells')
        return self


class CorrectionInput(BaseModel):
    base_revision_id: uuid.UUID
    changes: list[BlockChange] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=500)


class RevisionRef(BaseModel):
    id: uuid.UUID
    page_id: uuid.UUID
    revision_no: int
    base_revision_id: uuid.UUID


class SourceChanged(BaseModel):
    evidence: list[uuid.UUID]
    rule: list[uuid.UUID]
    assertion: list[uuid.UUID]
    case_revision: list[uuid.UUID]


class CorrectionResult(BaseModel):
    revision: RevisionRef
    changed_blocks: list[int]
    generation_id: uuid.UUID
    job_id: uuid.UUID
    coalesced: bool = Field(description='joined a rebuild that was still queued')
    source_changed: SourceChanged


class JobRef(BaseModel):
    id: uuid.UUID
    state: str
    counters: dict


class ImpactCounts(BaseModel):
    page: int
    chunk_added: int
    chunk_removed: int
    chunk_reused: int
    section_added: int
    section_removed: int
    evidence: int
    rule: int
    assertion: int
    case_revision: int


ImpactKind = Literal['page', 'chunk_added', 'chunk_removed', 'evidence', 'rule', 'assertion',
                     'case_revision']
assert set(ImpactKind.__args__) == set(corrections.IMPACT_KINDS)


class ImpactDTO(BaseModel):
    generation_id: uuid.UUID
    base_generation_id: uuid.UUID | None
    state: str
    job: JobRef | None
    counts: ImpactCounts
    kind: ImpactKind | None
    ids: list[uuid.UUID]
    next_cursor: str | None = Field(description='cursor for the next page of ids of kind')


@router.get('/book-versions/{version_id}/pages', response_model=ListEnvelope[PageSummaryDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def list_pages(version_id: uuid.UUID, limit: int = Query(default=50, ge=1, le=500),
               cursor: str | None = None, principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    items, next_cursor = corrections.list_pages(conn, principal, version_id, limit, cursor)
    return {**envelope(items), 'page': {'next_cursor': next_cursor,
                                        'has_more': next_cursor is not None}}


@router.get('/page-revisions/{revision_id}', response_model=Envelope[PageRevisionDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('R'))
def get_revision(revision_id: uuid.UUID, response: Response,
                 principal: Principal = Depends(current_principal),
                 conn: Connection = Depends(db)) -> dict:
    revision = corrections.get_revision(conn, principal, revision_id)
    response.headers['ETag'] = etag(revision['latest_revision_id'])
    return envelope(revision)


@router.post('/pages/{page_id}/corrections', status_code=201,
             response_model=Envelope[CorrectionResult],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND,
                        **problem_responses(409, 412, 428)},
             openapi_extra=permission('V'))
def correct_page(page_id: uuid.UUID, body: CorrectionInput, request: Request, response: Response,
                 principal: Principal = Depends(require_role('reviewer')),
                 conn: Connection = Depends(db)) -> dict:
    payload = {'page_id': str(page_id), **body.model_dump(mode='json')}
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /pages/{id}/corrections',
                             payload)
    if slot.replay:
        response.status_code = slot.replay.status_code
        response.headers['ETag'] = etag(slot.replay.body['data']['revision']['id'])
        return slot.replay.body
    page = corrections.lock_page(conn, principal, page_id)
    require_if_match(request, str(page['latest_revision_id']))
    result = corrections.correct_page(
        conn, principal, page, body.base_revision_id,
        [c.model_dump(exclude_none=True) for c in body.changes], body.reason,
        request_id_var.get())
    body_out = envelope(result)
    slot.complete(201, body_out)
    response.headers['ETag'] = etag(result['revision']['id'])
    return body_out


@router.get('/generations/{generation_id}/impact', response_model=Envelope[ImpactDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def generation_impact(generation_id: uuid.UUID, kind: ImpactKind | None = None,
                      limit: int = Query(default=100, ge=1, le=500), cursor: str | None = None,
                      principal: Principal = Depends(require_role('reviewer')),
                      conn: Connection = Depends(db)) -> dict:
    return envelope(corrections.impact(conn, generation_id, kind, limit, cursor))
