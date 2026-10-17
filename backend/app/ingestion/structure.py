"""``structure`` stage: section tree from headings, printed-label verification (docs/05).

``build_sections`` is a pure function of the generation's blocks in reading
order, so the chunker can re-derive which section a block belongs to without
storing a block→section table. Sections get paths like ``0003.0002`` (ordinal
per parent, zero-padded so paths sort in document order).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

from .worker import JobContext, Unit

STRUCTURE_VERSION = 'structure-1'
PREAMBLE = '(Phần mở đầu)'
_NUMERIC = re.compile(r'^\d{1,4}$')


@dataclass(frozen=True)
class BlockRef:
    block_id: str
    page_number: int
    page_kind: str
    ordinal: int
    kind: str
    role: str | None
    level: int | None
    text: str


@dataclass
class SectionSpec:
    path: str
    parent_path: str | None
    title: str
    ordinal: int
    level: int
    heading_block_id: str | None


def generation_blocks(conn: Connection, generation_id) -> list[BlockRef]:
    rows = conn.execute(text(
        "SELECT b.id, p.physical_page_number, p.page_kind, b.ordinal, b.kind,"
        " b.attributes->>'role' AS role, (b.attributes->>'level')::int AS level, b.text"
        ' FROM generation_pages gp JOIN pages p ON p.id = gp.page_id'
        ' JOIN blocks b ON b.page_revision_id = gp.page_revision_id'
        ' WHERE gp.generation_id = :g ORDER BY p.page_kind, p.physical_page_number, b.ordinal'),
        {'g': generation_id}).all()
    return [BlockRef(str(r[0]), r[1], r[2], r[3], r[4], r[5], r[6], r[7]) for r in rows]


def build_sections(blocks: list[BlockRef]) -> tuple[list[SectionSpec], dict[str, str]]:
    """Sections plus a map block_id → section path, in reading order."""
    sections: list[SectionSpec] = []
    assignment: dict[str, str] = {}
    stack: list[SectionSpec] = []
    children: Counter = Counter()
    current: SectionSpec | None = None
    for block in blocks:
        if block.role:          # headers, footers, folios, TOC lines belong to no section
            continue
        if block.kind == 'heading':
            level = block.level or 2
            while stack and stack[-1].level >= level:
                stack.pop()
            parent = stack[-1] if stack else None
            parent_key = parent.path if parent else ''
            children[parent_key] += 1
            path = (f'{parent.path}.' if parent else '') + f'{children[parent_key]:04d}'
            current = SectionSpec(path, parent.path if parent else None,
                                  ' '.join(block.text.split())[:300], children[parent_key],
                                  level, block.block_id)
            sections.append(current)
            stack.append(current)
        elif current is None:
            current = SectionSpec('0000', None, PREAMBLE, 0, 0, None)
            sections.insert(0, current)
        assignment[block.block_id] = current.path
    return sections, assignment


def label_check(pages: list[tuple[str, int, str | None]]) -> tuple[set[str], set[str], int | None]:
    """(verified revision ids, mismatched revision ids, dominant offset) for numeric labels."""
    numeric = [(rid, n, int(label)) for rid, n, label in pages if label and _NUMERIC.match(label)]
    if len(numeric) < 3:
        return set(), set(), None
    offsets = Counter(label - n for _, n, label in numeric)
    offset, count = offsets.most_common(1)[0]
    if count / len(numeric) < 0.6:
        return set(), set(), None   # no consistent folio scheme: leave labels unverified
    verified = {rid for rid, n, label in numeric if label - n == offset}
    return verified, {rid for rid, _, _ in numeric} - verified, offset


class StructureStage:
    name = 'structure'

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            ids = conn.execute(text(
                'SELECT page_revision_id FROM generation_pages WHERE generation_id = :g'
                ' ORDER BY page_id'), {'g': ctx.generation_id}).scalars().all()
        if not ids:
            return []
        digest = hashlib.sha256(('|'.join(map(str, ids)) + STRUCTURE_VERSION).encode()).hexdigest()
        return [Unit('doc', digest)]

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        with ctx.engine.connect() as conn:
            blocks = generation_blocks(conn, ctx.generation_id)
            labels = conn.execute(text(
                'SELECT r.id, p.physical_page_number, r.printed_page_label FROM generation_pages gp'
                ' JOIN pages p ON p.id = gp.page_id JOIN page_revisions r'
                " ON r.id = gp.page_revision_id WHERE gp.generation_id = :g"
                " AND p.page_kind = 'pdf_page'"), {'g': ctx.generation_id}).all()
        sections, _ = build_sections(blocks)
        verified, mismatched, offset = label_check([(str(r[0]), r[1], r[2]) for r in labels])
        return {'sections': [vars(s) for s in sections], 'verified': sorted(verified),
                'mismatched': sorted(mismatched), 'label_offset': offset}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        if result['verified']:
            conn.execute(text('UPDATE page_revisions SET printed_label_verified = true'
                              ' WHERE id = ANY(CAST(:ids AS uuid[]))'), {'ids': result['verified']})
        self.attach(conn, ctx, unit, result)
        return result

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> None:
        ids: dict[str, str] = {}
        for spec in result['sections']:   # parents come before children
            ids[spec['path']] = conn.execute(text(
                'INSERT INTO sections (generation_id, parent_id, title, path, ordinal,'
                " speaker_layer) VALUES (:g, :parent, :title, :path, :ordinal, 'unknown')"
                ' ON CONFLICT (generation_id, path) DO UPDATE SET path = EXCLUDED.path'
                ' RETURNING id'),
                {'g': ctx.generation_id, 'parent': ids.get(spec['parent_path']),
                 'title': spec['title'], 'path': spec['path'], 'ordinal': spec['ordinal']}).scalar_one()
        for revision_id in result['mismatched']:
            if not conn.execute(text(
                    "SELECT 1 FROM review_items WHERE generation_id = :g AND page_revision_id = :r"
                    " AND reason_code = 'PRINTED_LABEL_MISMATCH'"),
                    {'g': ctx.generation_id, 'r': revision_id}).first():
                conn.execute(text(
                    'INSERT INTO review_items (generation_id, page_revision_id, reason_code,'
                    " severity, resolution) VALUES (:g, :r, 'PRINTED_LABEL_MISMATCH', 'low',"
                    ' CAST(:d AS jsonb))'),
                    {'g': ctx.generation_id, 'r': revision_id,
                     'd': json.dumps({'expected_offset': result['label_offset']})})
        conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                          ' WHERE id = :g'),
                     {'g': ctx.generation_id, 'c': json.dumps({
                         'sections': len(result['sections']),
                         'printed_labels_verified': len(result['verified']),
                         'printed_label_offset': result['label_offset']})})
