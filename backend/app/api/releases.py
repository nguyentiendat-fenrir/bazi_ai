"""Generations, publication and corpus releases (docs/10 · Sách, upload, jobs và nguồn).

Publishing is synchronous: it only writes release membership and swaps the
active pointer (vectors and lexical entries already exist), so the response
carries the new release instead of an operation to poll.
"""
from __future__ import annotations

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency
from ..core.logging import request_id_var
from ..documents import releases
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, Meta, Page, permission, problem_responses

router = APIRouter(tags=['releases'])
NOT_FOUND = problem_responses(404)


class PageCoverage(BaseModel):
    total: int
    accepted: int
    review_required: int
    excluded: int
    missing: int
    excluded_ranges: list[str] = Field(description='physical pages not accepted, e.g. "3-5"')


class JobRef(BaseModel):
    id: uuid.UUID
    state: str
    counters: dict


class GenerationDTO(BaseModel):
    id: uuid.UUID
    book_version_id: uuid.UUID
    pipeline_profile_id: uuid.UUID
    base_generation_id: uuid.UUID | None
    state: str
    manifest_hash: str | None
    created_at: datetime
    coverage: PageCoverage
    open_review_items: dict[str, int]
    job: JobRef | None
    release_ids: list[uuid.UUID]
    in_active_release: bool


class PublishInput(BaseModel):
    allow_partial: bool = False
    ack_excluded_ranges: list[str] = Field(default=[], max_length=2000)
    activate: bool = Field(default=True, description='false builds a ready release only')


class ReleaseDTO(BaseModel):
    id: uuid.UUID
    parent_id: uuid.UUID | None
    state: str
    manifest_hash: str | None
    embedding_collection_id: uuid.UUID
    ontology_release_id: uuid.UUID
    lexical_profile_version: str
    created_at: datetime
    members_count: int
    active: bool


class ReleaseMember(BaseModel):
    book_version_id: uuid.UUID
    generation_id: uuid.UUID


class ReleaseDetail(ReleaseDTO):
    members: list[ReleaseMember]


class PublishResult(BaseModel):
    release: ReleaseDTO
    activated: bool
    coverage: PageCoverage


class ActivePointer(BaseModel):
    release_id: uuid.UUID
    visibility_epoch: int


class ReleasesView(BaseModel):
    active: ActivePointer | None = Field(description='null while the corpus is empty')
    releases: list[ReleaseDTO]


class ReleasesEnvelope(BaseModel):
    data: ReleasesView
    page: Page
    meta: Meta


class WithdrawInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class WithdrawResult(BaseModel):
    book_version_id: uuid.UUID
    status: str
    active_release_id: uuid.UUID | None = Field(description='the release now active, if any')
    visibility_epoch: int | None


class ActivateInput(BaseModel):
    expected_active_id: uuid.UUID | None = Field(
        description='the release the caller saw active (null for an empty corpus)')


@router.get('/generations/{generation_id}', response_model=Envelope[GenerationDTO],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def get_generation(generation_id: uuid.UUID,
                   principal: Principal = Depends(require_role('reviewer')),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(releases.generation_view(conn, generation_id))


@router.post('/generations/{generation_id}/publish', status_code=201,
             response_model=Envelope[PublishResult],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('V'))
def publish(generation_id: uuid.UUID, body: PublishInput, request: Request, response: Response,
            principal: Principal = Depends(require_role('reviewer')),
            conn: Connection = Depends(db)) -> dict:
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /generations/{id}/publish',
                             {'generation_id': str(generation_id), **body.model_dump()})
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    result = envelope(releases.publish(conn, principal.user_id, generation_id, body.allow_partial,
                                       body.ack_excluded_ranges, body.activate,
                                       request_id_var.get()))
    slot.complete(201, result)
    return result


@router.get('/corpus-releases', response_model=ReleasesEnvelope,
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def list_releases(limit: int = Query(default=20, ge=1, le=100), cursor: str | None = None,
                  principal: Principal = Depends(require_role('reviewer')),
                  conn: Connection = Depends(db)) -> dict:
    view, next_cursor = releases.list_releases(conn, limit, cursor)
    return {**envelope(view), 'page': {'next_cursor': next_cursor,
                                       'has_more': next_cursor is not None}}


@router.get('/corpus-releases/{release_id}', response_model=Envelope[ReleaseDetail],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def get_release(release_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
                conn: Connection = Depends(db)) -> dict:
    return envelope(releases.get_release(conn, release_id, members=True))


@router.post('/book-versions/{version_id}/withdraw', response_model=Envelope[WithdrawResult],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def withdraw(version_id: uuid.UUID, body: WithdrawInput,
             principal: Principal = Depends(require_role('reviewer')),
             conn: Connection = Depends(db)) -> dict:
    """Synchronous: visibility is revoked when this returns (idempotent)."""
    return envelope(releases.withdraw_version(conn, principal.user_id, version_id, body.reason,
                                              request_id_var.get()))


@router.post('/corpus-releases/{release_id}/activate', response_model=Envelope[ReleaseDTO],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('A'))
def activate(release_id: uuid.UUID, body: ActivateInput,
             principal: Principal = Depends(require_role('admin')),
             conn: Connection = Depends(db)) -> dict:
    return envelope(releases.activate_release(conn, principal.user_id, release_id,
                                              body.expected_active_id, request_id_var.get()))
