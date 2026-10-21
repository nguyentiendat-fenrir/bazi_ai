"""Metadata and context for chunks: entities, chart detection, near-duplicate hashes.

Pure functions, used by the chunk stage (stored per child in ``chunk_meta``) and
by retrieval (simhash collapse of the same passage in another edition).

Entities come from a fixed dictionary built from the calculation tables (stems,
branches, elements, ten gods, growth stages) plus core doctrine terms. Matching
is on lower-case text *with* diacritics: folding would merge "ắt" (then) with
the stem "Ất", "tài" with "tại", "thể" with "thế".
"""
from __future__ import annotations

import hashlib
import re

from ..calc.tables import (BRANCH_LABELS, ELEMENT_LABELS, GROWTH_LABELS, STEM_LABELS,
                           TEN_GOD_LABELS)
from ..knowledge.cases import parse_charts

META_VERSION = 'chunk-meta-1'

# Short forms books use for the ten gods ("Thực", "Thương", "T.Tài", "Sát", "Kiêu").
TEN_GOD_ALIASES = {
    'thất sát': 'Thất Sát', 'thiên quan': 'Thất Sát', 'chính quan': 'Chính Quan',
    'chánh quan': 'Chính Quan', 'thiên ấn': 'Thiên Ấn', 'kiêu thần': 'Thiên Ấn',
    'chính ấn': 'Chính Ấn', 'chánh ấn': 'Chính Ấn', 'thiên tài': 'Thiên Tài',
    'chính tài': 'Chính Tài', 'chánh tài': 'Chính Tài', 'thực thần': 'Thực Thần',
    'thương quan': 'Thương Quan', 'tỷ kiên': 'Tỷ Kiên', 'tỉ kiên': 'Tỷ Kiên',
    'kiếp tài': 'Kiếp Tài',
}
CONCEPTS = (
    'dụng thần', 'hỷ thần', 'kỵ thần', 'cừu thần', 'nhàn thần', 'tương thần', 'nguyệt lệnh',
    'cách cục', 'thân vượng', 'thân nhược', 'thông căn', 'thấu can', 'tàng can', 'tòng cách',
    'chân tòng', 'giả tòng', 'tòng sát', 'tòng tài', 'hóa khí', 'đại vận', 'lưu niên', 'ứng kỳ',
    'khách', 'chủ', 'thể', 'dụng', 'mộ', 'khố', 'tố công', 'công thần', 'phế thần', 'tượng pháp',
    'lý pháp', 'tam hợp', 'tam hội', 'lục hợp', 'lục xung', 'tương hình', 'tương hại', 'tương phá',
    'không vong', 'nạp âm', 'trường sinh', 'nhật chủ', 'nhật nguyên', 'thuận dụng', 'nghịch dụng',
    'điều hậu', 'phù ức', 'thông quan', 'bệnh dược', 'cứu ứng', 'thành cách', 'phá cách',
)


def _pattern(words) -> re.Pattern:
    alternatives = sorted({w.lower() for w in words}, key=len, reverse=True)
    return re.compile(r'(?<!\w)(' + '|'.join(re.escape(w) for w in alternatives) + r')(?!\w)')


_STEMS = _pattern(STEM_LABELS.values())
_BRANCHES = _pattern(list(BRANCH_LABELS.values()) + ['tị', 'tí'])
_ELEMENTS = _pattern(list(ELEMENT_LABELS.values()) + ['hoả', 'thuỷ'])
_GODS = _pattern(list(TEN_GOD_LABELS.values()) + list(TEN_GOD_ALIASES))
_GROWTH = _pattern(GROWTH_LABELS.values())
_CONCEPTS = _pattern(CONCEPTS)
_CANON = {**{v.lower(): v for v in TEN_GOD_LABELS.values()}, **TEN_GOD_ALIASES,
          'tị': 'Tỵ', 'tí': 'Tý', 'hoả': 'Hỏa', 'thuỷ': 'Thủy'}


def _found(pattern: re.Pattern, lowered: str, limit: int = 12) -> list[str]:
    seen: dict[str, None] = {}
    for match in pattern.finditer(lowered):
        word = _CANON.get(match.group(1), match.group(1).title())
        seen.setdefault(word, None)
    return list(seen)[:limit]


def entities(text_: str) -> dict:
    lowered = text_.lower()
    found = {'stems': _found(_STEMS, lowered), 'branches': _found(_BRANCHES, lowered),
             'elements': _found(_ELEMENTS, lowered), 'ten_gods': _found(_GODS, lowered),
             'growth_stages': _found(_GROWTH, lowered), 'concepts': _found(_CONCEPTS, lowered)}
    return {k: v for k, v in found.items() if v}


def charts_in(pieces: list[tuple[int, str, str]]) -> list[dict]:
    """Four-pillar charts printed in the given (ordinal, kind, text) blocks."""
    blocks = [{'ordinal': o, 'kind': k, 'text': t} for o, k, t in pieces]
    found = []
    for chart in parse_charts(blocks):
        found.append({'pillars': [f'{s}-{b}' for s, b in chart.pillars],
                      'sex_for_luck': chart.sex_for_luck,
                      'luck_pillars': [f'{s}-{b}' for s, b in chart.luck_pillars]})
    return found


_SHINGLE = re.compile(r'\w+', re.UNICODE)


def simhash(text_: str) -> int:
    """64-bit simhash over word 3-shingles; editions of one passage land within a few bits."""
    words = [w.lower() for w in _SHINGLE.findall(text_)]
    shingles = [' '.join(words[i:i + 3]) for i in range(max(1, len(words) - 2))]
    weights = [0] * 64
    for shingle in shingles:
        value = int.from_bytes(hashlib.blake2b(shingle.encode('utf-8'), digest_size=8).digest(),
                               'big')
        for bit in range(64):
            weights[bit] += 1 if value >> bit & 1 else -1
    result = sum(1 << bit for bit in range(64) if weights[bit] > 0)
    return result - (1 << 64) if result >= 1 << 63 else result   # fits a signed bigint


def hamming(a: int, b: int) -> int:
    return bin((a ^ b) & ((1 << 64) - 1)).count('1')


def header(book_title: str, school: str | None, breadcrumb: list[str],
           pages: tuple[int, int] | None) -> str:
    """Deterministic context line prepended to a child for embedding and display."""
    parts = [book_title]
    if school:
        parts.append(school)
    trail = ' › '.join(t for t in breadcrumb if t)
    if trail:
        parts.append(trail)
    if pages:
        parts.append(f'tr. {pages[0]}' + (f'–{pages[1]}' if pages[1] != pages[0] else ''))
    return ' · '.join(parts)
