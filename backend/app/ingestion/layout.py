"""Block roles, headings and speaker markers shared by PDF and DOCX extraction (docs/05, 06).

Everything here is a deterministic, explainable heuristic: each decision is
recorded in block attributes (``role``, ``level``, ``marker``, ``heading_rule``)
so reviewers can see why, and anything uncertain stays ``unknown``.
"""
from __future__ import annotations

from collections import Counter
import re

# Running headers/footers repeat on many pages once digits are masked.
DIGITS = re.compile(r'\d+')
FOLIO = re.compile(r'^(?:trang\s+|page\s+)?(\d{1,4}|[ivxlcdm]{1,7})$', re.IGNORECASE)
TOC_LINE = re.compile(r'(\.{4,}|…{2,}|\s{3,})\s*\d{1,4}\s*$')
HEADING_PATTERNS = [
    (re.compile(r'^(?:CHƯƠNG|Chương|PHẦN|Phần|QUYỂN|Quyển|THIÊN|Thiên)\s+[\dIVXLC]+\b'), 1, 'chapter'),
    (re.compile(r'^[IVXLC]{1,6}\.\s+\S'), 1, 'roman'),
    (re.compile(r'^\d{1,2}\.\d{1,2}\.\d{1,2}\.?\s+\S'), 3, 'decimal3'),
    (re.compile(r'^\d{1,2}\.\d{1,2}\.?\s+\S'), 3, 'decimal2'),
    (re.compile(r'^\d{1,2}\.\s+[A-ZĐÀ-Ỹ]'), 2, 'decimal1'),
]
MAX_HEADING_CHARS = 150
# Chart rows ("Mậu Kỷ Bính Canh", "Thực Thương nhật chủ t.Tài") are styled like headings
# in several books; they are data, never section titles.
CHART_TOKENS = {
    'giáp', 'ất', 'bính', 'đinh', 'mậu', 'kỷ', 'canh', 'tân', 'nhâm', 'quý',
    'tý', 'sửu', 'dần', 'mão', 'thìn', 'tỵ', 'tị', 'ngọ', 'mùi', 'thân', 'dậu', 'tuất', 'hợi',
    'tỷ', 'kiên', 'kiếp', 'thực', 'thương', 'tài', 'quan', 'sát', 'ấn', 'kiêu', 'nhật', 'chủ',
    'chính', 'thiên', 'thất', 't.tài', 'c.tài', 't.quan', 'c.quan', 'mộc', 'hỏa', 'hoả', 'thổ',
    'kim', 'thủy', 'thuỷ', 'năm', 'tháng', 'ngày', 'giờ', 'nam', 'nữ', 'mệnh', 'càn', 'khôn',
    'tạo', 'đại', 'vận', '-', '/', '|'}
# Explicit speaker markers at the start of a block (docs/06 speaker layers).
MARKERS = [
    (re.compile(r'^(nguyên văn|nguyên thư)\b', re.IGNORECASE), 'original_author'),
    (re.compile(r'^(nguyên chú|từ chú|lâm chú|nhậm chú|nhậm thị (?:viết|nói|bình)|'
                r'bình chú(?: của [^:：]{1,40})?|chú thích|chú giải|lời bàn)\b', re.IGNORECASE),
     'commentator'),
    (re.compile(r'^(lời dịch giả|người dịch|dịch giả|ghi chú của người dịch)\b', re.IGNORECASE),
     'translator'),
    (re.compile(r'^(lời biên tập|người biên soạn|biên soạn)\b', re.IGNORECASE), 'editor'),
]


def numbered_heading_line(line: str) -> bool:
    """A line that starts a numbered/labelled heading; blocks are split before it."""
    stripped = line.strip()
    return len(stripped) <= MAX_HEADING_CHARS and any(
        pattern.match(stripped) for pattern, _, _ in HEADING_PATTERNS)


def mask(text: str) -> str:
    return DIGITS.sub('#', ' '.join(text.split())).strip().lower()


def edge_lines(page_lines: list[str]) -> list[str]:
    """First and last two non-empty lines: where running headers/footers live."""
    lines = [line.strip() for line in page_lines if line.strip()]
    return lines[:2] + lines[-2:] if len(lines) > 4 else lines


def repeated_patterns(pages_lines: list[list[str]], min_share: float = 0.3) -> set[str]:
    counts = Counter()
    for lines in pages_lines:
        counts.update({mask(line) for line in edge_lines(lines)})
    threshold = max(3, int(len(pages_lines) * min_share))
    return {pattern for pattern, n in counts.items() if n >= threshold and pattern != '#'}


def is_toc_page(lines: list[str]) -> bool:
    return sum(1 for line in lines if TOC_LINE.search(line)) >= 3


def speaker_marker(text: str) -> tuple[str | None, str | None]:
    start = text.lstrip().lstrip('([“"\'').lstrip()[:60]   # "(Lâm chú: ...)" counts too
    for pattern, layer in MARKERS:
        match = pattern.match(start)
        if match:
            return layer, match.group(1).lower()
    return None, None


LIST_ITEM = re.compile(r'^\s*(?:[-–•+]\s|\(?[a-zđ]\)\s)')
SENTENCE_END = ('.', '!', '?', ':', '"', '”', ')', ';')


def is_chart_row(text: str) -> bool:
    if HEADING_PATTERNS[0][0].match(text.strip()):
        return False    # "Chương 31: Luận Chính Quan" names its topic with chart words
    words = [w.strip('.,:;()') for w in text.lower().split()]
    words = [w for w in words if w]
    return len(words) >= 2 and sum(w in CHART_TOKENS or w.isdigit() for w in words) / len(words) >= 0.6


def heading(text: str, size: float | None, weight: int | None, body_size: float | None,
            lines: int) -> tuple[int, str] | None:
    """(level, rule) when a short block looks like a heading; None otherwise."""
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_HEADING_CHARS or lines > 3 or TOC_LINE.search(stripped):
        return None
    if is_chart_row(stripped):
        return None
    for pattern, level, rule in HEADING_PATTERNS:
        # Numbered notes ("1. Thất chính Tứ dư là ...") run long; titles are short.
        if pattern.match(stripped) and lines <= 2 and len(stripped) <= 100:
            return level, rule
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) >= 4 and all(c.isupper() for c in letters) and len(stripped) <= 80:
        return 1, 'uppercase'
    if body_size and size and size >= body_size * 1.4:
        return 1, 'size'
    if body_size and size and size >= body_size * 1.15:
        return 2, 'size'
    if weight and weight >= 600 and len(stripped) <= 80 and not stripped.endswith(('.', ',', ';')):
        return 2, 'bold'
    return None


# Closing punctuation (Latin and CJK, with closing quotes/brackets after it).
CLOSED = re.compile(r'[.!?…:;。！？」』》〉)\]"”’»]\s*$')
LOWER_START = re.compile(r'^\s*[a-zàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũ'
                          r'ưừứựửữỳýỵỷỹđ]')


def continues(previous: str, current: str) -> bool:
    """``current`` carries on the sentence ``previous`` left open."""
    return not CLOSED.search(previous) and bool(LOWER_START.match(current))
