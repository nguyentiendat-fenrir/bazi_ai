"""What the harness needs from the outside world: a model and a retriever."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

SCHOOLS = ('tu_binh', 'manh_phai')
SCHOOL_LABELS = {'tu_binh': 'Tử Bình', 'manh_phai': 'Manh phái', None: 'chung'}


@dataclass(frozen=True)
class Passage:
    """One parent passage of a book, as the answer may cite it."""
    pid: str                      # stable id (the parent id); the same passage across queries
    text: str
    book: str = ''
    header: str = ''              # book · school · breadcrumb · pages
    school: str | None = None     # 'tu_binh' | 'manh_phai' | None
    pages: str = ''
    score: float | None = None
    meta: dict = field(default_factory=dict, compare=False, hash=False)


class Retriever(Protocol):
    def search(self, query: str, school: str | None, k: int) -> list[Passage]:
        """Best passages for ``query``, restricted to one school when given."""


class Model(Protocol):
    def structured(self, step: str, messages: list[dict], schema: type[T],
                   max_tokens: int) -> T:
        """The model's answer parsed into ``schema``; raises ``ModelError`` on failure.

        ``step`` names the harness step (decompose, judge, rewrite, branch, synthesize)
        so an adapter can choose thinking per step and a fake can script per step."""


class ModelError(Exception):
    def __init__(self, code: str, message: str = ''):
        super().__init__(message or code)
        self.code = code
