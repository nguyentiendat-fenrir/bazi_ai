"""Page/region OCR with SenOCR-Vi (Vietnamese fine-tune of PaddleOCR-VL-1.6) on the GPU.

Only pages flagged by native extraction are OCRed: whole ``scan`` pages, and
image regions of other pages. Rendering is capped in pixels (pixel bombs). OCR
never replaces native text: OCR blocks that overlap a native block are dropped
and the rest are appended after the native blocks, so native offsets — and any
evidence pointing at them — stay valid in the new revision.

The PaddleOCR-VL pipeline does layout (PP-DocLayoutV3) and recognition, both on
the transformers engine (torch; paddlepaddle is not installed — same output, and
its CUDA wheels conflict with torch's); its
labelled blocks map onto ours: titles → ``heading``, tables (HTML) → ``table``
with cells and one line per row (so printed pillar charts read like native chart
rows), page numbers/headers/footers → roles that never reach chunks. The model
runs through the transformers engine in bfloat16 (~2.5–3.2 GB VRAM with the
layout model; measured 1–7 s/page on the RTX 4090, 2026-10-21) and is loaded once
per worker process, then released after ``IDLE_SECONDS`` without pages so the
GPU is free for the other models on this host.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
import logging
import os
from pathlib import Path
import threading
import time
import unicodedata

import pypdfium2 as pdfium

from . import layout

log = logging.getLogger('bazi.ocr')
DPI_STEPS = (200, 150)
OOM_DPI_STEPS = (200, 150, 120)   # out of GPU memory: smaller renders before giving up
MAX_PIXELS = 40_000_000           # ~ A3 at 300 dpi; larger renders step DPI down
MIN_DPI = 120
MIN_REGION_AREA = 0.02            # ignore tiny images (logos, ornaments)
# Releasing the model when idle and loading it again later could leave the old copy alive
# in PaddleX's worker threads (two copies > the cap: OOM on the first page of the next book),
# so by default it stays loaded for the worker's life; OCR_IDLE_SECONDS > 0 turns release on.
IDLE_SECONDS = int(os.environ.get('OCR_IDLE_SECONDS', '0'))
# The card is shared with Qwen (~12.9 GB) and Gemma (~5.9 GB): OCR gets a hard cap so it
# can never push the others into OOM, and small VL batches so it fits under that cap.
GPU_MEMORY_GB = float(os.environ.get('OCR_GPU_MEMORY_GB', '3.0'))
VL_BATCH = int(os.environ.get('OCR_VL_BATCH', '1'))   # >1 breaks the HF processor (no padding)
ROLES = {'number': 'folio', 'header': 'header', 'footer': 'footer', 'header_image': 'header',
         'footer_image': 'footer'}
HEADINGS = {'doc_title': 1, 'paragraph_title': 2, 'figure_title': None}
SKIP = {'image', 'chart', 'seal'}


class OcrTimeout(Exception):
    pass


class OcrUnavailable(Exception):
    pass


class OcrOutOfMemory(Exception):
    """CUDA ran out of memory (another model on the card grew): transient, retry later."""


@dataclass
class OcrBlock:
    text: str
    bbox: list[float]
    conf: float | None
    region: int
    kind: str = 'paragraph'            # paragraph | heading | table | caption
    level: int | None = None
    label: str = 'text'
    role: str | None = None
    table_cells: list[list[str]] | None = None
    attributes: dict = field(default_factory=dict)


class _TableParser(HTMLParser):
    """``<table><tr><td>…`` (PaddleOCR-VL output) → rows of cell strings."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.rows.append([])
        elif tag in ('td', 'th'):
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ('td', 'th') and self._cell is not None:
            if not self.rows:
                self.rows.append([])
            self.rows[-1].append(' '.join(''.join(self._cell).split()))
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def table_rows(html: str) -> list[list[str]]:
    parser = _TableParser()
    parser.feed(html)
    return [row for row in parser.rows if any(cell for cell in row)]


