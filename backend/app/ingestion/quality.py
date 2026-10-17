"""``quality`` stage: explainable page signals → review items with a reason (docs/05).

Signals are measured, not combined into a fake probability. Thresholds are
configuration (``pipeline_profiles.config.quality``) until T014's labelled
pages calibrate them; ``calibrate`` reports precision/recall per reason
against such labels.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .normalize import unmapped_glyph_rate
from .worker import JobContext, Unit

QUALITY_VERSION = 'quality-1'
DEFAULTS = {'unmapped_glyph_rate': 0.01, 'reading_order_jumps': 2, 'reading_order_jump': 0.3}
STEMS = {'giáp', 'ất', 'bính', 'đinh', 'mậu', 'kỷ', 'canh', 'tân', 'nhâm', 'quý'}
BRANCHES = {'tý', 'sửu', 'dần', 'mão', 'thìn', 'tỵ', 'tị', 'ngọ', 'mùi', 'thân', 'dậu', 'tuất', 'hợi'}
SEVERITY = {'REPLACEMENT_CHARS': 'high', 'UNMAPPED_GLYPHS': 'high', 'PILLAR_ROW_MISMATCH': 'medium',
            'HEADING_SPLIT': 'low', 'READING_ORDER': 'low'}
_WORD = re.compile(r'[^\W\d_]+', re.UNICODE)


def _tokens(line: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(line)]


def pillar_mismatch(text_: str) -> bool:
    """A stems row followed by a branches row of a different length (a 4-pillar table)."""
    lines = [line for line in text_.split('\n') if line.strip()]
    for upper, lower in zip(lines, lines[1:]):
        stems = [t for t in _tokens(upper) if t in STEMS]
        branches = [t for t in _tokens(lower) if t in BRANCHES]
        if len(stems) >= 3 and len(stems) == len(_tokens(upper)) and len(branches) >= 3 \
                and len(branches) == len(_tokens(lower)) and len(stems) != len(branches):
            return True
    return False


def page_signals(page: dict, blocks: list[dict], config: dict) -> list[str]:
    reasons = []
    body = [b for b in blocks if not b['role']]
    joined = '\n'.join(b['text'] for b in body)
    if '�' in joined:
        reasons.append('REPLACEMENT_CHARS')
    if unmapped_glyph_rate(joined) > config['unmapped_glyph_rate']:
        reasons.append('UNMAPPED_GLYPHS')
    if any(pillar_mismatch(b['text']) for b in body):
        reasons.append('PILLAR_ROW_MISMATCH')
    for first, second in zip(body, body[1:]):
        if first['kind'] == 'heading' and second['kind'] == 'heading' \
                and second['text'][:1].islower():
            reasons.append('HEADING_SPLIT')
            break
    boxes = [b['bbox'] for b in body if b['bbox']]
    jumps = sum(1 for a, b in zip(boxes, boxes[1:]) if a[1] - b[1] > config['reading_order_jump'])
    if jumps >= config['reading_order_jumps']:
        reasons.append('READING_ORDER')
    return reasons


def calibrate(predicted: dict[str, set[str]], labelled: dict[str, set[str]]) -> dict:
    """Per reason precision/recall over pages: ``{page: {reasons}}`` both sides."""
    report = {}
    reasons = {r for v in list(predicted.values()) + list(labelled.values()) for r in v}
    for reason in sorted(reasons):
        tp = sum(1 for p in labelled if reason in labelled[p] and reason in predicted.get(p, ()))
        fp = sum(1 for p in predicted if reason in predicted[p] and reason not in labelled.get(p, ()))
        fn = sum(1 for p in labelled if reason in labelled[p] and reason not in predicted.get(p, ()))
        report[reason] = {'precision': tp / (tp + fp) if tp + fp else None,
                          'recall': tp / (tp + fn) if tp + fn else None,
                          'tp': tp, 'fp': fp, 'fn': fn}
    return report


class QualityStage:
    name = 'quality'

    def _config(self, ctx: JobContext) -> dict:
        return {**DEFAULTS, **(ctx.pipeline_config.get('quality') or {})}

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            ids = conn.execute(text('SELECT page_revision_id FROM generation_pages'
                                    ' WHERE generation_id = :g ORDER BY page_id'),
                               {'g': ctx.generation_id}).scalars().all()
        if not ids:
            return []
        material = '|'.join(map(str, ids)) + QUALITY_VERSION + json.dumps(self._config(ctx),
                                                                          sort_keys=True)
        return [Unit('doc', hashlib.sha256(material.encode()).hexdigest())]

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        config = self._config(ctx)
        with ctx.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT r.id AS revision_id, p.physical_page_number AS n, b.kind,"
                " b.attributes->>'role' AS role, b.text, b.bbox, b.speaker_layer,"
                " b.attributes ? 'marker' AS marked FROM generation_pages gp"
                ' JOIN pages p ON p.id = gp.page_id JOIN page_revisions r'
                ' ON r.id = gp.page_revision_id JOIN blocks b ON b.page_revision_id = r.id'
                ' WHERE gp.generation_id = :g ORDER BY p.physical_page_number, b.ordinal'),
                {'g': ctx.generation_id}).mappings().all()
        pages: dict[str, list[dict]] = {}
        for row in rows:
            pages.setdefault(str(row['revision_id']), []).append(dict(row))
        findings = {rid: page_signals({}, blocks, config) for rid, blocks in pages.items()}
        # Author layers: if the book marks speakers at all, unmarked body text needs review.
        marked = sum(1 for r in rows if r['marked'])
        unknown_pages = sorted({r['n'] for r in rows if not r['role'] and r['kind'] != 'heading'
                                and r['speaker_layer'] == 'unknown'}) if marked else []
        return {'findings': {k: v for k, v in findings.items() if v}, 'marked_blocks': marked,
                'speaker_unknown_pages': unknown_pages}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        self.attach(conn, ctx, unit, result)
        return result

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> None:
        counts = Counter()
        for revision_id, reasons in result['findings'].items():
            for reason in reasons:
                counts[reason] += 1
                self._review(conn, ctx, revision_id, reason, SEVERITY[reason], {})
        if result['speaker_unknown_pages']:
            counts['SPEAKER_LAYERS_INCOMPLETE'] += 1
            self._review(conn, ctx, None, 'SPEAKER_LAYERS_INCOMPLETE', 'medium',
                         {'pages': result['speaker_unknown_pages'][:500],
                          'marked_blocks': result['marked_blocks']})
        conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                          ' WHERE id = :g'),
                     {'g': ctx.generation_id, 'c': json.dumps({'quality': dict(counts)})})

    def _review(self, conn, ctx, revision_id, reason, severity, detail) -> None:
        exists = conn.execute(text(
            'SELECT 1 FROM review_items WHERE generation_id = :g AND reason_code = :c'
            ' AND page_revision_id IS NOT DISTINCT FROM CAST(:r AS uuid)'),
            {'g': ctx.generation_id, 'c': reason, 'r': revision_id}).first()
        if not exists:
            conn.execute(text(
                'INSERT INTO review_items (generation_id, page_revision_id, reason_code, severity,'
                ' resolution) VALUES (:g, CAST(:r AS uuid), :c, :s, CAST(:d AS jsonb))'),
                {'g': ctx.generation_id, 'r': revision_id, 'c': reason, 's': severity,
                 'd': json.dumps(detail)})
