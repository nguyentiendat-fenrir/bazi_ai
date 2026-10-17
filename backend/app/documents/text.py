"""Vietnamese-safe text helpers.

``nfc`` is the canonical form stored and shown. ``fold`` is only for secondary
search fields (lower case, no diacritics, đ→d): it must never overwrite
Vietnamese text (docs/05 · normalize).
"""
from __future__ import annotations

import re
import unicodedata

_SPACE = re.compile(r'\s+')
_UNSAFE_NAME = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')


def nfc(text: str) -> str:
    return unicodedata.normalize('NFC', text)


def fold(text: str) -> str:
    decomposed = unicodedata.normalize('NFD', text.replace('Đ', 'D').replace('đ', 'd'))
    stripped = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return _SPACE.sub(' ', unicodedata.normalize('NFC', stripped)).strip().lower()


def display_name(filename: str | None, fallback: str = 'upload') -> str:
    """Base name for people to read; never a path. Control and path characters removed."""
    name = nfc((filename or '').replace('\\', '/').rsplit('/', 1)[-1])
    name = _SPACE.sub(' ', _UNSAFE_NAME.sub('_', name)).strip(' .')
    return (name or fallback)[:255]


def title_from_filename(name: str) -> str:
    stem = name.rsplit('.', 1)[0] if '.' in name else name
    return _SPACE.sub(' ', stem.replace('_', ' ')).strip() or 'Untitled'
