"""In-process BM25 over the children of the active corpus release (the "sparse" side).

Vietnamese has no word segmentation here: a document is its syllables, each
counted twice — accented (lower-case NFC) and folded (no diacritics, đ→d) — so
"khach chu" typed without accents still matches while "Thân" vs "Thần" keep a
stronger exact signal. Section titles are indexed with the child (the child
text excludes headings). Okapi BM25 with k1=1.5, b=0.75 over these tokens.

Built from the database in a worker thread and swapped atomically when the
active release changes; a query never sees a half-built index. Size here is
tens of thousands of children, so a plain dict of postings is enough.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import math
import re

from ..documents.text import fold, nfc

K1 = 1.5
B = 0.75
_WORD = re.compile(r'\w+', re.UNICODE)
# Function words carry no evidence. Matched on the accented form: folding would turn
# "thể" (Thể–Dụng) into "the", "chủ" into "chu", "Tử" into "tu". Text typed without
# diacritics only drops the folded words that cannot be a BaZi term.
STOPWORDS = frozenset({
    'là', 'gì', 'của', 'và', 'có', 'không', 'nào', 'sao', 'như', 'trong', 'theo', 'một', 'các',
    'những', 'được', 'cho', 'với', 'về', 'ở', 'tại', 'thì', 'mà', 'nếu', 'để', 'đó', 'này', 'đây',
    'hay', 'hoặc', 'bao', 'nhiêu', 'ra', 'vì', 'phải', 'đến', 'ai', 'từ', 'cũng', 'rất', 'hơn',
    'sẽ', 'đã', 'đang', 'thế', 'ấy', 'kia', 'trên', 'dưới', 'vậy', 'rồi', 'người', 'khi'})
FOLDED_STOPWORDS = frozenset({
    'la', 'gi', 'cua', 'va', 'khong', 'nao', 'nhu', 'trong', 'theo', 'mot', 'cac', 'nhung', 'duoc',
    'cho', 'voi', 've', 'neu', 'nay', 'day', 'hoac', 'bao', 'nhieu', 'phai', 'cung', 'rat', 'hon',
    'se', 'dang', 'vay', 'roi', 'khi', 'nguoi'})


def tokens(text_: str) -> list[str]:
    words = [w.lower() for w in _WORD.findall(nfc(text_))]
    out = []
    for word in words:
        folded = fold(word)
        if word in STOPWORDS or (word == folded and folded in FOLDED_STOPWORDS) \
                or (len(folded) == 1 and not folded.isdigit()):
            continue
        out.append('a:' + word)
        out.append('f:' + folded)
    return out


@dataclass
class BM25Index:
    release_id: str | None = None
    doc_ids: list[str] = field(default_factory=list)
    lengths: list[int] = field(default_factory=list)
    postings: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    avg_length: float = 0.0

    @classmethod
    def build(cls, release_id, docs: list[tuple[str, str]]) -> 'BM25Index':
        """``docs``: (chunk_id, text) pairs."""
        index = cls(release_id=str(release_id) if release_id else None)
        postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for number, (doc_id, body) in enumerate(docs):
            counts = Counter(tokens(body))
            index.doc_ids.append(str(doc_id))
            index.lengths.append(sum(counts.values()))
            for term, freq in counts.items():
                postings[term].append((number, freq))
        index.postings = dict(postings)
        index.avg_length = (sum(index.lengths) / len(index.lengths)) if index.lengths else 0.0
        return index

    def __len__(self) -> int:
        return len(self.doc_ids)

    def search(self, query: str, limit: int, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        """Top ``limit`` (chunk_id, score); ``allowed`` restricts to chunk ids (filters, ACL)."""
        if not self.doc_ids:
            return []
        total = len(self.doc_ids)
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokens(query)):
            posting = self.postings.get(term)
            if not posting:
                continue
            idf = math.log(1 + (total - len(posting) + 0.5) / (len(posting) + 0.5))
            for number, freq in posting:
                norm = 1 - B + B * self.lengths[number] / (self.avg_length or 1)
                scores[number] += idf * freq * (K1 + 1) / (freq + K1 * norm)
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        out = []
        for number, score in ranked:
            doc_id = self.doc_ids[number]
            if allowed is not None and doc_id not in allowed:
                continue
            out.append((doc_id, score))
            if len(out) >= limit:
                break
        return out