def to_blocks(results: list[dict], width: int, height: int, region: int = 0,
              offset: tuple[int, int] = (0, 0), page_size: tuple[int, int] | None = None
              ) -> list[OcrBlock]:
    """PaddleOCR-VL ``parsing_res_list`` items → OcrBlocks with page-normalised boxes."""
    pw, ph = page_size or (width, height)
    blocks = []
    for item in results:
        label = item.get('block_label') or 'text'
        content = unicodedata.normalize('NFC', (item.get('block_content') or '').strip())
        if label in SKIP or not content:
            continue
        x0, y0, x1, y1 = [float(v) for v in item.get('block_bbox') or (0, 0, width, height)]
        box = [round((x0 + offset[0]) / pw, 5), round((y0 + offset[1]) / ph, 5),
               round((x1 + offset[0]) / pw, 5), round((y1 + offset[1]) / ph, 5)]
        block = OcrBlock(content, box, None, region, label=label, role=ROLES.get(label))
        if label == 'table' or content.lstrip().startswith('<table'):
            rows = table_rows(content)
            if not rows:
                continue
            block.kind, block.table_cells = 'table', rows
            block.text = '\n'.join(' '.join(cell for cell in row if cell) for row in rows)
            if all(layout.is_chart_row(line) for line in block.text.split('\n') if line.strip()):
                block.attributes['chart_row'] = True
        elif label in HEADINGS and HEADINGS[label] is not None:
            found = layout.heading(content, None, None, None, content.count('\n') + 1)
            block.kind = 'heading'
            block.level = found[0] if found else HEADINGS[label]
            block.attributes['heading_rule'] = found[1] if found else f'ocr_{label}'
        elif label == 'figure_title':
            block.kind = 'caption'
        elif all(layout.is_chart_row(line) for line in content.split('\n') if line.strip()):
            block.attributes['chart_row'] = True
        blocks.append(block)
    return blocks


_BRACKETS = '【】〔〕[]（）()「」 '
# Scanned editions label the layers as bracketed titles ("【 Nguyên văn 】", "【Thích nghĩa】").
_OCR_MARKERS = {'thích nghĩa': 'commentator', 'giải nghĩa': 'commentator',
                'bình giải': 'commentator', 'dịch nghĩa': 'translator'}


def _marker(text_: str) -> str | None:
    bare = text_.strip().strip(_BRACKETS).strip()
    layer, _ = layout.speaker_marker(bare)
    if layer:
        return layer
    lowered = bare.lower()
    return next((v for k, v in _OCR_MARKERS.items() if lowered.startswith(k)), None)


def assign_speakers(blocks: list[OcrBlock]) -> None:
    """"Nguyên văn:" / "Từ chú:" markers — inline, or as a bracketed title — set the speaker
    for that block and the following paragraphs of the page until the next marker or
    another heading (OCR has no colour cue). A marker title stays a heading."""
    current = None
    for block in blocks:
        if block.role:
            continue
        layer = _marker(block.text)
        if block.kind == 'heading':
            current = layer
            if layer:
                block.attributes['marker_heading'] = layer
            continue
        if layer:
            current = layer
            block.attributes.update(speaker=layer, marker=True)
        elif current:
            block.attributes.update(speaker=current, speaker_inherited=True)


class SenOcrEngine:
    """SenOCR-Vi inside the PaddleOCR-VL-1.6 pipeline (layout + VL recognition)."""

    def __init__(self, model_dir: str | None = None, device: str = 'gpu:0'):
        self.model_dir = model_dir or os.environ.get('OCR_MODEL_DIR', '/models/senocr-vi/current')
        self.device = device
        self._pipeline = None
        self._lock = threading.Lock()
        self._last_used = 0.0
        self._reaper: threading.Thread | None = None
        resolved = Path(self.model_dir)
        if not (resolved / 'model.safetensors').exists():
            raise OcrUnavailable(f'SenOCR-Vi not found in {self.model_dir}; run cli fetch-models')
        self.version = f'senocr-vi@{resolved.resolve().name}+paddleocr-vl-1.6'

    def _load(self):
        import paddlex
        import yaml
        config_path = Path(paddlex.__file__).parent / 'configs/pipelines/PaddleOCR-VL-1.6.yaml'
        config = yaml.safe_load(config_path.read_text())
        import torch
        if torch.cuda.is_available():
            total = torch.cuda.get_device_properties(0).total_memory
            torch.cuda.set_per_process_memory_fraction(
                min(1.0, GPU_MEMORY_GB * 1024 ** 3 / total), 0)
        config['SubModules']['VLRecognition'].update(model_dir=str(Path(self.model_dir).resolve()),
                                                     engine='transformers', batch_size=VL_BATCH)
        # Layout on the same engine: the whole pipeline runs on torch, no paddlepaddle needed.
        config['SubModules']['LayoutDetection']['engine'] = 'transformers'
        started = time.perf_counter()
        pipeline = paddlex.create_pipeline(config=config, device=self.device)
        log.info('ocr model loaded', extra={'event': 'ocr_loaded', 'model': self.version,
                                            'seconds': round(time.perf_counter() - started, 1)})
        return pipeline

    def _reap(self):
        while True:
            time.sleep(30)
            with self._lock:
                if self._pipeline is not None and time.monotonic() - self._last_used > IDLE_SECONDS:
                    self._pipeline = None
                    try:
                        import torch
                        torch.cuda.empty_cache()
                    except Exception:  # noqa: BLE001 - freeing is best effort
                        pass
                    log.info('ocr model released', extra={'event': 'ocr_released'})

    def recognize(self, image) -> list[dict]:
        """``image``: H×W×3 BGR uint8 array → PaddleOCR-VL ``parsing_res_list``."""
        with self._lock:
            if self._pipeline is None:
                self._pipeline = self._load()
                if self._reaper is None and IDLE_SECONDS > 0:
                    self._reaper = threading.Thread(target=self._reap, daemon=True)
                    self._reaper.start()
            self._last_used = time.monotonic()
            try:
                results = list(self._pipeline.predict(image))
            except Exception as exc:  # noqa: BLE001 - PaddleX wraps worker errors
                if 'out of memory' in str(exc).lower():
                    raise OcrOutOfMemory(str(exc)[:200]) from None
                raise
            finally:
                _free_cache()
            self._last_used = time.monotonic()
        items = []
        for result in results:
            data = result.json.get('res', result.json) if hasattr(result, 'json') else dict(result)
            items.extend(data.get('parsing_res_list') or [])
        return [{k: (v.tolist() if hasattr(v, 'tolist') else v) for k, v in item.items()}
                if isinstance(item, dict) else _item(item) for item in items]


