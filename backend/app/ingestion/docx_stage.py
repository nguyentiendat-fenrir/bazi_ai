"""DOCX ``extract`` stage: XML text with anchors, rendered pages when LibreOffice succeeds.

Rendered mode: one ``docx_rendered_page`` per rendered page holding the DOCX
paragraphs located on it (bbox from the render); ``rendered_object_id`` points
at the stored canonical PDF. A paragraph the matcher could not place keeps its
anchor and ``located=false`` — the UI cites "đoạn" rather than a page.
Anchor mode (render failed/unavailable): ``docx_anchor`` pages are internal
sequence numbers grouped by headings, with no geometry and no page claim.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..documents.corrections import effective_revision
from ..documents.formats import DOCX
from ..storage.service import store_object
from .docx import PARSER_VERSION, DocxBlock, DocxDocument, DocxRejected, extract, renderer_version
from .pdf_stages import local_source
from .worker import JobContext, Unit, UnitFailed

ANCHOR_PAGE_BLOCKS = 40
MIN_LOCATED_RATIO = 0.9


def _pages(doc: DocxDocument) -> list[tuple[int, str, list[DocxBlock]]]:
    """(number, page_kind, blocks) in document order."""
    if doc.rendered_pdf is not None:
        pages: dict[int, list[DocxBlock]] = {}
        current = 1
        for block in doc.blocks:
            current = block.page or current   # unlocated blocks travel with their neighbours
            pages.setdefault(current, []).append(block)
        return [(n, 'docx_rendered_page', blocks) for n, blocks in sorted(pages.items())]
    groups: list[list[DocxBlock]] = []
    for block in doc.blocks:
        if not groups or block.kind == 'heading' or len(groups[-1]) >= ANCHOR_PAGE_BLOCKS:
            groups.append([])
        groups[-1].append(block)
    return [(i + 1, 'docx_anchor', blocks) for i, blocks in enumerate(groups)]


class DocxExtractStage:
    name = 'extract'

    def units(self, ctx: JobContext) -> list[Unit]:
        if ctx.source_mime != DOCX:
            return []
        if 'docx_renderer' not in ctx.state:
            ctx.state['docx_renderer'] = renderer_version() or 'none'
        digest = hashlib.sha256(f"{ctx.source_sha256}|{PARSER_VERSION}|"
                                f"{ctx.state['docx_renderer']}".encode()).hexdigest()
        return [Unit('doc', digest)]

    def compute(self, ctx: JobContext, unit: Unit) -> DocxDocument:
        work = Path(tempfile.mkdtemp(prefix='bazi-docx-'))
        source = work / 'source.docx'          # LibreOffice picks its filter by extension
        shutil.copyfile(local_source(ctx), source)
        try:
            doc = extract(source, work)
        except DocxRejected as exc:
            shutil.rmtree(work, ignore_errors=True)
            raise UnitFailed(exc.code, str(exc)) from None
        doc.extra['work_dir'] = str(work)
        return doc

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, doc: DocxDocument) -> dict:
        try:
            rendered_id = None
            if doc.rendered_pdf is not None:
                with open(doc.rendered_pdf, 'rb') as rendered:
                    rendered_id = store_object(conn, ctx.store, rendered, 'application/pdf')['id']
            pages = []
            for number, kind, blocks in _pages(doc):
                page_id, revision_id = self._page(conn, ctx, number, kind, blocks, doc, rendered_id)
                pages.append({'page_id': str(page_id), 'page_revision_id': str(revision_id)})
            located_ratio = (doc.located / len(doc.blocks)) if doc.blocks else 1.0
            review = None
            if doc.rendered_pdf is None:
                review = 'DOCX_RENDER_FAILED'
            elif located_ratio < MIN_LOCATED_RATIO:
                review = 'DOCX_LOCATE_PARTIAL'
            output = {'mode': 'rendered' if rendered_id else 'anchor', 'pages': pages,
                      'rendered_object_id': str(rendered_id) if rendered_id else None,
                      'render_error': doc.render_error, 'located_ratio': round(located_ratio, 3),
                      'review': review}
            self.attach(conn, ctx, unit, output)
            return output
        finally:
            shutil.rmtree(doc.extra.get('work_dir', ''), ignore_errors=True)

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        linked = 0
        for page in output['pages']:
            linked += conn.execute(text(
                'INSERT INTO generation_pages (generation_id, page_revision_id, page_id)'
                ' VALUES (:g, :r, :p) ON CONFLICT (generation_id, page_id) DO NOTHING'),
                {'g': ctx.generation_id, 'p': page['page_id'],
                 'r': effective_revision(conn, page['page_id'], page['page_revision_id'])}).rowcount
        if not linked:
            return
        total = len(output['pages'])
        conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                          ' WHERE id = :g'),
                     {'g': ctx.generation_id, 'c': json.dumps({
                         'total': total, 'parser_version': PARSER_VERSION,
                         'docx_mode': output['mode'], 'located_ratio': output['located_ratio']})})
        conn.execute(text('UPDATE ingestion_jobs SET counters = counters || CAST(:c AS jsonb)'
                          ' WHERE id = :j'),
                     {'j': ctx.job_id, 'c': json.dumps({'pages_total': total,
                                                        'pages_processed': total,
                                                        'pages_accepted': total})})
        if output['review']:
            first = output['pages'][0]['page_revision_id'] if output['pages'] else None
            conn.execute(text(
                'INSERT INTO review_items (generation_id, page_revision_id, reason_code, severity,'
                " resolution) VALUES (:g, :r, :c, 'low', CAST(:d AS jsonb))"),
                {'g': ctx.generation_id, 'r': first, 'c': output['review'],
                 'd': json.dumps({'render_error': output['render_error'],
                                  'located_ratio': output['located_ratio']})})

    def _page(self, conn: Connection, ctx: JobContext, number: int, kind: str,
              blocks: list[DocxBlock], doc: DocxDocument, rendered_id):
        anchor = {'from': blocks[0].anchor, 'to': blocks[-1].anchor}
        page_id = conn.execute(text(
            'INSERT INTO pages (book_version_id, physical_page_number, page_kind, source_anchor)'
            ' VALUES (:v, :n, :k, CAST(:a AS jsonb)) ON CONFLICT (book_version_id,'
            ' physical_page_number, page_kind) DO NOTHING RETURNING id'),
            {'v': ctx.book_version_id, 'n': number, 'k': kind, 'a': json.dumps(anchor)}).scalar()
        if page_id is None:
            page_id = conn.execute(text(
                'SELECT id FROM pages WHERE book_version_id = :v AND physical_page_number = :n'
                ' AND page_kind = :k'), {'v': ctx.book_version_id, 'n': number, 'k': kind}).scalar_one()
        offsets, parts, position = [], [], 0
        for block in blocks:
            offsets.append((position, position + len(block.text)))
            parts.append(block.text)
            position += len(block.text) + 2
        normalized = '\n\n'.join(parts)
        text_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        same = conn.execute(text(
            "SELECT id FROM page_revisions WHERE page_id = :p AND text_hash = :h"
            " AND layout->>'parser_version' = :parser AND NOT (quality ? 'correction')"
            ' ORDER BY revision_no LIMIT 1'),
            {'p': page_id, 'h': text_hash, 'parser': PARSER_VERSION}).scalar()
        if same:
            return page_id, same
        latest = conn.execute(text(
            'SELECT id, revision_no FROM page_revisions WHERE page_id = :p'
            ' ORDER BY revision_no DESC LIMIT 1'), {'p': page_id}).mappings().first()
        layout = {'parser_version': PARSER_VERSION, 'renderer': doc.renderer,
                  'rendered_pages': doc.rendered_pages, 'render_error': doc.render_error,
                  'page_kind': kind}
        revision_id = conn.execute(text(
            'INSERT INTO page_revisions (page_id, revision_no, base_revision_id, raw_text,'
            ' normalized_text, offset_map, layout, text_hash, quality, state, rendered_object_id)'
            " VALUES (:p, :no, :base, :raw, :norm, CAST(:map AS jsonb), CAST(:layout AS jsonb),"
            " :hash, CAST(:quality AS jsonb), 'accepted', :rendered) RETURNING id"),
            {'p': page_id, 'no': (latest['revision_no'] + 1) if latest else 1,
             'base': latest['id'] if latest else None, 'raw': normalized, 'norm': normalized,
             'map': json.dumps([[s, e, b.anchor] for (s, e), b in zip(offsets, blocks)]),
             'layout': json.dumps(layout), 'hash': text_hash,
             'quality': json.dumps({'page_class': 'docx', 'needs_ocr': False,
                                    'located': sum(1 for b in blocks if b.page is not None),
                                    'blocks': len(blocks)}),
             'rendered': rendered_id}).scalar_one()
        for ordinal, ((start, end), block) in enumerate(zip(offsets, blocks)):
            conn.execute(text(
                'INSERT INTO blocks (page_revision_id, ordinal, kind, bbox, start_offset, end_offset,'
                " text, table_cells, speaker_layer, attributes) VALUES (:r, :o, :k,"
                " CAST(:b AS jsonb), :s, :e, :t, CAST(:cells AS jsonb), :sp,"
                ' CAST(:a AS jsonb))'),
                {'r': revision_id, 'o': ordinal, 'k': block.kind,
                 'b': json.dumps(block.bbox), 's': start, 'e': end, 't': block.text,
                 'cells': json.dumps(block.table_cells) if block.table_cells is not None else None,
                 'sp': block.speaker,
                 'a': json.dumps({'anchor': block.anchor, 'style': block.style,
                                  'located': block.located or False,
                                  **({'marker': block.marker} if block.marker else {}),
                                  **({'level': 1 if (block.style or '').lower().startswith(
                                      ('title', 'heading1')) else 2}
                                     if block.kind == 'heading' else {})})})
        return page_id, revision_id
