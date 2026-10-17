"""Page/region OCR with Tesseract in a bounded subprocess (docs/05 OCR, docs/12 sandbox).

Only pages flagged by native extraction are OCRed: whole ``scan`` pages, and
image regions of other pages. Rendering is capped in pixels (pixel bombs) and
DPI steps down once on timeout before the page goes to review. OCR never
replaces native text: OCR blocks that overlap a native block are dropped and
the rest are appended after the native blocks, so native offsets — and any
evidence pointing at them — stay valid in the new revision.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import os
import shutil
import subprocess
import sys
import unicodedata

import pypdfium2 as pdfium

DEFAULT_LANGS = 'vie+eng'
DPI_STEPS = (300, 200)
MAX_PIXELS = 40_000_000           # ~ A3 at 300 dpi; larger renders step DPI down
MIN_DPI = 120
TIMEOUT_SECONDS = 120
MIN_REGION_AREA = 0.02            # ignore tiny images (logos, ornaments)
MEMORY_LIMIT = 2 * 1024 ** 3


class OcrTimeout(Exception):
    pass


class OcrUnavailable(Exception):
    pass


@dataclass
class OcrWord:
    text: str
    box: list[float]       # normalised page box, top-left origin
    conf: float
    group: tuple           # (region, block, paragraph, line)


@dataclass
class OcrBlock:
    text: str
    bbox: list[float]
    conf: float
    region: int


class TesseractEngine:
    """Runs the ``tesseract`` CLI on a PPM image; TSV output with word boxes."""

    def __init__(self, binary: str | None = None, timeout: int = TIMEOUT_SECONDS):
        self.binary = binary or shutil.which('tesseract')
        self.timeout = timeout
        if not self.binary:
            raise OcrUnavailable('tesseract is not installed in this worker image')
        self._version = None

    @property
    def version(self) -> str:
        if self._version is None:
            out = subprocess.run([self.binary, '--version'], capture_output=True, timeout=30,
                                 env=self._env())
            self._version = (out.stdout or out.stderr).decode(errors='replace').split('\n')[0]
        return self._version

    def _env(self) -> dict:
        env = {'OMP_THREAD_LIMIT': '1', 'PATH': os.environ.get('PATH', '')}
        if 'TESSDATA_PREFIX' in os.environ:
            env['TESSDATA_PREFIX'] = os.environ['TESSDATA_PREFIX']
        return env

    def _limits(self):
        if sys.platform == 'win32':
            return None
        import resource

        def apply():
            resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
            resource.setrlimit(resource.RLIMIT_CPU, (self.timeout + 5, self.timeout + 5))
        return apply

    def words(self, image: bytes, langs: str) -> list[dict]:
        try:
            out = subprocess.run([self.binary, 'stdin', 'stdout', '-l', langs, '--psm', '3', 'tsv'],
                                 input=image, capture_output=True, timeout=self.timeout,
                                 env=self._env(), preexec_fn=self._limits())
        except subprocess.TimeoutExpired:
            raise OcrTimeout(f'tesseract exceeded {self.timeout}s') from None
        if out.returncode != 0:
            raise OcrUnavailable(out.stderr.decode(errors='replace')[:300])
        rows = csv.DictReader(io.StringIO(out.stdout.decode('utf-8', 'replace')), delimiter='\t',
                              quoting=csv.QUOTE_NONE)
        return [r for r in rows if r.get('level') == '5' and (r.get('text') or '').strip()]


def render(doc: pdfium.PdfDocument, index: int, dpi: int) -> tuple[bytes, int, int, int]:
    """PPM (P6) of the displayed page; returns (image, width_px, height_px, dpi used)."""
    page = doc[index]
    try:
        width, height = page.get_size()      # displayed orientation
        while dpi > MIN_DPI and (width * dpi / 72) * (height * dpi / 72) > MAX_PIXELS:
            dpi = int(dpi * 0.8)
        if (width * dpi / 72) * (height * dpi / 72) > MAX_PIXELS:
            raise OcrTimeout('page too large to render within the pixel limit')
        bitmap = page.render(scale=dpi / 72, rev_byteorder=True, fill_color=(255, 255, 255, 255),
                             prefer_bgrx=False)
        try:
            w, h, stride = bitmap.width, bitmap.height, bitmap.stride
            channels = len(bitmap.mode)
            buffer = bytes(bitmap.buffer)
        finally:
            bitmap.close()
    finally:
        page.close()
    rgb = bytearray()
    for row in range(h):
        line = buffer[row * stride: row * stride + w * channels]
        if channels == 3:
            rgb += line
        else:
            rgb += b''.join(line[i:i + 3] for i in range(0, len(line), channels))
    return b'P6 %d %d 255\n' % (w, h) + bytes(rgb), w, h, dpi


def crop(ppm: bytes, w: int, h: int, box: list[float]) -> tuple[bytes, int, int, int, int]:
    header_end = ppm.index(b'\n', 0) + 1
    pixels = ppm[header_end:]
    x0, y0 = int(box[0] * w), int(box[1] * h)
    x1, y1 = max(int(box[2] * w), x0 + 1), max(int(box[3] * h), y0 + 1)
    out = bytearray()
    for row in range(y0, y1):
        out += pixels[(row * w + x0) * 3:(row * w + x1) * 3]
    cw, ch = x1 - x0, y1 - y0
    return b'P6 %d %d 255\n' % (cw, ch) + bytes(out), x0, y0, cw, ch


def ocr_page(doc: pdfium.PdfDocument, index: int, regions: list[list[float]] | None,
             engine: TesseractEngine, langs: str = DEFAULT_LANGS) -> tuple[list[OcrWord], int]:
    """OCR a whole page (regions=None) or listed regions; DPI steps down once on timeout."""
    last_error: Exception | None = None
    for dpi in DPI_STEPS:
        try:
            image, w, h, used = render(doc, index, dpi)
            targets = [(0, [0.0, 0.0, 1.0, 1.0])] if regions is None else list(enumerate(regions))
            words: list[OcrWord] = []
            for region, box in targets:
                part, ox, oy, cw, ch = crop(image, w, h, box) if regions is not None else \
                    (image, 0, 0, w, h)
                for r in engine.words(part, langs):
                    left, top = ox + int(r['left']), oy + int(r['top'])
                    right, bottom = left + int(r['width']), top + int(r['height'])
                    words.append(OcrWord(
                        unicodedata.normalize('NFC', r['text'].strip()),
                        [round(left / w, 5), round(top / h, 5), round(right / w, 5),
                         round(bottom / h, 5)],
                        float(r['conf']),
                        (region, int(r['block_num']), int(r['par_num']), int(r['line_num']))))
            return words, used
        except OcrTimeout as exc:
            last_error = exc
    raise OcrTimeout(str(last_error))


def group_blocks(words: list[OcrWord]) -> list[OcrBlock]:
    """Words → lines → paragraph blocks, in reading order of Tesseract's own grouping."""
    paragraphs: dict[tuple, list[OcrWord]] = {}
    for word in words:
        paragraphs.setdefault(word.group[:3], []).append(word)
    blocks = []
    for key, members in paragraphs.items():
        lines: dict[int, list[OcrWord]] = {}
        for word in members:
            lines.setdefault(word.group[3], []).append(word)
        text = '\n'.join(' '.join(w.text for w in line) for _, line in sorted(lines.items()))
        boxes = [w.box for w in members]
        blocks.append(OcrBlock(text, [min(b[0] for b in boxes), min(b[1] for b in boxes),
                                      max(b[2] for b in boxes), max(b[3] for b in boxes)],
                               round(sum(w.conf for w in members) / len(members), 1), key[0]))
    blocks.sort(key=lambda b: (b.bbox[1], b.bbox[0]))
    return blocks


def _overlap(a: list[float], b: list[float]) -> float:
    """Fraction of box ``a`` covered by box ``b``."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    area = max((a[2] - a[0]) * (a[3] - a[1]), 1e-9)
    return inter / area


def new_ocr_blocks(ocr_blocks: list[OcrBlock], native_boxes: list[list[float]],
                   threshold: float = 0.5) -> list[OcrBlock]:
    """Drop OCR blocks that duplicate native text (mostly inside a native block)."""
    return [b for b in ocr_blocks if b.text.strip()
            and all(_overlap(b.bbox, n) < threshold for n in native_boxes)]
