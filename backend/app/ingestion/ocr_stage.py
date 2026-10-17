"""``ocr`` stage: OCR flagged pages/regions and publish a merged revision.

Outcome per page:
* text found → new revision = native blocks unchanged + OCR blocks appended,
  linked to the generation in place of the native one; low confidence or a
  whole-page scan below the threshold also opens a review item;
* timeout (after one lower-DPI retry), engine missing, or nothing recognised →
  the native revision stays linked and a review item explains why.
A page never fails the job (docs/05: OCR timeout goes to review).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .ocr import (DEFAULT_LANGS, DPI_STEPS, MIN_REGION_AREA, OcrBlock, OcrTimeout, OcrUnavailable,
                  TesseractEngine, group_blocks, new_ocr_blocks, ocr_page)
from .pdf_stages import _document
from .worker import JobContext, Unit

OCR_VERSION = 'ocr-merge-1'
MIN_CONFIDENCE = 60.0


@dataclass
class OcrOutcome:
    status: str                       # ok | timeout | unavailable | empty
    page_number: int
    native_revision_id: str
    blocks: list[OcrBlock] = field(default_factory=list)
    mean_conf: float | None = None
    dpi: int | None = None
    engine: str | None = None
    mode: str = 'page'                # page | regions
    detail: str | None = None


def _region_area(box: list[float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


class OcrStage:
    name = 'ocr'

    def __init__(self, engine_factory=TesseractEngine, langs: str = DEFAULT_LANGS):
        self.engine_factory = engine_factory
        self.langs = langs

    def _engine(self, ctx: JobContext):
        if 'ocr_engine' not in ctx.state:
            try:
                ctx.state['ocr_engine'] = self.engine_factory()
            except OcrUnavailable:
                ctx.state['ocr_engine'] = None
        return ctx.state['ocr_engine']

    def _langs(self, ctx: JobContext) -> str:
        return (ctx.pipeline_config.get('ocr') or {}).get('languages') or self.langs

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT p.physical_page_number AS n, r.id, r.text_hash,"
                " (r.quality->>'needs_ocr')::boolean AS needs_ocr, r.quality->>'page_class' AS cls,"
                " r.layout->'image_boxes' AS boxes,"
                # OCR output and human corrections are final for this page's text.
                " (r.quality ? 'ocr' OR r.quality ? 'correction') AS settled FROM generation_pages gp"
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
                [row['text_hash'].strip(), boxes, self._langs(ctx), DPI_STEPS, version,
                 OCR_VERSION]).encode()).hexdigest()
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
            words, dpi = ocr_page(_document(ctx), number - 1, regions, engine, self._langs(ctx))
        except OcrTimeout as exc:
            outcome.status, outcome.detail = 'timeout', str(exc)[:200]
            return outcome
        except OcrUnavailable as exc:
            outcome.status, outcome.detail = 'unavailable', str(exc)[:200]
            return outcome
        blocks = new_ocr_blocks(group_blocks(words), native['native_boxes'])
        outcome.dpi, outcome.engine = dpi, engine.version
        if blocks:
            outcome.status, outcome.blocks = 'ok', blocks
            outcome.mean_conf = round(sum(b.conf for b in blocks) / len(blocks), 1)
        return outcome

    # ---- persistence -------------------------------------------------------------
    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: OcrOutcome) -> dict:
        page_id = conn.execute(text('SELECT page_id FROM page_revisions WHERE id = :r'),
                               {'r': result.native_revision_id}).scalar_one()
        output = {'status': result.status, 'page_id': str(page_id),
                  'page_revision_id': result.native_revision_id, 'review': None}
        if result.status == 'ok':
            output['page_revision_id'] = str(self._merged_revision(conn, page_id, result))
            low = result.mean_conf is not None and result.mean_conf < MIN_CONFIDENCE
            if low:
                output['review'] = 'OCR_LOW_CONFIDENCE'
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

    def _merged_revision(self, conn: Connection, page_id, result: OcrOutcome):
        native = conn.execute(text(
            'SELECT id, revision_no, raw_text, normalized_text, offset_map, layout, quality,'
            ' printed_page_label FROM page_revisions WHERE id = :r'),
            {'r': result.native_revision_id}).mappings().one()
        native_blocks = conn.execute(text(
            'SELECT ordinal, kind, bbox, start_offset, end_offset, text, table_cells,'
            ' speaker_layer, attributes FROM blocks WHERE page_revision_id = :r ORDER BY ordinal'),
            {'r': native['id']}).mappings().all()
        merged = native['normalized_text']
        ocr_rows = []
        next_ordinal = (native_blocks[-1]['ordinal'] + 1) if native_blocks else 0
        for i, block in enumerate(result.blocks):
            merged += '\n\n' if merged else ''
            start = len(merged)
            merged += block.text
            ocr_rows.append((next_ordinal + i, block, start, len(merged)))
        text_hash = hashlib.sha256(merged.encode('utf-8')).hexdigest()
        existing = conn.execute(text(
            'SELECT id FROM page_revisions WHERE page_id = :p AND text_hash = :h'
            " AND base_revision_id = :base AND quality->'ocr'->>'version' = :v"),
            {'p': page_id, 'h': text_hash, 'base': native['id'], 'v': OCR_VERSION}).scalar()
        if existing:
            return existing
        whole_page = result.mode == 'page'
        state = 'accepted' if (result.mean_conf or 0) >= MIN_CONFIDENCE else 'review_required'
        if not whole_page and native['quality'].get('replacement_chars'):
            state = 'review_required'
        quality = {**native['quality'], 'needs_ocr': False,
                   'ocr': {'version': OCR_VERSION, 'engine': result.engine, 'dpi': result.dpi,
                           'mode': result.mode, 'mean_conf': result.mean_conf,
                           'blocks': len(result.blocks)}}
        latest_no = conn.execute(text('SELECT max(revision_no) FROM page_revisions WHERE page_id = :p'),
                                 {'p': page_id}).scalar_one()
        offset_map = list(native['offset_map']) + [[s, e, o] for o, _, s, e in ocr_rows]
        revision_id = conn.execute(text(
            'INSERT INTO page_revisions (page_id, revision_no, base_revision_id, raw_text,'
            ' normalized_text, offset_map, layout, printed_page_label, text_hash, quality, state)'
            ' VALUES (:p, :no, :base, :raw, :norm, CAST(:map AS jsonb), CAST(:layout AS jsonb),'
            ' :label, :hash, CAST(:quality AS jsonb), :state) RETURNING id'),
            {'p': page_id, 'no': latest_no + 1, 'base': native['id'], 'raw': native['raw_text'],
             'norm': merged, 'map': json.dumps(offset_map), 'layout': json.dumps(native['layout']),
             'label': native['printed_page_label'], 'hash': text_hash,
             'quality': json.dumps(quality), 'state': state}).scalar_one()
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
            conn.execute(insert, {'r': revision_id, 'o': ordinal, 'k': 'paragraph',
                                  'b': json.dumps(block.bbox), 's': start, 'e': end,
                                  't': block.text, 'cells': None, 'sp': 'unknown',
                                  'a': json.dumps({'origin': 'ocr', 'conf': block.conf,
                                                   'region': block.region,
                                                   'engine': result.engine})})
        return revision_id
