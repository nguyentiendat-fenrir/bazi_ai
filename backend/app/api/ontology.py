"""Ontology releases and the knowledge impact graph (docs/10 · Tri thức và mệnh lệ)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db, require_role
from ..auth.service import Principal
from ..core.concurrency import claim_idempotency
from ..core.logging import request_id_var
from ..knowledge import impact, ontology_release
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['knowledge'])


class OntologyReleaseDTO(BaseModel):
    id: uuid.UUID
    version: str
    state: Literal['building', 'published', 'retired']
    manifest_hash: str | None
    created_at: datetime
    concepts: int
    terms: int
    pinned_by_active_corpus: bool


class Changes(BaseModel):
    added: list[str]
    removed: list[str]
    total: int


class OntologyDiff(BaseModel):
    base_release_id: uuid.UUID | None
    base_version: str | None
    manifest_hash: str
    changed: bool
    concepts: Changes
    terms: Changes


class PublishOntologyInput(BaseModel):
    version: str | None = Field(default=None, max_length=64,
                                description='defaults to onto-YYYYMMDD-N')


class PublishOntologyResult(BaseModel):
    release: OntologyReleaseDTO
    diff: OntologyDiff
    corpus_release_id: uuid.UUID | None = Field(
        description='the corpus release that now pins it (none while the corpus is empty)')


class Dependents(BaseModel):
    analyses: int
    runs: int


class ImpactDTO(BaseModel):
    entity_kind: str
    entity_id: uuid.UUID
    counts: dict[str, int]
    ids: dict[str, list[uuid.UUID]] = Field(description='first 100 per kind')
    dependents: Dependents = Field(description='owner-private answers counted, never listed')


@router.get('/ontology-releases', response_model=ListEnvelope[OntologyReleaseDTO],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('R'))
def list_releases(principal: Principal = Depends(current_principal),
                  conn: Connection = Depends(db)) -> dict:
    return {**envelope(ontology_release.list_releases(conn)), 'page': {}}


@router.get('/ontology-releases/preview', response_model=Envelope[OntologyDiff],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def preview(principal: Principal = Depends(require_role('reviewer')),
            conn: Connection = Depends(db)) -> dict:
    return envelope(ontology_release.preview(conn))


@router.get('/ontology-releases/{release_id}', response_model=Envelope[OntologyReleaseDTO],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('R'))
def get_release(release_id: uuid.UUID, principal: Principal = Depends(current_principal),
                conn: Connection = Depends(db)) -> dict:
    return envelope(ontology_release.release_dto(conn, release_id))


@router.post('/ontology-releases', status_code=201, response_model=Envelope[PublishOntologyResult],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(409)},
             openapi_extra=permission('V'))
def publish(body: PublishOntologyInput, request: Request, response: Response,
            principal: Principal = Depends(require_role('reviewer')),
            conn: Connection = Depends(db)) -> dict:
    slot = claim_idempotency(conn, request, principal.user_id, 'POST /ontology-releases',
                             body.model_dump())
    if slot.replay:
        response.status_code = slot.replay.status_code
        return slot.replay.body
    result = envelope(ontology_release.publish(conn, principal.user_id, body.version,
                                               request_id_var.get()))
    slot.complete(201, result)
    return result


@router.get('/knowledge/impact', response_model=Envelope[ImpactDTO],
            responses={**AUTHENTICATED_ERRORS, **problem_responses(404)},
            openapi_extra=permission('V'))
def knowledge_impact(entity_kind: str, entity_id: uuid.UUID,
                     principal: Principal = Depends(require_role('reviewer')),
                     conn: Connection = Depends(db)) -> dict:
    return envelope(impact.impact(conn, entity_kind, entity_id))
