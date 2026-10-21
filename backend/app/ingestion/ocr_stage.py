"""``ocr`` stage: OCR flagged pages/regions with SenOCR-Vi and publish a new revision.

Outcome per page:
* whole ``scan`` page with text found → new revision made of the OCR blocks only
  (a scan's own text layer, when it has one, is sparse and garbled; the native
  revision stays as history and any evidence on it stays valid);
* image regions of a text page → native blocks unchanged + OCR blocks appended;
* nothing recognised, engine missing, or the page cannot be rendered → the native
  revision stays linked and a review item explains why.
A page never fails the job (docs/05: OCR problems go to review).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .ocr import (DPI_STEPS, MIN_REGION_AREA, OcrBlock, OcrOutOfMemory, OcrTimeout,
                  OcrUnavailable, new_ocr_blocks, ocr_page, shared_engine)
from .pdf_stages import _document
from .worker import JobContext, RetryableError, Unit

OCR_VERSION = 'ocr-senocr-1'
REPLACEMENT = '�'


@dataclass
class OcrOutcome:
    status: str                       # ok | timeout | unavailable | empty
    page_number: int
    native_revision_id: str
    blocks: list[OcrBlock] = field(default_factory=list)
    dpi: int | None = None
    engine: str | None = None
    mode: str = 'page'                # page | regions
    detail: str | None = None


def _region_area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


class OcrStage:
    name = 'ocr'

    def __init__(self, settings=None, engine_factory=shared_engine):
        self.settings = settings
        self.engine_factory = engine_factory

    def _engine(self, ctx: JobContext):
        if 'ocr_engine' not in ctx.state:
            try:
                ctx.state['ocr_engine'] = self.engine_factory()
            except OcrUnavailable:
                ctx.state['ocr_engine'] = None
        return ctx.state['ocr_engine']

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT p.physical_page_number AS n, r.id, r.text_hash,"
                " (r.quality->>'needs_ocr')::boolean AS needs_ocr, r.quality->>'page_class' AS cls,"
                " r.layout->'image_boxes' AS boxes,"
                # OCR output, human corrections and excluded pages need no (more) OCR.
                " (r.quality ? 'ocr' OR r.quality ? 'correction' OR r.state = 'excluded') AS settled"
                ' FROM generation_pages gp'
                ' JOIN pages p ON p.id = gp.page_id JOIN page_revisions r ON r.id = gp.page_revision_id'
                " WHERE gp.generation_id = :g AND p.page_kind = 'pdf_page'"
                ' ORDER BY p.physical_page_number'), {'g': ctx.generation_id}).mappings().all()
        engine = self._engine(ctx)
        version = engine.version if engine else 'none'
        units = []
        for row in rows:
            boxes = [b for b in (row['boxes'] or []) if _region_area(b) >= MIN_REGION_AREA]
            if row['settled'] or not (row['needs_ocr'] or boxes):
                continue
            digest = hashlib.sha256(json.dumps(
                [row['text_hash'].strip(), boxes, DPI_STEPS, version, OCR_VERSION]).encode()).hexdigest()
            units.append(Unit(f"page:{row['n']}", digest))
        return units

    def _native(self, ctx: JobContext, number: int) -> dict:
        with ctx.engine.connect() as conn:
            revision = conn.execute(text(
                "SELECT r.id, r.quality->>'page_class' AS cls, r.layout->'image_boxes' AS boxes"
                ' FROM generation_pages gp JOIN pages p ON p.id = gp.page_id'
                ' JOIN page_revisions r ON r.id = gp.page_revision_id'
                " WHERE gp.generation_id = :g AND p.physical_page_number = :n"
                " AND p.page_kind = 'pdf_page'"), {'g': ctx.generation_id, 'n': number}).mappings().one()
            boxes = [list(b) for (b,) in conn.execute(text(
                'SELECT bbox FROM blocks WHERE page_revision_id = :r'), {'r': revision['id']})]
        return {**revision, 'native_boxes': boxes}

    def compute(self, ctx: JobContext, unit: Unit) -> OcrOutcome:
        number = int(unit.key.split(':', 1)[1])
        native = self._native(ctx, number)
        whole_page = native['cls'] == 'scan'
        regions = None if whole_page else [b for b in (native['boxes'] or [])
                                           if _region_area(b) >= MIN_REGION_AREA]
        outcome = OcrOutcome('empty', number, str(native['id']),
                             mode='page' if whole_page else 'regions')
        engine = self._engine(ctx)
        if engine is None:
            outcome.status = 'unavailable'
            return outcome
        try:
            blocks, dpi = ocr_page(_document(ctx), number - 1, regions, engine)
        except OcrTimeout as exc:
            outcome.status, outcome.detail = 'timeout', str(exc)[:200]
            return outcome
        except OcrUnavailable as exc:
            outcome.status, outcome.detail = 'unavailable', str(exc)[:200]
            return outcome
        except OcrOutOfMemory as exc:
            # The GPU is shared; memory frees up. Retry the page later instead of
            # settling it as "no OCR" (the unit retries with jitter, up to 5 times).
            raise RetryableError('OCR_OUT_OF_MEMORY', str(exc)) from None
        if not whole_page:
            blocks = new_ocr_blocks(blocks, [b for b in native['native_boxes'] if b])
        outcome.dpi, outcome.engine = dpi, engine.version
        # Any recognised text counts: a scanned chapter title page ("CHƯƠNG 3") is short but
        # carries the heading the section tree needs; only an empty result goes to review.
        if any(b.text.strip() for b in blocks if not b.role):
            outcome.status, outcome.blocks = 'ok', blocks
        return outcome

    # ---- persistence -------------------------------------------------------------
    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: OcrOutcome) -> dict:
        page_id = conn.execute(text('SELECT page_id FROM page_revisions WHERE id = :r'),
                               {'r': result.native_revision_id}).scalar_one()
        output = {'status': result.status, 'page_id': str(page_id),
                  'page_revision_id': result.native_revision_id, 'review': None}
        if result.status == 'ok':
            revision_id, garbled = self._new_revision(conn, page_id, result)
            output['page_revision_id'] = str(revision_id)
            if garbled:
                output['review'] = 'OCR_GARBLED'
        else:
            output['review'] = {'timeout': 'OCR_TIMEOUT', 'unavailable': 'OCR_UNAVAILABLE',
                                'empty': 'OCR_EMPTY'}[result.status]
        output['detail'] = result.detail
        self.attach(conn, ctx, unit, output)
        return output

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        current = conn.execute(text(
            'SELECT page_revision_id FROM generation_pages WHERE generation_id = :g'
            ' AND page_id = :p'), {'g': ctx.generation_id, 'p': output['page_id']}).scalar()
        if current is not None and str(current) != output['page_revision_id']:
            # generation_pages rows are immutable: swap the link while still building.
            conn.execute(text('DELETE FROM generation_pages WHERE generation_id = :g'
                              ' AND page_id = :p'), {'g': ctx.generation_id, 'p': output['page_id']})
            conn.execute(text('INSERT INTO generation_pages (generation_id, page_revision_id,'
                              ' page_id) VALUES (:g, :r, :p)'),
                         {'g': ctx.generation_id, 'r': output['page_revision_id'],
                          'p': output['page_id']})
        if output['review'] and not conn.execute(text(
                'SELECT 1 FROM review_items WHERE generation_id = :g AND page_revision_id = :r'
                ' AND reason_code = :c'), {'g': ctx.generation_id, 'r': output['page_revision_id'],
                                           'c': output['review']}).first():
            conn.execute(text(
                'INSERT INTO review_items (generation_id, page_revision_id, reason_code, severity,'
                " resolution) VALUES (:g, :r, :c, 'medium', CAST(:detail AS jsonb))"),
                {'g': ctx.generation_id, 'r': output['page_revision_id'], 'c': output['review'],
                 'detail': json.dumps({'ocr_status': output['status'],
                                       'detail': output.get('detail')})})
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || jsonb_build_object('
            " 'pages_ocr_text', coalesce((counters->>'pages_ocr_text')::int, 0) + :ok,"
            " 'pages_ocr_review', coalesce((counters->>'pages_ocr_review')::int, 0) + :rev)"
            ' WHERE id = :j'),
            {'j': ctx.job_id, 'ok': int(output['status'] == 'ok'), 'rev': int(bool(output['review']))})

    def _new_revision(self, conn: Connection, page_id, result: OcrOutcome):
        native = conn.execute(text(
            'SELECT id, revision_no, raw_text, normalized_text, offset_map, layout, quality,'
            ' printed_page_label FROM page_revisions WHERE id = :r'),
            {'r': result.native_revision_id}).mappings().one()
        whole_page = result.mode == 'page'
        native_blocks = [] if whole_page else conn.execute(text(
            'SELECT ordinal, kind, bbox, start_offset, end_offset, text, table_cells,'
            ' speaker_layer, attributes FROM blocks WHERE page_revision_id = :r ORDER BY ordinal'),
            {'r': native['id']}).mappings().all()
        merged = '' if whole_page else native['normalized_text']
        ocr_rows = []
        next_ordinal = (native_blocks[-1]['ordinal'] + 1) if native_blocks else 0
        for i, block in enumerate(result.blocks):
            merged += '\n\n' if merged else ''
            start = len(merged)
            merged += block.text
            ocr_rows.append((next_ordinal + i, block, start, len(merged)))
        text_hash = hashlib.sha256(merged.encode('utf-8')).hexdigest()
        body = ''.join(b.text for b in result.blocks if not b.role)
        garbled = bool(body) and body.count(REPLACEMENT) / len(body) > 0.01
        existing = conn.execute(text(
            'SELECT id FROM page_revisions WHERE page_id = :p AND text_hash = :h'
            " AND base_revision_id = :base AND quality->'ocr'->>'version' = :v"),
            {'p': page_id, 'h': text_hash, 'base': native['id'], 'v': OCR_VERSION}).scalar()
        if existing:
            return existing, garbled
        quality = {**native['quality'], 'needs_ocr': False,
                   'ocr': {'version': OCR_VERSION, 'engine': result.engine, 'dpi': result.dpi,
                           'mode': result.mode, 'blocks': len(result.blocks),
                           'labels': sorted({b.label for b in result.blocks})}}
        if whole_page:
            quality['page_class'] = 'scan'
        latest_no = conn.execute(text('SELECT max(revision_no) FROM page_revisions WHERE page_id = :p'),
                                 {'p': page_id}).scalar_one()
        offset_map = ([] if whole_page else list(native['offset_map'])) + \
            [[s, e, o] for o, _, s, e in ocr_rows]
        revision_id = conn.execute(text(
            'INSERT INTO page_revisions (page_id, revision_no, base_revision_id, raw_text,'
            ' normalized_text, offset_map, layout, printed_page_label, text_hash, quality, state)'
            ' VALUES (:p, :no, :base, :raw, :norm, CAST(:map AS jsonb), CAST(:layout AS jsonb),'
            ' :label, :hash, CAST(:quality AS jsonb), :state) RETURNING id'),
            {'p': page_id, 'no': latest_no + 1, 'base': native['id'],
             'raw': merged if whole_page else native['raw_text'], 'norm': merged,
             'map': json.dumps(offset_map), 'layout': json.dumps(native['layout']),
             'label': native['printed_page_label'], 'hash': text_hash,
             'quality': json.dumps(quality),
             'state': 'review_required' if garbled else 'accepted'}).scalar_one()
        insert = text(
            'INSERT INTO blocks (page_revision_id, ordinal, kind, bbox, start_offset, end_offset,'
            ' text, table_cells, speaker_layer, attributes) VALUES (:r, :o, :k, CAST(:b AS jsonb),'
            ' :s, :e, :t, CAST(:cells AS jsonb), :sp, CAST(:a AS jsonb))')
        for block in native_blocks:   # native text copied unchanged, same offsets
            conn.execute(insert, {'r': revision_id, 'o': block['ordinal'], 'k': block['kind'],
                                  'b': json.dumps(block['bbox']), 's': block['start_offset'],
                                  'e': block['end_offset'], 't': block['text'],
                                  'cells': json.dumps(block['table_cells'])
                                  if block['table_cells'] is not None else None,
                                  'sp': block['speaker_layer'],
                                  'a': json.dumps({**block['attributes'], 'origin': 'native'})})
        for ordinal, block, start, end in ocr_rows:
            attributes = {**block.attributes, 'origin': 'ocr', 'ocr_label': block.label,
                          'region': block.region, 'engine': result.engine}
            speaker = attributes.pop('speaker', 'unknown')
            if block.role:
                attributes['role'] = block.role
            if block.level is not None:
                attributes['level'] = block.level
            conn.execute(insert, {'r': revision_id, 'o': ordinal, 'k': block.kind,
                                  'b': json.dumps(block.bbox), 's': start, 'e': end,
                                  't': block.text,
                                  'cells': json.dumps(block.table_cells, ensure_ascii=False)
                                  if block.table_cells is not None else None,
                                  'sp': speaker, 'a': json.dumps(attributes, ensure_ascii=False)})
        return revision_id, garbled
