"""Page images for review and citations (docs/10 · GET /page-revisions/{id}/render).

A page exists only after the sandboxed worker opened its source, so the API renders a
document that already parsed. PDFium is not thread-safe: one lock serialises every call
in this process, and the pixel cap bounds memory per image. PNG is encoded here with
zlib, so the API needs no imaging library.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import struct
import tempfile
import threading
import zlib

import pypdfium2 as pdfium

from ..storage.base import ObjectStore

MAX_PIXELS = 8_000_000
CACHE_DIR = Path(tempfile.gettempdir()) / 'bazi-render-cache'
CACHE_FILES = 8                      # local copies of recently viewed sources
RENDERER = f'pdfium-{pdfium.PDFIUM_INFO.build}-png1'
_LOCK = threading.Lock()


class RenderUnavailable(Exception):
    """The page has no image (e.g. a DOCX whose canonical render failed)."""


@dataclass(frozen=True)
class Source:
    object_key: str
    sha256: str
    page_index: int                  # 0-based page of the PDF (source or DOCX render)


def _local_copy(store: ObjectStore, source: Source) -> Path:
    """Verified local file of the source, kept for the next pages of the same book."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / source.sha256
    if path.is_file():
        os.utime(path)
        return path
    digest = hashlib.sha256()
    fd, tmp = tempfile.mkstemp(dir=CACHE_DIR)
    with os.fdopen(fd, 'wb') as out:
        for chunk in store.get_stream(source.object_key):
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest() != source.sha256:
        os.unlink(tmp)
        raise RenderUnavailable('stored source does not match its hash')
    os.replace(tmp, path)
    for old in sorted(CACHE_DIR.iterdir(), key=lambda p: p.stat().st_mtime)[:-CACHE_FILES]:
        old.unlink(missing_ok=True)
    return path


def png(width: int, height: int, rgb: bytes) -> bytes:
    """Minimal RGB8 PNG (filter 0 per row)."""
    stride = width * 3
    raw = b''.join(b'\x00' + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))


def page_png(store: ObjectStore, source: Source, scale: float) -> tuple[bytes, float]:
    """PNG of one page in its displayed orientation; returns (image, scale used)."""
    path = _local_copy(store, source)
    with _LOCK:
        doc = pdfium.PdfDocument(str(path))
        try:
            if not 0 <= source.page_index < len(doc):
                raise RenderUnavailable('page is outside the document')
            page = doc[source.page_index]
            try:
                width, height = page.get_size()
                # PDFium rounds each side up, so shrink until the rounded image fits.
                while math.ceil(width * scale) * math.ceil(height * scale) > MAX_PIXELS:
                    scale = min(scale * 0.99, (MAX_PIXELS / (width * height)) ** 0.5)
                bitmap = page.render(scale=scale, rev_byteorder=True, prefer_bgrx=False,
                                     fill_color=(255, 255, 255, 255))
                try:
                    w, h, stride = bitmap.width, bitmap.height, bitmap.stride
                    channels = len(bitmap.mode)
                    buffer = bytes(bitmap.buffer)
                finally:
                    bitmap.close()
            finally:
                page.close()
        finally:
            doc.close()
    if channels == 3 and stride == w * 3:
        rgb = buffer[:h * stride]
    else:
        rows = (buffer[y * stride:y * stride + w * channels] for y in range(h))
        rgb = b''.join(row if channels == 3 else b''.join(
            row[i:i + 3] for i in range(0, len(row), channels)) for row in rows)
    return png(w, h, rgb), scale
