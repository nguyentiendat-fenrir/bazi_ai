"""Search over the active corpus release (docs/10 · Lá số, retrieval, chat; docs/07)."""
from __future__ import annotations

from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.engine import Connection

from ..auth.deps import current_principal, db
from ..auth.service import Principal
from ..retrieval.search import Spec, search
from .health import envelope
from .schemas import AUTHENTICATED_ERRORS, Envelope, permission

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


class SearchResult(BaseModel):
    status: Literal['ok', 'no_match', 'empty_corpus', 'empty_filters']
    release_id: uuid.UUID | None
    visibility_epoch: int | None
    query: QueryView
    hits: list[Hit]
    degraded: list[str]
    counts: dict[str, int] = Field(default_factory=dict)
    took_ms: float | None = None


@router.post('/search', response_model=Envelope[SearchResult], responses=AUTHENTICATED_ERRORS,
             openapi_extra=permission('R'))
def run_search(body: SearchInput, request: Request,
               principal: Principal = Depends(current_principal),
               conn: Connection = Depends(db)) -> dict:
    spec = Spec(body.query, body.top_k, body.school_ids, body.book_ids, body.book_version_ids,
                body.topic_ids, (body.page_from, body.page_to) if body.page_from else None)
    settings = request.app.state.settings
    transport = getattr(request.app.state, 'embedding_transport', None)
    return envelope(search(conn, principal, spec, settings.app_env, transport))
