"""Text normalisation with offset maps (docs/05 · normalize, Locator).

``normalize`` returns NFC text with invisible noise removed (zero-width marks,
soft hyphens, BOM) and NBSP-like spaces turned into ordinary spaces, plus a map
from every normalised codepoint back to the raw string, so a citation in the
normalised text can always be traced to the extracted raw text. Meaning-bearing
characters are never changed: Vietnamese diacritics stay (only the separate
search field is folded) and Hán characters are kept as they are.

Offsets in the database are Unicode codepoints; JavaScript strings are UTF-16,
so the UI converts with ``to_utf16``/``from_utf16`` before highlighting.
"""
from __future__ import annotations

import unicodedata

# Removed: invisible formatting that PDFs/DOCX inject between letters.
DROP = {'­', '​', '‌', '‍', '⁠', '﻿'}
# Space-like characters that should behave like a plain space for reading and search.
SPACES = {' ', ' ', ' ', ' ', ' ', ' ', ' ', ' ',
          ' ', ' ', ' ', ' ', '　'}
# Private Use Area: glyphs a font did not map to Unicode (quality signal, kept verbatim).
PUA_RANGES = ((0xE000, 0xF8FF), (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD))


def normalize(raw: str) -> tuple[str, list[int]]:
    """NFC + noise removal; ``index[i]`` is the raw position of normalised char ``i``.

    NFC composition can merge several raw codepoints into one: the map points at the
    first raw codepoint of each composed character.
    """
    cleaned, origin = [], []
    for i, ch in enumerate(raw):
        if ch in DROP:
            continue
        cleaned.append(' ' if ch in SPACES else ch)
        origin.append(i)
    text, index = [], []
    position = 0
    # Normalise cluster by cluster so every output char keeps a raw origin.
    while position < len(cleaned):
        end = position + 1
        while end < len(cleaned) and unicodedata.combining(cleaned[end]):
            end += 1
        cluster = unicodedata.normalize('NFC', ''.join(cleaned[position:end]))
        for k, ch in enumerate(cluster):
            text.append(ch)
            index.append(origin[min(position + k, end - 1)] if len(cluster) == end - position
                         else origin[position])
        position = end
    return ''.join(text), index


def to_utf16(text: str, offset: int) -> int:
    """Codepoint offset → UTF-16 code unit offset (characters beyond the BMP count twice)."""
    return offset + sum(1 for ch in text[:offset] if ord(ch) > 0xFFFF)


def from_utf16(text: str, unit_offset: int) -> int:
    units = 0
    for i, ch in enumerate(text):
        if units >= unit_offset:
            return i
        units += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def unmapped_glyph_rate(text: str) -> float:
    letters = [ch for ch in text if not ch.isspace()]
    if not letters:
        return 0.0
    pua = sum(1 for ch in letters if any(lo <= ord(ch) <= hi for lo, hi in PUA_RANGES))
    return pua / len(letters)