def _free_cache() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 - freeing is best effort
        pass


def _item(block) -> dict:
    return {'block_label': getattr(block, 'label', 'text'),
            'block_content': getattr(block, 'content', ''),
            'block_bbox': list(getattr(block, 'bbox', [0, 0, 0, 0]))}


_ENGINE: SenOcrEngine | None = None
_ENGINE_LOCK = threading.Lock()


def shared_engine() -> SenOcrEngine:
    """One engine per worker process (the model is held once, released when idle)."""
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = SenOcrEngine()
        return _ENGINE


def render(doc: pdfium.PdfDocument, index: int, dpi: int):
    """BGR uint8 array of the displayed page; returns (image, width_px, height_px, dpi used)."""
    import numpy as np
    page = doc[index]
    try:
        width, height = page.get_size()      # displayed orientation
        while dpi > MIN_DPI and (width * dpi / 72) * (height * dpi / 72) > MAX_PIXELS:
            dpi = int(dpi * 0.8)
        if (width * dpi / 72) * (height * dpi / 72) > MAX_PIXELS:
            raise OcrTimeout('page too large to render within the pixel limit')
        bitmap = page.render(scale=dpi / 72, fill_color=(255, 255, 255, 255))
        try:
            array = bitmap.to_numpy()
            mode = bitmap.mode
        finally:
            bitmap.close()
    finally:
        page.close()
    if mode in ('BGRA', 'BGRX'):
        array = array[:, :, :3]
    elif mode in ('RGBA', 'RGBX'):
        array = array[:, :, [2, 1, 0]]
    elif mode == 'RGB':
        array = array[:, :, ::-1]
    elif mode == 'L':
        array = np.stack([array] * 3, axis=-1)
    image = np.ascontiguousarray(array)
    return image, image.shape[1], image.shape[0], dpi


def ocr_page(doc: pdfium.PdfDocument, index: int, regions: list[list[float]] | None,
             engine: SenOcrEngine) -> tuple[list[OcrBlock], int]:
    """OCR a whole page (regions=None) or listed regions. A render too large steps DPI down
    once; running out of GPU memory steps down to 120 dpi before giving up."""
    last_error: Exception | None = None
    for dpi in OOM_DPI_STEPS:
        try:
            image, w, h, used = render(doc, index, dpi)
            targets = [(0, [0.0, 0.0, 1.0, 1.0])] if regions is None else list(enumerate(regions))
            blocks: list[OcrBlock] = []
            for region, box in targets:
                if regions is None:
                    part, ox, oy = image, 0, 0
                else:
                    x0, y0 = int(box[0] * w), int(box[1] * h)
                    x1, y1 = max(int(box[2] * w), x0 + 1), max(int(box[3] * h), y0 + 1)
                    part, ox, oy = image[y0:y1, x0:x1], x0, y0
                found = engine.recognize(part)
                blocks += to_blocks(found, part.shape[1], part.shape[0], region, (ox, oy), (w, h))
            assign_speakers(blocks)
            return blocks, used
        except OcrOutOfMemory as exc:
            last_error = exc
            _free_cache()
            continue
        except (OcrTimeout, MemoryError) as exc:
            last_error = exc
            if dpi not in DPI_STEPS:
                break
        except RuntimeError as exc:
            if 'out of memory' not in str(exc).lower():
                raise
            last_error = OcrOutOfMemory(str(exc)[:200])
            _free_cache()
            continue
        if dpi == DPI_STEPS[-1]:
            break                      # timeouts stop at the normal steps
    if isinstance(last_error, OcrOutOfMemory):
        raise last_error
    raise OcrTimeout(str(last_error))


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
