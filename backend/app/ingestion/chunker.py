"""``chunk`` stage: section- and speaker-aware chunks with exact provenance (docs/05, 07).

Rules:
* a chunk never crosses a section boundary or mixes speaker layers;
* pillar tables (consecutive ``chart_row`` blocks) and "Thí dụ / Ví dụ" case
  windows are atomic units — split only if a single unit exceeds the maximum;
* a block longer than the maximum is split at sentence ends;
* a sentence the PDF split over two blocks (it runs onto the next page, or a symbol or
  font change broke the paragraph) stays one unit: a block that ends without closing
  punctuation followed by one that starts in lower case are never cut apart;
* consecutive chunks of one section/speaker overlap by whole trailing pieces, starting at
  the beginning of a sentence;
* every piece of chunk text is a span ``[chunk_start, chunk_end)`` that equals
  ``normalized_text[start_offset:end_offset]`` of its page revision — a chunk on
  two pages has spans on both revisions;
* identical text with identical spans and quality reuses the existing chunk
  row, so a re-chunk only creates rows for what changed (stable identity, T017);
  a page accepted or excluded by review gets rows with the new quality.

Token counts use an approximate syllable tokenizer until the embedding model's
tokenizer is chosen (T016/T036); its name is part of the chunker version.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..knowledge import scopes
from .layout import CLOSED as _CLOSED, LOWER_START as _LOWER_START, continues
from .structure import BlockRef, build_sections
from .worker import JobContext, Unit

TOKENIZER = 'syllable-approx-1'
CHUNKER_VERSION = f'chunker-2/{TOKENIZER}'
DEFAULTS = {'target': 500, 'max': 700, 'overlap': 80}
SEPARATOR = '\n\n'
CASE_HEADING = re.compile(r'^\(?\s*(thí dụ|ví dụ|mệnh lệ|lệ)\b', re.IGNORECASE)
_SENTENCE = re.compile(r'(?<=[.!?…;:])\s+')

_TOKEN = re.compile(r'\w+|[^\w\s]', re.UNICODE)

TOPIC_KEYWORDS = {
    'van_han': ('đại vận', 'lưu niên', 'ứng kỳ', 'hành vận', 'tiểu vận'),
    'thap_than': ('thực thần', 'thương quan', 'chính quan', 'thất sát', 'chính tài', 'thiên tài',
                  'chính ấn', 'thiên ấn', 'kiêu thần', 'tỷ kiên', 'kiếp tài'),
    'ngu_hanh': ('ngũ hành', 'mộc', 'hỏa', 'thổ', 'kim', 'thủy', 'tương sinh', 'tương khắc'),
}


def count_tokens(text_: str) -> int:
    return len(_TOKEN.findall(text_))


@dataclass
class Piece:
    """A contiguous slice of one block (usually the whole block)."""
    block: dict
    start: int          # offset inside the block text
    end: int

    @property
    def text(self) -> str:
        return self.block['text'][self.start:self.end]

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)


@dataclass
class Group:
    """Atomic run of pieces: a paragraph, a whole pillar table, or a case window."""
    pieces: list[Piece]
    kind: str            # text | table | case

    @property
    def tokens(self) -> int:
        return sum(p.tokens for p in self.pieces)


@dataclass
class ChunkSpec:
    section_path: str
    speaker: str
    kind: str
    pieces: list[Piece] = field(default_factory=list)

    @property
    def text(self) -> str:
        return SEPARATOR.join(p.text for p in self.pieces)

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)


def _split_block(block: dict, maximum: int) -> list[Piece]:
    """Whole block, or sentence-bounded slices when it is longer than ``maximum``."""
    if count_tokens(block['text']) <= maximum:
        return [Piece(block, 0, len(block['text']))]
    pieces, start, position = [], 0, 0
    bounds = [m.end() for m in _SENTENCE.finditer(block['text'])] + [len(block['text'])]
    for bound in bounds:
        if count_tokens(block['text'][start:bound]) > maximum and position > start:
            pieces.append(Piece(block, start, position))
            start = position
        position = bound
    pieces.append(Piece(block, start, len(block['text'])))
    # Trim whitespace at slice edges so spans hold text, not padding.
    trimmed = []
    for piece in pieces:
        s, e = piece.start, piece.end
        while s < e and block['text'][s].isspace():
            s += 1
        while e > s and block['text'][e - 1].isspace():
            e -= 1
        if e > s:
            trimmed.append(Piece(block, s, e))
    return trimmed


def _sentence_units(group: Group, maximum: int) -> list[Group]:
    """An oversized group split into units of whole pieces, cut only after a piece that
    closes a sentence when possible."""
    units, current = [], []
    for piece in group.pieces:
        if current and sum(p.tokens for p in current) + piece.tokens > maximum:
            # Move back to the last sentence end inside the current unit, if there is one.
            cut = max((i for i, p in enumerate(current) if _CLOSED.search(p.text)), default=None)
            if cut is not None and cut < len(current) - 1:
                units.append(Group(current[:cut + 1], group.kind))
                current = current[cut + 1:]
            else:
                units.append(Group(current, group.kind))
                current = []
        current.append(piece)
    if current:
        units.append(Group(current, group.kind))
    return units


def plan_chunks(blocks: list[dict], config: dict) -> list[ChunkSpec]:
    """Pure planning step: blocks (reading order, with section_path) → chunk specs."""
    target, maximum, overlap = config['target'], config['max'], config['overlap']
    groups: list[tuple[str, str, Group]] = []   # (section, speaker, group)
    case_until_heading = False
    for block in blocks:
        if block['kind'] == 'heading':
            case_until_heading = bool(CASE_HEADING.match(block['text'].strip()))
            continue          # titles live in sections; their text is not chunk content
        key = (block['section_path'], block['speaker'])
        kind = 'table' if block['chart_row'] else ('case' if case_until_heading else 'text')
        last = groups[-1] if groups else None
        joinable = last and (last[0], last[1]) == key and (
            (kind == 'table' and last[2].kind == 'table') or
            (kind == 'case' and last[2].kind in ('case', 'table') and case_until_heading) or
            # One sentence split over two blocks: keep it in one unit.
            (kind == 'text' and last[2].kind == 'text'
             and continues(last[2].pieces[-1].text, block['text'])))
        if joinable:
            last[2].pieces.extend(_split_block(block, maximum))
            if kind == 'case':
                last[2].kind = 'case'
            continue
        groups.append((key[0], key[1], Group(_split_block(block, maximum), kind)))

    chunks: list[ChunkSpec] = []
    for section, speaker, group in groups:
        units = [group] if group.tokens <= maximum else _sentence_units(group, maximum)
        for unit in units:
            current = chunks[-1] if chunks else None
            same_scope = current and (current.section_path, current.speaker) == (section, speaker)
            fits = same_scope and current.tokens + unit.tokens <= target and \
                current.kind == unit.kind == 'text'
            if fits:
                current.pieces.extend(unit.pieces)
                continue
            spec = ChunkSpec(section, speaker, unit.kind)
            if same_scope and unit.kind == 'text' and current.kind == 'text':
                # Overlap: carry whole trailing pieces of the previous chunk.
                carried, size = [], 0
                for piece in reversed(current.pieces):
                    if size + piece.tokens > overlap:
                        break
                    carried.insert(0, piece)
                    size += piece.tokens
                # Never open a chunk with the second half of a sentence.
                while carried:
                    index = current.pieces.index(carried[0])
                    if index == 0 or not continues(current.pieces[index - 1].text, carried[0].text):
                        break
                    size -= carried.pop(0).tokens
                if carried and size + unit.tokens <= maximum:
                    spec.pieces.extend(carried)
            spec.pieces.extend(unit.pieces)
            chunks.append(spec)
    return chunks


def propose_topics(spec: ChunkSpec) -> list[tuple[str, float]]:
    """Keyword topics for a chunk; status 'proposed', never treated as reviewed."""
    lowered = spec.text.lower()
    topics = []
    if spec.kind == 'case':
        topics.append(('menh_le', 0.8))
    if spec.kind == 'table':
        topics.append(('can_chi', 0.7))
    for topic, words in TOPIC_KEYWORDS.items():
        hits = sum(lowered.count(w) for w in words)
        if hits >= 2:
            topics.append((topic, round(min(0.9, 0.3 + 0.1 * hits), 2)))
    return topics


class ChunkStage:
    name = 'chunk'

    def _config(self, ctx: JobContext) -> dict:
        return {**DEFAULTS, **(ctx.pipeline_config.get('chunk') or {})}

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            ids = conn.execute(text('SELECT page_revision_id FROM generation_pages'
                                    ' WHERE generation_id = :g ORDER BY page_id'),
                               {'g': ctx.generation_id}).scalars().all()
        if not ids:
            return []
        material = '|'.join(map(str, ids)) + CHUNKER_VERSION + json.dumps(self._config(ctx),
                                                                          sort_keys=True)
        return [Unit('doc', hashlib.sha256(material.encode()).hexdigest())]

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        with ctx.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT b.id, p.physical_page_number, p.page_kind, b.ordinal, b.kind,"
                " b.attributes->>'role' AS role, (b.attributes->>'level')::int AS level, b.text,"
                " b.page_revision_id, b.start_offset, b.end_offset, b.bbox, b.speaker_layer,"
                " coalesce((b.attributes->>'chart_row')::boolean, false) AS chart_row, r.state"
                ' FROM generation_pages gp JOIN pages p ON p.id = gp.page_id'
                ' JOIN page_revisions r ON r.id = gp.page_revision_id'
                ' JOIN blocks b ON b.page_revision_id = r.id WHERE gp.generation_id = :g'
                ' ORDER BY p.page_kind, p.physical_page_number, b.ordinal'),
                {'g': ctx.generation_id}).mappings().all()
        refs = [BlockRef(str(r['id']), r['physical_page_number'], r['page_kind'], r['ordinal'],
                         r['kind'], r['role'], r['level'], r['text']) for r in rows]
        _, assignment = build_sections(refs)
        blocks = [{'id': str(r['id']), 'text': r['text'], 'kind': r['kind'],
                   'revision_id': str(r['page_revision_id']), 'start': r['start_offset'],
                   'end': r['end_offset'], 'bbox': r['bbox'], 'speaker': r['speaker_layer'],
                   'chart_row': r['chart_row'], 'review': r['state'] == 'review_required',
                   'section_path': assignment[str(r['id'])]}
                  for r in rows if not r['role'] and r['state'] != 'excluded'
                  and str(r['id']) in assignment]
        specs = plan_chunks(blocks, self._config(ctx))
        language = (ctx.pipeline_config.get('language') or 'vi')
        return {'chunks': [{
            'text': spec.text, 'tokens': spec.tokens, 'kind': spec.kind,
            'speaker': spec.speaker, 'section_path': spec.section_path, 'language': language,
            'quality': 'review_required' if any(p.block['review'] for p in spec.pieces)
            else 'accepted',
            'topics': propose_topics(spec),
            'spans': self._spans(spec)} for spec in specs]}

    def _spans(self, spec: ChunkSpec) -> list[dict]:
        spans, position = [], 0
        for piece in spec.pieces:
            spans.append({'revision_id': piece.block['revision_id'], 'block_id': piece.block['id'],
                          'start': piece.block['start'] + piece.start,
                          'end': piece.block['start'] + piece.end, 'bbox': piece.block['bbox'],
                          'chunk_start': position, 'chunk_end': position + (piece.end - piece.start)})
            position += piece.end - piece.start + len(SEPARATOR)
        return spans

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        members = []
        for ordinal, chunk in enumerate(result['chunks']):
            chunk_id = self._chunk_row(conn, chunk)
            members.append({'chunk_id': str(chunk_id), 'section_path': chunk['section_path'],
                            'ordinal': ordinal, 'topics': chunk['topics']})
        output = {'members': members, 'chunker_version': CHUNKER_VERSION}
        self.attach(conn, ctx, unit, output)
        return output

    def _chunk_row(self, conn: Connection, chunk: dict):
        content_hash = hashlib.sha256(chunk['text'].encode('utf-8')).hexdigest()
        signature = json.dumps([[s['revision_id'], s['block_id'], s['start'], s['end'],
                                 s['chunk_start'], s['chunk_end']] for s in chunk['spans']])
        existing = conn.execute(text(
            'SELECT c.id FROM chunks c WHERE c.content_hash = :h AND c.speaker_layer = :sp'
            ' AND c.quality_state = :q AND (SELECT jsonb_agg(jsonb_build_array(s.page_revision_id::text, s.block_id::text,'
            ' s.start_offset, s.end_offset, s.chunk_start, s.chunk_end) ORDER BY s.ordinal)'
            ' FROM chunk_spans s WHERE s.chunk_id = c.id) = CAST(:sig AS jsonb) LIMIT 1'),
            {'h': content_hash, 'sp': chunk['speaker'], 'q': chunk['quality'],
             'sig': signature}).scalar()
        if existing:
            return existing
        chunk_id = conn.execute(text(
            'INSERT INTO chunks (content_hash, text, token_count, language, kind, speaker_layer,'
            ' quality_state) VALUES (:h, :t, :n, :lang, :k, :sp, :q) RETURNING id'),
            {'h': content_hash, 't': chunk['text'], 'n': chunk['tokens'], 'lang': chunk['language'],
             'k': chunk['kind'], 'sp': chunk['speaker'], 'q': chunk['quality']}).scalar_one()
        for ordinal, span in enumerate(chunk['spans']):
            conn.execute(text(
                'INSERT INTO chunk_spans (chunk_id, page_revision_id, block_id, ordinal, start_offset,'
                ' end_offset, bbox, chunk_start, chunk_end) VALUES (:c, :r, :b, :o, :s, :e,'
                ' CAST(:bbox AS jsonb), :cs, :ce)'),
                {'c': chunk_id, 'r': span['revision_id'], 'b': span['block_id'], 'o': ordinal,
                 's': span['start'], 'e': span['end'], 'bbox': json.dumps(span['bbox']),
                 'cs': span['chunk_start'], 'ce': span['chunk_end']})
        return chunk_id

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        sections = dict(conn.execute(text('SELECT path, id FROM sections WHERE generation_id = :g'),
                                     {'g': ctx.generation_id}).all())
        topics = dict(conn.execute(text('SELECT key, id FROM topics')).all())
        linked = 0
        for member in output['members']:
            done = conn.execute(text(
                'INSERT INTO generation_chunks (generation_id, chunk_id, section_id, ordinal)'
                ' VALUES (:g, :c, :s, :o) ON CONFLICT DO NOTHING'),
                {'g': ctx.generation_id, 'c': member['chunk_id'],
                 's': sections[member['section_path']], 'o': member['ordinal']}).rowcount
            linked += done
            if not done:
                continue
            for topic, confidence in member['topics']:
                if topic in topics:
                    conn.execute(text(
                        'INSERT INTO chunk_classifications (chunk_id, generation_id, topic_id,'
                        " status, confidence, classification_version) VALUES (:c, :g, :t,"
                        " 'proposed', :conf, 'keywords-1')"),
                        {'c': member['chunk_id'], 'g': ctx.generation_id, 't': topics[topic],
                         'conf': confidence})
        if linked:
            conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                              ' WHERE id = :g'),
                         {'g': ctx.generation_id, 'c': json.dumps({
                             'chunks': len(output['members']),
                             'chunker_version': output['chunker_version']})})
            conn.execute(text('UPDATE ingestion_jobs SET counters = counters || CAST(:c AS jsonb)'
                              ' WHERE id = :j'),
                         {'j': ctx.job_id, 'c': json.dumps({'chunks': len(output['members'])})})
        # School of each chunk from the version's approved scopes (reviewed, not guessed).
        scopes.classify(conn, ctx.generation_id, ctx.book_version_id)
