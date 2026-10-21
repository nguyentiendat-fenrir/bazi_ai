"""Request/response contracts of ``POST /ask`` (and the judge views that replay them)."""
from __future__ import annotations

from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

Status = Literal['ok', 'insufficient_evidence', 'empty_corpus', 'no_match',
                 'provider_not_configured', 'provider_error']


class AskIn(BaseModel):
    model_config = ConfigDict(extra='forbid')

    question: str = Field(min_length=1, max_length=4000)
    school_keys: list[str] = Field(default=[], max_length=5,
                                   description='restrict to these schools (manh_phai, tu_binh)')
    book_ids: list[uuid.UUID] = Field(default=[], max_length=50)
    thinking: bool | None = Field(default=None, description='Qwen thinking; default from settings')
    rerank: bool = True


class ReviewedRule(BaseModel):
    assertion_id: str
    key: str
    revision: int
    text: str


class Scores(BaseModel):
    dense_raw: float | None = Field(None, description='cosine similarity')
    sparse_raw: float | None = Field(None, description='BM25 score')
    dense: float = Field(description='dense score min-max normalised in this query')
    sparse: float = Field(description='BM25 score min-max normalised in this query')
    fused: float = Field(description='w_dense·dense + w_sparse·sparse')
    rerank: float | None = None
    dense_rank: int | None = None
    sparse_rank: int | None = None
    rerank_rank: int | None = None


class SourceSpan(BaseModel):
    page_revision_id: str
    physical_page_number: int
    printed_page_label: str | None = None
    start_offset: int
    end_offset: int


class ChildOut(BaseModel):
    chunk_id: str
    rank: int
    book_title: str
    edition: str | None = None
    school: str | None = None
    breadcrumb: list[str] = []
    section_path: str
    page_start: int | None = None
    page_end: int | None = None
    printed_pages: list[str] | None = None
    speaker_layer: str
    unit_kind: str
    header: str = ''
    text: str
    scores: Scores
    also_in: list[dict] = []
    parent_handle: str | None = Field(None, description='P# of the parent sent to the model')
    expert_reviewed: bool = False
    reviewed_rules: list[ReviewedRule] = []
    meta: dict = Field(default_factory=dict, description='entities, charts, extraction, …')
    spans: list[SourceSpan] = Field(default=[], description='exact source spans (page viewer)')


class ParentOut(BaseModel):
    handle: str
    parent_id: str
    book_title: str
    school: str | None = None
    breadcrumb: list[str] = []
    header: str = ''
    page_start: int | None = None
    page_end: int | None = None
    summary: str | None = None
    text: str
    tokens: int
    child_ids: list[str] = Field(description='retrieved children that selected this parent')
    cited: bool = False
    expert_reviewed: bool = False
    reviewed_rules: list[ReviewedRule] = []


class AskOut(BaseModel):
    status: Status
    question: str
    answer: str | None = Field(None, description='validated answer, invalid [P#] removed')
    raw_answer: str | None = Field(None, description='model output before validation')
    cited: list[str] = []
    invalid_citations: list[str] = []
    model_said_insufficient: bool | None = None
    parents: list[ParentOut] = []
    children: list[ChildOut] = []
    degraded: list[str] = []
    settings: dict = {}
    versions: dict = {}
    timings_ms: dict = {}
    usage: dict = {}
    error: str | None = None
