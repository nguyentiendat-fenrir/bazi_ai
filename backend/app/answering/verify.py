"""Checks done by code, not by the model: quotes exist, claims are supported, no risky certainty."""
from __future__ import annotations

import re
import unicodedata

_PUNCT = re.compile(r'[^\w\s]', re.UNICODE)
_SPACE = re.compile(r'\s+')
_ELLIPSIS = re.compile(r'\s*(?:\.\.\.|…)\s*')
MIN_QUOTE_CHARS = 12
STOPWORDS = {'là', 'và', 'của', 'có', 'không', 'thì', 'mà', 'các', 'những', 'một', 'được', 'cho',
             'với', 'về', 'ở', 'tại', 'theo', 'này', 'đó', 'khi', 'nên', 'cũng', 'như', 'trong',
             'sẽ', 'đã', 'đang', 'vì', 'do', 'nếu', 'thế', 'nào', 'gì', 'ra', 'lại', 'rất', 'hơn',
             'sách', 'nói', 'ghi', 'rằng', 'vậy', 'ấy', 'người', 'lá', 'số'}


def norm(text: str) -> str:
    text = unicodedata.normalize('NFC', text).lower().replace('“', ' ').replace('”', ' ')
    return _SPACE.sub(' ', _PUNCT.sub(' ', text)).strip()


def quote_found(quote: str, text: str) -> bool:
    """Every part of the quote (split at an ellipsis) appears verbatim in ``text``."""
    parts = [norm(p) for p in _ELLIPSIS.split(quote) if norm(p)]
    if not parts or sum(len(p) for p in parts) < MIN_QUOTE_CHARS:
        return False
    haystack = norm(text)
    return all(p in haystack for p in parts)


def tokens(text: str) -> set[str]:
    return {w for w in norm(text).split() if w not in STOPWORDS and not w.isdigit()}


def support(claim: str, sources: list[str]) -> float:
    """Share of the claim's content words found in the cited texts."""
    words = tokens(claim)
    if not words:
        return 0.0
    cited = set().union(*(tokens(s) for s in sources)) if sources else set()
    return len(words & cited) / len(words)


# A question asking for certainty about the person's own future death, illness, accident or
# divorce is refused; questions about events a book records ("chết năm Bính Tý, vì sao?") are not.
_RISK = re.compile(r'chết|tử vong|qua đời|mất mạng|bệnh nặng|ung thư|tai nạn|ly hôn|ly dị|tù tội',
                   re.IGNORECASE)
_FUTURE = re.compile(r'\bsẽ\b|sắp|năm nay|năm tới|năm sau|có\s.{0,40}\skhông\b|bao giờ|khi nào|'
                     r'\b20[2-9]\d\b|chắc chắn', re.IGNORECASE)
_INJECTION = re.compile(r'bỏ qua (mọi |các )?(quy tắc|hướng dẫn|chỉ dẫn)|không cần (dẫn )?nguồn|'
                        r'ignore (all |previous )?(rules|instructions)', re.IGNORECASE)
_RISKY_CLAIM = re.compile(r'(sẽ|chắc chắn|nhất định).{0,30}(chết|tử vong|qua đời|bệnh|ung thư|'
                          r'tai nạn|ly hôn)', re.IGNORECASE)


def risky_question(question: str) -> bool:
    return bool(_RISK.search(question) and _FUTURE.search(question))


def injection(question: str) -> bool:
    return bool(_INJECTION.search(question))


def risky_claim(text: str) -> bool:
    return bool(_RISKY_CLAIM.search(text))
