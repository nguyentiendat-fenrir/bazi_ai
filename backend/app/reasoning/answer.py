"""Answer contract (docs/09 · Answer contract) and the draft a model may propose.

The model never writes the final answer: it proposes a ``DraftAnswer`` citing only
the run's handles (evidence ``E1``…, fact paths, rule keys); the validator turns it
into an ``Answer`` whose claims carry stored evidence ids and a support status.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ClaimKind = Literal['calculation', 'rule_result', 'source_statement', 'interpretation',
                    'limitation']
Inference = Literal['direct', 'conditional', 'interpretive']
Status = Literal['supported', 'partial', 'insufficient_evidence', 'empty_corpus',
                 'provider_not_configured']


class DraftClaim(BaseModel):
    text: str = Field(min_length=1, max_length=800)
    kind: ClaimKind
    evidence: list[str] = Field(default=[], max_length=6, description='handles like E1')
    fact_paths: list[str] = Field(default=[], max_length=8)
    rule_keys: list[str] = Field(default=[], max_length=8)
    school_key: str | None = None
    inference_level: Inference = 'direct'
    time_scope: str | None = Field(default=None, max_length=80)


class DraftPosition(BaseModel):
    school_key: str | None = None
    claim_indexes: list[int] = Field(max_length=12)


class DraftDisagreement(BaseModel):
    topic: str = Field(min_length=1, max_length=200)
    positions: list[DraftPosition] = Field(min_length=2, max_length=6)


class DraftAnswer(BaseModel):
    summary: str = Field(min_length=1, max_length=1200)
    claims: list[DraftClaim] = Field(max_length=12)
    disagreements: list[DraftDisagreement] = Field(default=[], max_length=5)
    limitations: list[str] = Field(default=[], max_length=6)
    follow_up_questions: list[str] = Field(default=[], max_length=3)


class Citation(BaseModel):
    handle: str
    evidence_span_ids: list[str]
    book_id: str
    book_title: str
    edition_label: str
    section_title: str | None
    speaker_layer: str
    pages: list[int]
    printed_pages: list[str]
    quote: str
    support: float
    viewer: list[dict]


class Claim(BaseModel):
    id: str
    text: str
    kind: ClaimKind
    school_key: str | None = None
    method_key: str | None = None
    time_scope: str | None = None
    fact_paths: list[str] = []
    rule_trace_ids: list[str] = Field(default=[], description='rule revision ids of the trace')
    citations: list[Citation] = []
    support_status: Literal['validated', 'needs_review', 'insufficient']
    inference_level: Inference
    unresolved_exceptions: list[str] = []


class Disagreement(BaseModel):
    topic: str
    positions: list[dict]


class Answer(BaseModel):
    status: Status
    mode: Literal['research', 'chart_analysis', 'comparison']
    summary: str
    claims: list[Claim]
    disagreements: list[Disagreement] = []
    limitations: list[str] = []
    follow_up_questions: list[str] = []
    rejected_claims: int = Field(default=0, description='model claims dropped by validation')
    trace_ref: dict
