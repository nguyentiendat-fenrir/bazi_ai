"""Search over the active corpus release (docs/10 · Lá số, retrieval, chat; docs/07)."""
from __future__ import annotations

from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..retrieval.citations import resolve
from ..retrieval.search import Spec, search
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, permission, problem_responses

router = APIRouter(tags=['retrieval'])


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    mode: Literal['research', 'chart_analysis', 'comparison'] = 'research'
    top_k: int = Field(default=8, ge=1, le=30)
    school_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    book_ids: list[uuid.UUID] = Field(default=[], max_length=50)
    book_version_ids: list[uuid.UUID] = Field(default=[], max_length=50)
    topic_ids: list[uuid.UUID] = Field(default=[], max_length=20)
    page_from: int | None = Field(default=None, ge=1)
    page_to: int | None = Field(default=None, ge=1)
    rerank: bool = Field(default=True, description='order the top 40 with the active reranker')
    pack: bool = Field(default=False, description='also return the packed evidence bundle')

    @model_validator(mode='after')
    def page_range(self) -> 'SearchInput':
        if (self.page_from is None) != (self.page_to is None) or (
                self.page_from is not None and self.page_from > self.page_to):
            raise ValueError('give page_from <= page_to together, or neither')
        return self


class Expansion(BaseModel):
    concept: str
    school_key: str
    matched: str
    variants: list[str]


class QueryView(BaseModel):
    normalized: str
    folded: str
    expansions: list[Expansion]


class HitSpan(BaseModel):
    page_revision_id: uuid.UUID
    block_id: uuid.UUID
    start_offset: int
    end_offset: int
    chunk_start: int
    chunk_end: int
    physical_page_number: int
    printed_page_label: str | None


class Hit(BaseModel):
    chunk_id: uuid.UUID
    score: float = Field(description='weighted reciprocal-rank fusion score')
    ranks: dict[str, int] = Field(description='rank in each candidate list (lexical, vector)')
    text: str
    content_hash: str
    kind: str
    speaker_layer: str
    book_id: uuid.UUID
    book_title: str
    book_version_id: uuid.UUID
    edition_label: str
    generation_id: uuid.UUID
    section_title: str
    section_path: str
    school_key: str | None
    pages: list[int]
    spans: list[HitSpan]
    ordinal: int
    rerank_score: float | None = None


class BundleSpan(BaseModel):
    page_revision_id: uuid.UUID
    block_id: uuid.UUID
    start_offset: int
    end_offset: int
    physical_page_number: int


class EvidenceGroup(BaseModel):
    evidence_id: str = Field(description='opaque handle a model cites (E1, E2, …)')
    chunk_ids: list[uuid.UUID]
    book_id: uuid.UUID
    book_title: str
    book_version_id: uuid.UUID
    edition_label: str
    school_key: str | None
    speaker_layer: str
    section_title: str
    section_path: str
    pages: list[int]
    printed_pages: list[str]
    spans: list[BundleSpan]
    excerpt: str
    tokens: int
    score: float
    rerank_score: float | None
    kinds: list[str]
    merged: bool


class Bundle(BaseModel):
    bundle_id: uuid.UUID = Field(description='cite its handles via POST /citations/resolve')
    groups: list[EvidenceGroup]
    tokens: int
    omitted: int
    truncated: bool


class SearchResult(BaseModel):
    status: Literal['ok', 'no_match', 'empty_corpus', 'empty_filters']
    release_id: uuid.UUID | None
    visibility_epoch: int | None
    query: QueryView
    hits: list[Hit]
    degraded: list[str]
    counts: dict[str, int] = Field(default_factory=dict)
    took_ms: float | None = None
    bundle: Bundle | None = None


@router.post('/search', response_model=Envelope[SearchResult], responses=AUTHENTICATED_ERRORS,
             openapi_extra=permission('R'))
def run_search(body: SearchInput, request: Request,
               principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    spec = Spec(body.query, body.top_k, body.school_ids, body.book_ids, body.book_version_ids,
                body.topic_ids, (body.page_from, body.page_to) if body.page_from else None,
                body.rerank, body.pack)
    state = request.app.state
    return envelope(search(conn, principal, spec, state.settings.app_env,
                           getattr(state, 'embedding_transport', None),
                           getattr(state, 'rerank_transport', None)))


class ClaimInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    evidence_ids: list[str] = Field(max_length=20, description='handles from the bundle (E1…)')
    quote: str | None = Field(default=None, max_length=1000)


class CitationResolveInput(BaseModel):
    bundle_id: uuid.UUID
    claims: list[ClaimInput] = Field(min_length=1, max_length=100)


class ViewerSpan(BaseModel):
    page_revision_id: uuid.UUID
    physical_page_number: int
    printed_page_label: str | None
    start_offset: int
    end_offset: int
    bbox: list[float] | None


class Citation(BaseModel):
    evidence_id: str
    evidence_span_ids: list[uuid.UUID]
    book_id: uuid.UUID
    book_title: str
    book_version_id: uuid.UUID
    edition_label: str
    section_title: str
    speaker_layer: str
    pages: list[int]
    printed_pages: list[str]
    quote: str
    support: float = Field(description='share of the claim content words in the cited text')
    viewer: list[ViewerSpan]


class CitationProblem(BaseModel):
    evidence_id: str
    code: Literal['UNKNOWN_EVIDENCE', 'SOURCE_WITHDRAWN', 'SPAN_INVALID', 'SOURCE_CHANGED',
                  'QUOTE_MISMATCH', 'UNSUPPORTED_DETAIL']


class ClaimResult(BaseModel):
    index: int
    status: Literal['supported', 'weak', 'insufficient_evidence', 'invalid']
    problems: list[CitationProblem]
    support: float
    citations: list[Citation]


class CitationResolveResult(BaseModel):
    bundle_id: uuid.UUID
    release_id: uuid.UUID
    epoch_changed: bool
    claims: list[ClaimResult]


@router.post('/citations/resolve', response_model=Envelope[CitationResolveResult],
             responses={**AUTHENTICATED_ERRORS, **problem_responses(404, 410)},
             openapi_extra=permission('R'))
def resolve_citations(body: CitationResolveInput, principal: Principal = Depends(current_principal),
                      conn: Connection = Depends(db)) -> dict:
    """Invalid citations must never reach a reader, not even in a streaming draft."""
    return envelope(resolve(conn, principal, body.bundle_id,
                            [c.model_dump() for c in body.claims]))
