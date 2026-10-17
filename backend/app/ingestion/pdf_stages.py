"""PDF stages for the job runner: ``validate`` (whole document) and ``extract`` (per page).

Extraction writes immutable page revisions + blocks and selects them for the
generation. A rerun with the same parser and identical text reuses the latest
revision instead of creating a duplicate.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import tempfile

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..documents.corrections import effective_revision
from ..documents.formats import PDF
from .pdf_native import (PARSER_VERSION, PageExtraction, PdfRejected, document_profile,
                         extract_page, open_document)
from .worker import JobContext, Unit, UnitFailed

CACHE_DIR = Path(tempfile.gettempdir()) / 'bazi-source-cache'


def _sha(*parts) -> str:
    return hashlib.sha256('|'.join(str(p) for p in parts).encode()).hexdigest()


def local_source(ctx: JobContext) -> str:
    """Worker-local copy of the source, verified against its content address."""
    if 'source_path' in ctx.state:
        return ctx.state['source_path']
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / ctx.source_sha256
    if not path.is_file():
        digest = hashlib.sha256()
        fd, tmp = tempfile.mkstemp(dir=CACHE_DIR)
        with os.fdopen(fd, 'wb') as out:
            for chunk in ctx.store.get_stream(ctx.source_key):
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != ctx.source_sha256:
            os.unlink(tmp)
            raise UnitFailed('SOURCE_CHECKSUM_MISMATCH', 'Stored source does not match its hash')
        os.replace(tmp, path)
    ctx.state['source_path'] = str(path)
    return str(path)


def _document(ctx: JobContext):
    if 'pdf' not in ctx.state:
        try:
            ctx.state['pdf'] = open_document(local_source(ctx))
        except PdfRejected as exc:
            raise UnitFailed(exc.code, str(exc)) from None
    return ctx.state['pdf']


class ValidatePdfStage:
    name = 'validate'

    def units(self, ctx: JobContext) -> list[Unit]:
        if ctx.source_mime != PDF:
            return []
        return [Unit('doc', _sha(ctx.source_sha256, PARSER_VERSION))]

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        doc = _document(ctx)
        return {'page_count': len(doc), 'parser_version': PARSER_VERSION,
                'profile': document_profile(doc)}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        self.attach(conn, ctx, unit, result)
        return result

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> None:
        conn.execute(text(
            'UPDATE generations SET coverage = coverage || CAST(:c AS jsonb) WHERE id = :g'),
            {'g': ctx.generation_id, 'c': json.dumps({'total': result['page_count'],
                                                     'parser_version': PARSER_VERSION,
                                                     'doc_profile': result.get('profile', {})})})
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || CAST(:c AS jsonb) WHERE id = :j'),
            {'j': ctx.job_id, 'c': json.dumps({'pages_total': result['page_count']})})


class ExtractPdfStage:
    name = 'extract'

    def units(self, ctx: JobContext) -> list[Unit]:
        if ctx.source_mime != PDF:
            return []
        with ctx.engine.connect() as conn:
            total = conn.execute(text("SELECT (coverage->>'total')::int FROM generations"
                                      ' WHERE id = :g'), {'g': ctx.generation_id}).scalar()
        if total is None:
            raise UnitFailed('VALIDATE_MISSING', 'validate stage did not record a page count')
        with ctx.engine.connect() as conn:
            ctx.state['doc_profile'] = conn.execute(text(
                "SELECT coverage->'doc_profile' FROM generations WHERE id = :g"),
                {'g': ctx.generation_id}).scalar() or {}
        return [Unit(f'page:{n}', _sha(ctx.source_sha256, n, PARSER_VERSION))
                for n in range(1, total + 1)]

    def compute(self, ctx: JobContext, unit: Unit) -> PageExtraction:
        number = int(unit.key.split(':', 1)[1])
        return extract_page(_document(ctx), number - 1, ctx.state.get('doc_profile'))

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit,
                page: PageExtraction) -> dict:
        page_id = conn.execute(text(
            'INSERT INTO pages (book_version_id, physical_page_number, page_kind)'
            " VALUES (:v, :n, 'pdf_page') ON CONFLICT (book_version_id, physical_page_number,"
            ' page_kind) DO NOTHING RETURNING id'),
            {'v': ctx.book_version_id, 'n': page.number}).scalar()
        if page_id is None:
            page_id = conn.execute(text(
                "SELECT id FROM pages WHERE book_version_id = :v AND physical_page_number = :n"
                " AND page_kind = 'pdf_page'"), {'v': ctx.book_version_id, 'n': page.number}).scalar_one()
        revision_id, created = self._revision(conn, page_id, page)
        output = {'page_id': str(page_id), 'page_revision_id': str(revision_id),
                  'created_revision': created, 'page_class': page.page_class,
                  'state': page.quality_state, 'needs_ocr': page.needs_ocr}
        self.attach(conn, ctx, unit, output)
        return output

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        revision = effective_revision(conn, output['page_id'], output['page_revision_id'])
        linked = conn.execute(text(
            'INSERT INTO generation_pages (generation_id, page_revision_id, page_id)'
            ' VALUES (:g, :r, :p) ON CONFLICT (generation_id, page_id) DO NOTHING RETURNING id'),
            {'g': ctx.generation_id, 'r': revision, 'p': output['page_id']}).first()
        if linked is None:
            return  # already linked (retry job of this generation): counters already done
        state = output['state']
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || jsonb_build_object('
            " 'pages_processed', coalesce((counters->>'pages_processed')::int, 0) + 1,"
            " 'pages_accepted', coalesce((counters->>'pages_accepted')::int, 0) + :acc,"
            " 'pages_review_required', coalesce((counters->>'pages_review_required')::int, 0) + :rev,"
            " 'pages_needing_ocr', coalesce((counters->>'pages_needing_ocr')::int, 0) + :ocr)"
            ' WHERE id = :j'),
            {'j': ctx.job_id, 'acc': int(state == 'accepted'), 'rev': int(state != 'accepted'),
             'ocr': int(output['needs_ocr'])})

    def _revision(self, conn: Connection, page_id, page: PageExtraction):
        text_hash = hashlib.sha256(page.normalized_text.encode('utf-8')).hexdigest()
        # Any earlier extraction of the same text by this parser is the same revision
        # (corrections and OCR merges stacked on it are not extractions).
        same = conn.execute(text(
            "SELECT id FROM page_revisions WHERE page_id = :p AND text_hash = :h"
            " AND layout->>'parser_version' = :parser AND NOT (quality ? 'correction')"
            " AND NOT (quality ? 'ocr') ORDER BY revision_no LIMIT 1"),
            {'p': page_id, 'h': text_hash, 'parser': PARSER_VERSION}).scalar()
        if same:
            return same, False
        latest = conn.execute(text(
            'SELECT id, revision_no FROM page_revisions WHERE page_id = :p'
            ' ORDER BY revision_no DESC LIMIT 1'), {'p': page_id}).mappings().first()
        layout = {'width': page.width, 'height': page.height, 'rotation': page.rotation,
                  'page_class': page.page_class, 'image_area': page.image_area,
                  'image_boxes': page.image_boxes, 'char_count': page.char_count,
                  'fonts': page.fonts, 'parser_version': PARSER_VERSION}
        quality = {'page_class': page.page_class, 'needs_ocr': page.needs_ocr,
                   'replacement_chars': page.replacement_chars,
                   'printed_label_source': page.printed_label_source}
        revision_id = conn.execute(text(
            'INSERT INTO page_revisions (page_id, revision_no, base_revision_id, raw_text,'
            ' normalized_text, offset_map, layout, printed_page_label, text_hash, quality, state)'
            ' VALUES (:p, :no, :base, :raw, :norm, CAST(:map AS jsonb), CAST(:layout AS jsonb),'
            ' :label, :hash, CAST(:quality AS jsonb), :state) RETURNING id'),
            {'p': page_id, 'no': (latest['revision_no'] + 1) if latest else 1,
             'base': latest['id'] if latest else None, 'raw': page.raw_text,
             'norm': page.normalized_text,
             'map': json.dumps([[b.start, b.end, b.ordinal] for b in page.blocks]),
             'layout': json.dumps(layout), 'label': page.printed_label, 'hash': text_hash,
             'quality': json.dumps(quality), 'state': page.quality_state}).scalar_one()
        for block in page.blocks:
            conn.execute(text(
                'INSERT INTO blocks (page_revision_id, ordinal, kind, bbox, start_offset,'
                " end_offset, text, speaker_layer, attributes) VALUES (:r, :o, :k,"
                " CAST(:bbox AS jsonb), :s, :e, :t, :sp, CAST(:attrs AS jsonb))"),
                {'r': revision_id, 'o': block.ordinal, 'k': block.kind,
                 'bbox': json.dumps(block.bbox), 's': block.start, 'e': block.end,
                 't': block.text, 'sp': block.speaker, 'attrs': json.dumps(block.attributes)})
        return revision_id, True


def page_summary(page: PageExtraction) -> dict:
    """JSON-safe view for tooling/tests."""
    data = asdict(page)
    data.pop('raw_text')
    return data
