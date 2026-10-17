"""Native PDF text/layout extraction with PDFium (pypdfium2) — ADR-22.

Per page: characters with boxes, font, size, weight and fill colour are grouped
into lines and then blocks (style and vertical gap boundaries). Colour is kept
because some books mark commentary layers by colour (Tử Bình). Each page is
classified text / sparse / mixed / scan / blank from character count and image
area — a page with little text is not an error by itself (docs/05). Nothing is
OCRed here; scan and mixed pages are flagged for the OCR stage.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import ctypes
import re
import unicodedata

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

PARSER_VERSION = f'pdfium-native-1/{pdfium.PYPDFIUM_INFO}/{pdfium.PDFIUM_INFO}'
MAX_PAGES = 3000
_DIGITS = re.compile(r'^(\d{1,4}|[ivxlcdm]{1,7})$', re.IGNORECASE)


class PdfRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Block:
    ordinal: int
    text: str
    bbox: list[float]
    start: int = 0
    end: int = 0
    attributes: dict = field(default_factory=dict)


@dataclass
class PageExtraction:
    number: int                      # physical, 1-based
    width: float                     # unrotated page space, points
    height: float
    rotation: int
    raw_text: str
    normalized_text: str
    blocks: list[Block]
    page_class: str                  # text | sparse | mixed | scan | blank
    image_area: float                # fraction of the page covered by images
    image_boxes: list                # normalised boxes of images, for region OCR
    char_count: int
    replacement_chars: int
    printed_label: str | None
    printed_label_source: str | None
    fonts: dict

    @property
    def needs_ocr(self) -> bool:
        return self.page_class in ('scan', 'mixed')

    @property
    def quality_state(self) -> str:
        if self.replacement_chars or self.page_class == 'scan':
            return 'review_required'
        return 'accepted'


def open_document(path: str) -> pdfium.PdfDocument:
    try:
        doc = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        message = str(exc).lower()
        if 'password' in message:
            raise PdfRejected('PASSWORD_REQUIRED', 'PDF is encrypted; upload an unlocked copy') from None
        raise PdfRejected('PDF_CORRUPT', 'PDF cannot be parsed') from None
    if len(doc) > MAX_PAGES:
        raise PdfRejected('PAGE_LIMIT', f'PDF has more than {MAX_PAGES} pages')
    return doc


def _normalizer(width: float, height: float, rotation: int):
    """PDF user space (origin bottom-left) → 0..1 box after rotation, origin top-left."""
    def to_box(left: float, bottom: float, right: float, top: float) -> list[float]:
        x0, x1 = left / width, right / width
        y0, y1 = 1 - top / height, 1 - bottom / height   # flip to top-left origin
        if rotation == 90:
            x0, y0, x1, y1 = 1 - y1, x0, 1 - y0, x1
        elif rotation == 180:
            x0, y0, x1, y1 = 1 - x1, 1 - y1, 1 - x0, 1 - y0
        elif rotation == 270:
            x0, y0, x1, y1 = y0, 1 - x1, y1, 1 - x0
        return [round(min(max(v, 0.0), 1.0), 5) for v in (x0, y0, x1, y1)]
    return to_box


def _images(page: pdfium.PdfPage, width: float, height: float, to_box) -> tuple[float, list]:
    """Covered fraction and normalised boxes of image objects (candidate OCR regions)."""
    total, boxes = 0.0, []
    for obj in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
        left, bottom, right, top = obj.get_bounds()
        area = max(0.0, min(right, width) - max(left, 0.0)) * max(0.0, min(top, height)
                                                                   - max(bottom, 0.0))
        if area <= 0:
            continue
        total += area
        boxes.append(to_box(max(left, 0.0), max(bottom, 0.0), min(right, width), min(top, height)))
    fraction = round(min(total / (width * height), 1.0), 4) if width and height else 0.0
    return fraction, boxes


def _chars(textpage: pdfium.PdfTextPage):
    """Yield (char, box or None, style) for every character index, generated breaks included."""
    count = textpage.count_chars()
    text = textpage.get_text_range(0, count) if count else ''
    per_char = len(text) == count  # surrogate pairs break the 1:1 mapping
    name = ctypes.create_string_buffer(128)
    flags = ctypes.c_int()
    r, g, b, a = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    for i in range(count):
        ch = text[i] if per_char else textpage.get_text_range(i, 1)
        if ch in '\r\n' or pdfium_c.FPDFText_IsGenerated(textpage, i) == 1:
            yield ch, None, None
            continue
        box = textpage.get_charbox(i, loose=False)
        pdfium_c.FPDFText_GetFontInfo(textpage, i, name, 128, flags)
        pdfium_c.FPDFText_GetFillColor(textpage, i, r, g, b, a)
        style = (name.value.decode('latin-1').split('+')[-1],
                 round(pdfium_c.FPDFText_GetFontSize(textpage, i), 1),
                 pdfium_c.FPDFText_GetFontWeight(textpage, i),
                 f'#{r.value:02x}{g.value:02x}{b.value:02x}')
        yield ch, box, style


def _lines(textpage: pdfium.PdfTextPage) -> list[dict]:
    lines, current = [], {'chars': [], 'boxes': [], 'styles': Counter()}
    for ch, box, style in _chars(textpage):
        if ch == '\n':
            lines.append(current)
            current = {'chars': [], 'boxes': [], 'styles': Counter()}
            continue
        if ch == '\r':
            continue
        current['chars'].append(ch)
        if box is not None and not ch.isspace():
            current['boxes'].append(box)
            current['styles'][style] += 1
    lines.append(current)
    result = []
    for line in lines:
        text = ''.join(line['chars']).strip()
        if not text:
            continue
        boxes = line['boxes'] or [(0, 0, 0, 0)]
        result.append({'text': text,
                       'left': min(b[0] for b in boxes), 'bottom': min(b[1] for b in boxes),
                       'right': max(b[2] for b in boxes), 'top': max(b[3] for b in boxes),
                       'style': line['styles'].most_common(1)[0][0] if line['styles'] else None,
                       'styles': line['styles']})
    return result


def _same_block(prev: dict, line: dict) -> bool:
    if prev['style'] is None or line['style'] is None:
        return False
    _, size_a, _, color_a = prev['style']
    _, size_b, _, color_b = line['style']
    height = max(prev['top'] - prev['bottom'], 1.0)
    gap = prev['bottom'] - line['top']           # PDF y grows upwards
    similar_size = abs(size_a - size_b) <= 0.15 * max(size_a, size_b, 1.0)
    return color_a == color_b and similar_size and -height < gap <= 1.2 * height


def _blocks(lines: list[dict], to_box) -> list[Block]:
    groups: list[list[dict]] = []
    for line in lines:
        if groups and _same_block(groups[-1][-1], line):
            groups[-1].append(line)
        else:
            groups.append([line])
    blocks = []
    for ordinal, group in enumerate(groups):
        styles = Counter()
        for line in group:
            styles.update(line['styles'])
        font, size, weight, color = styles.most_common(1)[0][0] if styles else (None, 0, 0, None)
        text = unicodedata.normalize('NFC', '\n'.join(line['text'] for line in group))
        blocks.append(Block(ordinal, text, to_box(min(line['left'] for line in group),
                                                  min(line['bottom'] for line in group),
                                                  max(line['right'] for line in group),
                                                  max(line['top'] for line in group)),
                            attributes={'font': font, 'size': size, 'weight': weight,
                                        'color': color, 'lines': len(group)}))
    return blocks


def _classify(char_count: int, image_area: float) -> str:
    if char_count == 0:
        return 'scan' if image_area >= 0.3 else 'blank'
    if char_count < 20 and image_area >= 0.5:
        return 'scan'                 # a few stray characters on a scanned image
    if image_area >= 0.25:
        return 'mixed'                # real text plus a large figure/table image
    return 'sparse' if char_count < 100 else 'text'


def _label(doc: pdfium.PdfDocument, index: int, blocks: list[Block]) -> tuple[str | None, str | None]:
    try:
        label = doc.get_page_label(index)
    except Exception:  # noqa: BLE001 - malformed label trees are common; fall back
        label = None
    if label:
        return label, 'pdf_label'
    # A short number alone in the first or last block is a printed folio candidate.
    for block in (blocks[:1] + blocks[-1:]) if blocks else []:
        first_line = block.text.split('\n', 1)[0].strip()
        if _DIGITS.match(first_line):
            return first_line, 'heuristic'
    return None, None


def extract_page(doc: pdfium.PdfDocument, index: int) -> PageExtraction:
    page = doc[index]
    try:
        width, height = page.get_size()
        rotation = page.get_rotation()
        if rotation in (90, 270):
            # get_size() is the displayed size; character/object coordinates live in the
            # unrotated page space, so normalise against the unrotated dimensions.
            width, height = height, width
        textpage = page.get_textpage()
        try:
            raw_text = textpage.get_text_range()
            lines = _lines(textpage)
        finally:
            textpage.close()
        to_box = _normalizer(width, height, rotation)
        image_area, image_boxes = _images(page, width, height, to_box)
    finally:
        page.close()
    blocks = _blocks(lines, to_box)
    position = 0
    parts = []
    for block in blocks:
        block.start, block.end = position, position + len(block.text)
        parts.append(block.text)
        position = block.end + 2   # blocks are joined by a blank line
    normalized = '\n\n'.join(parts)
    char_count = sum(1 for c in normalized if not c.isspace())
    fonts = Counter()
    for block in blocks:
        fonts[f"{block.attributes['font']}|{block.attributes['color']}"] += len(block.text)
    label, source = _label(doc, index, blocks)
    return PageExtraction(
        number=index + 1, width=width, height=height, rotation=rotation, raw_text=raw_text,
        normalized_text=normalized, blocks=blocks,
        page_class=_classify(char_count, image_area), image_area=image_area,
        image_boxes=image_boxes,
        char_count=char_count, replacement_chars=normalized.count('�'),
        printed_label=label, printed_label_source=source, fonts=dict(fonts.most_common(8)))
