"""What the model must return at each step (kept small for an 8B model)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal['du', 'mot_phan', 'thieu', 'mau_thuan']


class Decomposition(BaseModel):
    """① The question split into the ideas it asks about (one object + one thing to know)."""
    sub_questions: list[str] = Field(default=[], max_length=4)


class Quote(BaseModel):
    handle: str = Field(description='P1, P2… of the passage the quote is copied from')
    quote: str = Field(description='copied verbatim from that passage')


class Judgement(BaseModel):
    """② Is this need answered by these passages?"""
    status: Status
    quotes: list[Quote] = Field(default=[], max_length=4)
    missing: str = Field(default='', max_length=400, description='what is still not found')


class Rewrite(BaseModel):
    """④ New search queries for a need that is still missing."""
    queries: list[str] = Field(min_length=1, max_length=2)


class Claim(BaseModel):
    text: str = Field(max_length=600)
    sources: list[str] = Field(default=[], max_length=4, description='P# handles, or F for chart facts')


class BranchAnalysis(BaseModel):
    """B3–B5/B7 for one school, from that school's passages and the chart facts."""
    claims: list[Claim] = Field(default=[], max_length=8)


class PartClaim(Claim):
    part: Literal['chinh', 'goc_nhin_khac'] = 'chinh'


class Synthesis(BaseModel):
    """Final answer as claims; B6 agreement when both schools analysed a chart."""
    claims: list[PartClaim] = Field(default=[], max_length=12)
    agreement: Literal['giong', 'khac', 'mot_ben', 'khong_ap_dung'] = 'khong_ap_dung'
    insufficient: bool = False
