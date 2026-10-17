"""DOCX text with stable XML anchors, and its canonical PDF rendering (docs/05 · Locator).

The DOCX XML is the authoritative text. Every body paragraph and table gets an
anchor path (``body/p[12]``, ``body/tbl[3]``) that survives rendering changes.
A canonical PDF rendered by a pinned LibreOffice gives "rendered pages" for the
viewer; paragraphs are located on it by text matching. When rendering fails or
a paragraph cannot be found, the anchor alone is the locator — no page number
is invented.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

from .layout import speaker_marker
from .normalize import normalize

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
PARSER_VERSION = 'docx-xml-2'
RENDER_TIMEOUT = 240
MAX_XML_BYTES = 50 * 1024 * 1024
_HEADING = re.compile(r'^(heading|title|subtitle|u\d|tieude|tiêuđề)', re.IGNORECASE)
_WS = re.compile(r'\s+')


class DocxRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class DocxBlock:
    anchor: str                       # body/p[i] | body/tbl[j]
    kind: str                         # paragraph | heading | table
    text: str
    style: str | None = None
    table_cells: list | None = None
    page: int | None = None           # rendered page, when located
    bbox: list[float] | None = None
    located: str | None = None        # exact (text matched) | inferred (between neighbours)
    speaker: str = 'unknown'
    marker: str | None = None


@dataclass
class DocxDocument:
    blocks: list[DocxBlock]
    rendered_pdf: Path | None = None
    renderer: str | None = None
    render_error: str | None = None
    rendered_pages: int = 0
    located: int = 0
    extra: dict = field(default_factory=dict)


def _xml(archive: zipfile.ZipFile, name: str) -> ET.Element:
    info = archive.getinfo(name)
    if info.file_size > MAX_XML_BYTES:
        raise DocxRejected('DOCX_XML_LIMIT', f'{name} is too large')
    payload = archive.read(info)
    if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise DocxRejected('DOCX_INVALID', 'DOCX XML declares entities')
    return ET.fromstring(payload)


def _paragraph_text(p: ET.Element) -> str:
    parts = []
    for node in p.iter():
        if node.tag == W + 't' and node.text:
            parts.append(node.text)
        elif node.tag == W + 'tab':
            parts.append('\t')
        elif node.tag in (W + 'br', W + 'cr'):
            parts.append('\n')
    return normalize(''.join(parts))[0].strip()


def _style(p: ET.Element) -> str | None:
    style = p.find(f'{W}pPr/{W}pStyle')
    return style.get(W + 'val') if style is not None else None


def _is_heading(p: ET.Element, style: str | None) -> bool:
    if p.find(f'{W}pPr/{W}outlineLvl') is not None:
        return True
    return bool(style and _HEADING.match(style))


def _children(container: ET.Element):
    """Body-level paragraphs and tables, unwrapping content controls (w:sdt)."""
    for child in container:
        if child.tag == W + 'sdt':
            content = child.find(W + 'sdtContent')
            if content is not None:
                yield from _children(content)
        elif child.tag in (W + 'p', W + 'tbl'):
            yield child


def parse(path: str | Path) -> list[DocxBlock]:
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise DocxRejected('DOCX_INVALID', 'Not a readable DOCX archive') from None
    with archive:
        if 'word/document.xml' not in archive.namelist():
            raise DocxRejected('DOCX_INVALID', 'Archive is not a Word document')
        body = _xml(archive, 'word/document.xml').find(W + 'body')
    if body is None:
        return []
    blocks, p_index, t_index = [], 0, 0
    for node in _children(body):
        if node.tag == W + 'p':
            p_index += 1
            text = _paragraph_text(node)
            if not text:
                continue
            style = _style(node)
            block = DocxBlock(f'body/p[{p_index}]',
                              'heading' if _is_heading(node, style) else 'paragraph', text, style)
            layer, marker = speaker_marker(text)
            if layer:
                block.speaker, block.marker = layer, marker
            blocks.append(block)
        else:
            t_index += 1
            rows = []
            for tr in node.iter(W + 'tr'):
                rows.append([' '.join(_paragraph_text(p) for p in tc.iter(W + 'p')).strip()
                             for tc in tr.iter(W + 'tc')])
            if any(cell for row in rows for cell in row):
                text = '\n'.join(' | '.join(row) for row in rows)
                blocks.append(DocxBlock(f'body/tbl[{t_index}]', 'table',
                                        unicodedata.normalize('NFC', text), table_cells=rows))
    return blocks


# ---- canonical rendering -------------------------------------------------------------

def soffice() -> str | None:
    return shutil.which('soffice') or shutil.which('libreoffice')


def renderer_version() -> str | None:
    binary = soffice()
    if not binary:
        return None
    out = subprocess.run([binary, '--version'], capture_output=True, timeout=60)
    return out.stdout.decode(errors='replace').strip().split('\n')[0] or None


def render(path: str | Path, out_dir: str | Path, timeout: int = RENDER_TIMEOUT) -> Path:
    """DOCX → PDF with a throwaway LibreOffice profile; raises DocxRejected on failure."""
    binary = soffice()
    if not binary:
        raise DocxRejected('RENDER_UNAVAILABLE', 'LibreOffice is not installed in this worker')
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory() as profile:
        command = [binary, f'-env:UserInstallation=file://{Path(profile).as_posix()}',
                   '--headless', '--norestore', '--nolockcheck', '--nologo',
                   '--convert-to', 'pdf', '--outdir', str(out_dir), str(path)]
        try:
            subprocess.run(command, capture_output=True, timeout=timeout,
                           env={'PATH': os.environ.get('PATH', ''), 'HOME': profile})
        except subprocess.TimeoutExpired:
            raise DocxRejected('RENDER_TIMEOUT', f'LibreOffice exceeded {timeout}s') from None
    pdf = out_dir / (Path(path).stem + '.pdf')
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise DocxRejected('RENDER_FAILED', 'LibreOffice produced no PDF')
    return pdf


def _compact(text: str) -> tuple[str, list[int]]:
    """Letters and digits only, NFC, lower case, plus a map back to original indices.

    Renders add what the XML does not contain — automatic list numbers ("1."),
    dot leaders for tabs in tables of contents, soft hyphens — so matching keeps
    only alphanumerics; the DOCX text then appears as a substring of the render.
    """
    chars, index = [], []
    for i, ch in enumerate(unicodedata.normalize('NFC', text)):
        if not ch.isalnum():
            continue
        chars.append(ch.lower())
        index.append(i)
    return ''.join(chars), index


PROBE = 40  # compact characters: short enough to stay on one rendered page
MIN_ADVANCE = 6  # shorter probes may place a block but never move the search cursor
NEAR_PAGES = 3   # phrases shorter than LONG_PROBE repeat ("Ví dụ nam mệnh:") — search close by
LONG_PROBE = 25


def _probes(block: DocxBlock) -> list[tuple[str, bool]]:
    """(probe, near_only): a table by its rows, text by its start then its end.

    Tables are always searched close by: the same chart is often printed again in a
    later example, and a far match would drag the cursor past everything between.
    """
    if block.kind == 'table' and block.table_cells:
        # Narrow rendered cells wrap mid-word but keep row order, so a whole row is a
        # safe probe; a single short cell such as "Tân" is not.
        # Pillar tables repeat rows across examples, so use all rows in order.
        whole = _compact(''.join(''.join(row) for row in block.table_cells))[0]
        return [(whole[:PROBE], True)] if len(whole) >= MIN_ADVANCE else []
    needle, _ = _compact(block.text)
    if not needle:
        return []
    near = len(needle) < LONG_PROBE
    probes = [(needle[:PROBE], near)]
    if len(needle) > 2 * PROBE:
        probes.append((needle[-PROBE:], near))   # paragraph that starts on the previous page
    return probes


def _find(pages: list[dict], probe: str, near: bool, page_no: int,
          cursor: int) -> tuple[int, int] | None:
    """First occurrence at or after (page_no, cursor), keeping document order.

    Near-only probes (short phrases, tables) look a few pages ahead: a common
    phrase matched far away would drag the cursor past everything in between.
    """
    last = min(len(pages), page_no + NEAR_PAGES) if near else len(pages)
    for p in range(page_no, last):
        start = pages[p]['compact'].find(probe, cursor if p == page_no else 0)
        if start >= 0:
            return p, start
    return None


def _infer_between(blocks: list[DocxBlock]) -> int:
    """Unmatched blocks squeezed between two matched blocks on the same rendered page.

    Narrow table cells wrap and interleave in the render, so tables often cannot be
    matched verbatim; their page is certain when both neighbours sit on one page.
    No box is invented.
    """
    inferred = 0
    previous = None
    for i, block in enumerate(blocks):
        if block.located == 'exact':
            previous = block.page
            continue
        following = next((b.page for b in blocks[i + 1:] if b.located == 'exact'), None)
        if previous is not None and previous == following:
            block.page, block.located = previous, 'inferred'
            inferred += 1
    return inferred


def locate(blocks: list[DocxBlock], pdf_path: Path) -> int:
    """Assign rendered page and box to blocks, in document order; returns how many matched."""
    import pypdfium2 as pdfium

    from .pdf_native import _normalizer

    doc = pdfium.PdfDocument(str(pdf_path))
    located = 0
    try:
        pages = []
        for i in range(len(doc)):
            page = doc[i]
            textpage = page.get_textpage()
            raw = textpage.get_text_range()
            compact, index = _compact(raw)
            width, height = page.get_size()
            pages.append({'tp': textpage, 'page': page, 'raw_len': len(raw), 'compact': compact,
                          'index': index, 'to_box': _normalizer(width, height, page.get_rotation())})
        page_no, cursor = 0, 0
        for block in blocks:
            for probe, near in _probes(block):
                hit = _find(pages, probe, near, page_no, cursor)
                if hit is None:
                    continue
                p, start = hit
                info = pages[p]
                first = info['index'][start]
                last = info['index'][min(start + len(probe), len(info['index'])) - 1]
                boxes = [info['tp'].get_charbox(i) for i in range(first, last + 1)]
                boxes = [b for b in boxes if b[2] > b[0]]
                block.page, block.located = p + 1, 'exact'
                if boxes:
                    block.bbox = info['to_box'](min(b[0] for b in boxes), min(b[1] for b in boxes),
                                                max(b[2] for b in boxes), max(b[3] for b in boxes))
                if len(probe) >= MIN_ADVANCE:   # a short match could be a coincidence
                    page_no, cursor = p, start + len(probe)
                located += 1
                break
        located += _infer_between(blocks)
    finally:
        for p in locals().get('pages', []):
            p['tp'].close()
            p['page'].close()
        doc.close()
    return located


def extract(path: str | Path, work_dir: str | Path, render_pdf: bool = True) -> DocxDocument:
    blocks = parse(path)
    result = DocxDocument(blocks)
    if not render_pdf:
        return result
    try:
        pdf = render(path, work_dir)
    except DocxRejected as exc:
        result.render_error = exc.code
        return result
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(str(pdf)) as rendered:
        result.rendered_pages = len(rendered)
    result.rendered_pdf, result.renderer = pdf, renderer_version()
    result.located = locate(blocks, pdf)
    return result
