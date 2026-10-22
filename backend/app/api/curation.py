"""Definition curation review (docs/10 · Tri thức → Biên soạn).

Definitions are drafted and checked by an outside model (``knowledge/curation.py``, run by
``cli curate``); here a reviewer reads them beside their evidence, approves one or many (the
ordinary concept review, with its gate), asks for a rewrite with a note, or edits through
``POST /concepts/{id}/revisions`` (an edit keeps the sources).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.deps import db, require_role
from ..auth.service import Principal
from ..core.errors import AppError
from ..core.logging import request_id_var
from ..documents.text import fold
from ..knowledge import decisions
from .health import envelope
from .knowledge import _offset, _paged
from .schemas import AUTHENTICATED_ERRORS, Envelope, ListEnvelope, permission, problem_responses

router = APIRouter(tags=['knowledge'])
NOT_FOUND = problem_responses(404)
Verdict = Literal['pass', 'fix', 'fail', 'pending']
Status = Literal['ready', 'needs_context', 'needs_split', 'rewrite_requested']


class CuratedRow(BaseModel):
    concept_id: uuid.UUID
    label: str
    school_key: str
    revision: int
    state: str
    status: Status
    llm_verdict: Literal['pass', 'fix', 'fail'] | None
    problems: int
    sources: int
    independent_sources: int
    updated_at: datetime


class EvidenceItem(BaseModel):
    id: uuid.UUID
    quote: str
    book_title: str
    page: int
    speaker_layer: str
    page_revision_id: uuid.UUID
    start_offset: int
    end_offset: int


class CuratedClaim(BaseModel):
    text: str
    evidence_ids: list[uuid.UUID]


class LlmProblem(BaseModel):
    kind: str
    detail: str


class CuratedDefinition(BaseModel):
    concept_id: uuid.UUID
    canonical_key: str
    label: str
    school_key: str
    revision: int
    latest_revision: int
    state: str
    definition: str
    essential_notes: str
    claims: list[CuratedClaim]
    issues: list[str]
    status: Status
    llm_verdict: Literal['pass', 'fix', 'fail'] | None
    llm_problems: list[LlmProblem]
    independent_sources: int
    rewrite_note: str
    compose_model: str | None
    review_model: str | None
    evidence: list[EvidenceItem]


class ApproveItem(BaseModel):
    concept_id: uuid.UUID
    base_revision: int = Field(ge=1)


class ApproveInput(BaseModel):
    items: list[ApproveItem] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=1000)


class ApproveResult(BaseModel):
    concept_id: uuid.UUID
    approved: bool
    error: str | None = None


class RewriteInput(BaseModel):
    note: str = Field(default='', max_length=2000)


LATEST = ('c.revision = (SELECT max(revision) FROM concepts x WHERE x.school_id = c.school_id'
          ' AND x.canonical_key = c.canonical_key)')


@router.get('/curation/definitions', response_model=ListEnvelope[CuratedRow],
            responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def list_definitions(verdict: Verdict | None = None, status: Status | None = None,
                     state: str | None = Query(default=None, max_length=20),
                     school_id: uuid.UUID | None = None,
                     q: str | None = Query(default=None, max_length=200),
                     limit: int = Query(default=50, ge=1, le=200), cursor: str | None = None,
                     principal: Principal = Depends(require_role('reviewer')),
                     conn: Connection = Depends(db)) -> dict:
    offset = _offset(cursor)
    clauses, params = [LATEST], {'limit': limit + 1, 'offset': offset}
    if verdict == 'pending':
        clauses.append('k.llm_verdict IS NULL')
    elif verdict:
        clauses.append('k.llm_verdict = :verdict')
        params['verdict'] = verdict
    for name, value in (('status', status), ('state', state)):
        if value:
            clauses.append(f"{'k' if name == 'status' else 'c'}.{name} = :{name}")
            params[name] = value
    if school_id:
        clauses.append('c.school_id = :school')
        params['school'] = school_id
    if q:
        clauses.append('position(:q in k.name_key) > 0 OR position(:qf in c.canonical_key) > 0'
                       ' OR EXISTS (SELECT 1 FROM terms t WHERE t.concept_id = c.id'
                       ' AND position(:qf in t.form_folded) > 0)')
        params.update(q=q.strip().lower(), qf=fold(q))
    rows = conn.execute(text(
        'SELECT c.id AS concept_id, c.label, s.key AS school_key, c.revision, c.state, k.status,'
        ' k.llm_verdict, jsonb_array_length(k.llm_problems) AS problems, k.independent_sources,'
        ' k.updated_at, (SELECT count(*) FROM concept_sources cs WHERE cs.concept_id = c.id) AS sources'
        ' FROM concept_curation k JOIN concepts c ON c.id = k.concept_id'
        ' JOIN schools s ON s.id = c.school_id WHERE ' + ' AND '.join(f'({c})' for c in clauses) +
        " ORDER BY CASE c.state WHEN 'approved' THEN 2 WHEN 'rejected' THEN 3 ELSE 1 END,"
        " CASE k.llm_verdict WHEN 'pass' THEN 1 WHEN 'fix' THEN 2 WHEN 'fail' THEN 3 ELSE 4 END,"
        ' k.independent_sources DESC, c.label LIMIT :limit OFFSET :offset'), params).mappings().all()
    return _paged([dict(r) for r in rows], limit, offset)


def _definition(conn: Connection, concept_id) -> dict:
    row = conn.execute(text(
        'SELECT c.id AS concept_id, c.canonical_key, c.label, s.key AS school_key, c.revision, c.state,'
        ' c.description AS definition, k.essential_notes, k.claims, k.issues, k.status, k.llm_verdict,'
        ' k.llm_problems, k.independent_sources, k.rewrite_note, k.compose_model, k.review_model,'
        ' (SELECT max(revision) FROM concepts x WHERE x.school_id = c.school_id'
        '  AND x.canonical_key = c.canonical_key) AS latest_revision'
        ' FROM concept_curation k JOIN concepts c ON c.id = k.concept_id'
        ' JOIN schools s ON s.id = c.school_id WHERE k.concept_id = :c'), {'c': concept_id}
    ).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'No curated definition for this concept')
    evidence = conn.execute(text(
        'SELECT e.id, substr(r.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset)'
        ' AS quote, b.title AS book_title, p.physical_page_number AS page, e.speaker_layer,'
        ' e.page_revision_id, e.start_offset, e.end_offset FROM concept_sources cs'
        ' JOIN evidence_spans e ON e.id = cs.evidence_id JOIN page_revisions r ON r.id = e.page_revision_id'
        ' JOIN pages p ON p.id = r.page_id JOIN book_versions v ON v.id = e.book_version_id'
        ' JOIN books b ON b.id = v.book_id WHERE cs.concept_id = :c ORDER BY cs.ordinal'),
        {'c': concept_id}).mappings().all()
    return {**dict(row), 'evidence': [dict(e) for e in evidence]}


@router.get('/curation/definitions/{concept_id}', response_model=Envelope[CuratedDefinition],
            responses={**AUTHENTICATED_ERRORS, **NOT_FOUND}, openapi_extra=permission('V'))
def get_definition(concept_id: uuid.UUID, principal: Principal = Depends(require_role('reviewer')),
                   conn: Connection = Depends(db)) -> dict:
    return envelope(_definition(conn, concept_id))


@router.post('/curation/definitions/approve', response_model=Envelope[list[ApproveResult]],
             responses=AUTHENTICATED_ERRORS, openapi_extra=permission('V'))
def approve_definitions(body: ApproveInput, principal: Principal = Depends(require_role('reviewer')),
                        conn: Connection = Depends(db)) -> dict:
    """Approve several drafts at once; each goes through the concept review and its gate, and
    one that cannot be approved (moved on, sources withdrawn) does not stop the others."""
    results = []
    for item in body.items:
        savepoint = conn.begin_nested()
        try:
            decisions.decide(conn, principal, 'concept', item.concept_id, 'approve',
                             item.base_revision, body.reason, request_id_var.get())
            savepoint.commit()
            results.append({'concept_id': item.concept_id, 'approved': True})
        except AppError as exc:
            savepoint.rollback()
            results.append({'concept_id': item.concept_id, 'approved': False, 'error': exc.message})
    return envelope(results)


@router.post('/curation/definitions/{concept_id}/rewrite', response_model=Envelope[CuratedDefinition],
             responses={**AUTHENTICATED_ERRORS, **NOT_FOUND, **problem_responses(409)},
             openapi_extra=permission('V'))
def request_rewrite(concept_id: uuid.UUID, body: RewriteInput,
                    principal: Principal = Depends(require_role('reviewer')),
                    conn: Connection = Depends(db)) -> dict:
    """The next ``cli curate`` composes this concept again, with the note as an instruction."""
    current = _definition(conn, concept_id)
    if current['revision'] != current['latest_revision'] or current['state'] == 'approved':
        raise AppError(409, 'CONFLICT', 'only the latest unapproved revision can be rewritten')
    conn.execute(text("UPDATE concept_curation SET status = 'rewrite_requested', rewrite_note = :n"
                      ' WHERE concept_id = :c'), {'n': body.note.strip(), 'c': concept_id})
    return envelope(_definition(conn, concept_id))
