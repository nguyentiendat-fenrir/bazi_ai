"""Synthetic PDFs for extraction tests (no book content).

Text needs a TrueType font that covers Vietnamese; a system font is used when
present, otherwise text fixtures are unavailable and tests skip.
"""
from __future__ import annotations

import ctypes
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as c

FONT_CANDIDATES = [
    Path('C:/Windows/Fonts/arial.ttf'), Path('C:/Windows/Fonts/tahoma.ttf'),
    Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    Path('/usr/share/fonts/dejavu/DejaVuSans.ttf'),
    Path('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf'),
]


def font_path() -> Path | None:
    return next((p for p in FONT_CANDIDATES if p.is_file()), None)


class PdfBuilder:
    def __init__(self):
        self.pdf = pdfium.PdfDocument.new()
        self._font = None
        self._font_buffer = None  # keep alive while the document lives

    def font(self):
        if self._font is None:
            path = font_path()
            if path is None:
                raise FileNotFoundError('no TrueType font with Vietnamese coverage found')
            data = path.read_bytes()
            self._font_buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            self._font = c.FPDFText_LoadFont(self.pdf, self._font_buffer, len(data),
                                             c.FPDF_FONT_TRUETYPE, 1)
        return self._font

    def page(self, width=612, height=792, rotation=0, lines=(), image=None):
        """lines: (text, x, y, size, (r, g, b)); image: (left, bottom, width, height)."""
        page = self.pdf.new_page(width, height)
        for text, x, y, size, color in lines:
            obj = c.FPDFPageObj_CreateTextObj(self.pdf, self.font(), size)
            encoded = (text + '\x00').encode('utf-16-le')
            buffer = ctypes.create_string_buffer(encoded)
            c.FPDFText_SetText(obj, ctypes.cast(buffer, ctypes.POINTER(c.FPDF_WCHAR)))
            c.FPDFPageObj_SetFillColor(obj, *color, 255)
            c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, x, y)
            c.FPDFPage_InsertObject(page, obj)
        if image is not None:
            left, bottom, w, h = image
            img = pdfium.PdfImage.new(self.pdf)
            bitmap = pdfium.PdfBitmap.new_native(64, 64, c.FPDFBitmap_BGRA)
            bitmap.fill_rect((40, 40, 40, 255), 0, 0, 32, 64)
            img.set_bitmap(bitmap)
            img.set_matrix(pdfium.PdfMatrix().scale(w, h).translate(left, bottom))
            page.insert_obj(img)
        page.gen_content()
        if rotation:
            page.set_rotation(rotation)
        return self

    def save(self, path) -> Path:
        self.pdf.save(str(path))
        return Path(path)
