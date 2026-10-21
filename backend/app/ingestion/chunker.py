"""``chunk`` stage: structure-first parent/child chunks with exact provenance (chunker-3).

The book is read as chapters → sections → subsections (the heading tree of the
``structure`` stage) → atomic units, and two chunk layers are cut from it:

* **units** are never split: a paragraph (a sentence the PDF broke over two
  blocks or pages stays one paragraph — ``continues``), a whole list (an intro
  line ending in ":" plus its items), a whole table or printed pillar chart, and
  a whole example ("Ví dụ / Thí dụ / Mệnh lệ / Càn tạo …" with its chart and the
  prose that discusses it). Only a single unit longer than the hard cap is cut —
  at block boundaries, else at sentence ends — and flagged ``oversized_unit``;
* **children** are what gets embedded and retrieved: one unit, or consecutive
  short paragraphs of one section and speaker layer merged up to a target;
* **parents** are what the LLM reads: the highest node of the heading tree
  whose whole subtree fits the parent budget (so a short section keeps its
  subsections together), else that node's own text in windows of whole children
  and then its subsections, recursively. A parent never crosses a heading of a
  node outside it, so it is always "this section", "this subsection" or "part n
  of this section".

Every child piece is a span ``[chunk_start, chunk_end)`` equal to
``normalized_text[start_offset:end_offset]`` of its page revision; parents are
rendered text over their children (heading lines included) and keep the child
list, so a citation always resolves to exact source spans. Identical child text
with identical spans and quality reuses the existing chunk row (stable identity,
T017). Metadata and the context header of each child go to ``chunk_meta``;
parents go to ``chunk_parents`` (summaries are added by the ``summarize`` stage).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..knowledge import scopes
from . import chunk_meta
from .layout import CLOSED as _CLOSED, LIST_ITEM, continues
from .structure import BlockRef, build_sections
from .tokens import count_tokens, counter_name
from .worker import JobContext, Unit

CHUNKER_NAME = 'chunker-3'
DEFAULTS = {'child_target': 250, 'hard_max': 1000, 'parent_max': 1200, 'example_max': 900}
SEPARATOR = '\n\n'
CASE_HEADING = re.compile(r'^\(?\s*(thí dụ|ví dụ|mệnh lệ|lệ)\b', re.IGNORECASE)
EXAMPLE_START = re.compile(
    r'^\s*\(?\s*(thí dụ|ví dụ|mệnh lệ|lệ\s*\d|càn tạo|khôn tạo|nam mệnh|nữ mệnh|tạo\s*:)',
    re.IGNORECASE)
NUMBERED_ITEM = re.compile(r'^\s*\(?\d{1,2}[.)]\s+\S')
_SENTENCE = re.compile(r'(?<=[.!?…;:])\s+')
DB_KIND = {'paragraph': 'text', 'list': 'list', 'table': 'table', 'example': 'case'}
SPEAKER_TAGS = {'original_author': 'Nguyên văn', 'commentator': 'Bình chú',
                'translator': 'Lời dịch giả', 'editor': 'Lời biên tập'}
TOPIC_KEYWORDS = {
    'van_han': ('đại vận', 'lưu niên', 'ứng kỳ', 'hành vận', 'tiểu vận'),
    'thap_than': ('thực thần', 'thương quan', 'chính quan', 'thất sát', 'chính tài', 'thiên tài',
                  'chính ấn', 'thiên ấn', 'kiêu thần', 'tỷ kiên', 'kiếp tài'),
    'ngu_hanh': ('ngũ hành', 'mộc', 'hỏa', 'thổ', 'kim', 'thủy', 'tương sinh', 'tương khắc'),
}


def chunker_version() -> str:
    return f'{CHUNKER_NAME}/{counter_name()}'


@dataclass
class Piece:
    """A contiguous slice of one block (usually the whole block)."""
    block: dict
    start: int          # offset inside the block text
    end: int

    @property
    def text(self) -> str:
        return self.block['text'][self.start:self.end]


@dataclass
class UnitSpec:
    section_path: str
    speaker: str
    kind: str                      # paragraph | list | table | example
    pieces: list[Piece] = field(default_factory=list)
    oversized: bool = False

    @property
    def text(self) -> str:
        return SEPARATOR.join(p.text for p in self.pieces)

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)


@dataclass
class ChildSpec:
    section_path: str
    speaker: str
    kind: str
    pieces: list[Piece]
    oversized: bool = False
    parent: int = -1

    @property
    def text(self) -> str:
        return SEPARATOR.join(p.text for p in self.pieces)

    @property
    def tokens(self) -> int:
        return count_tokens(self.text)


@dataclass
class ParentSpec:
    root_path: str                 # the section the parent belongs to
    children: list[int]            # child indices, document order
    text: str
    tokens: int
    kind: str                      # subtree | window


# ---- units -----------------------------------------------------------------------------------

def _whole(block: dict) -> Piece:
    return Piece(block, 0, len(block['text']))


def _sentence_slices(block: dict, maximum: int) -> list[Piece]:
    """A block longer than ``maximum`` cut at sentence ends (trimmed slices)."""
    raw, start, position = [], 0, 0
    bounds = [m.end() for m in _SENTENCE.finditer(block['text'])] + [len(block['text'])]
    for bound in bounds:
        if count_tokens(block['text'][start:bound]) > maximum and position > start:
            raw.append((start, position))
            start = position
        position = bound
    raw.append((start, len(block['text'])))
    pieces = []
    for s, e in raw:
        while s < e and block['text'][s].isspace():
            s += 1
        while e > s and block['text'][e - 1].isspace():
            e -= 1
        if e > s:
            pieces.append(Piece(block, s, e))
    return pieces


def _is_list_item(text_: str) -> bool:
    return bool(LIST_ITEM.match(text_) or NUMBERED_ITEM.match(text_))


def plan_units(blocks: list[dict], config: dict) -> list[UnitSpec]:
    """Blocks (reading order, with section_path/speaker/kind/chart_row) → atomic units."""
    units: list[UnitSpec] = []
    example_section = False          # inside a "Ví dụ" heading's section
    after_heading = False            # a heading always ends the unit before it
    for block in blocks:
        if block['kind'] == 'heading':
            example_section = bool(CASE_HEADING.match(block['text'].strip()))
            after_heading = True
            continue          # titles live in the section tree; parents render them
        scope = (block['section_path'], block['speaker'])
        last = units[-1] if units else None
        same = last is not None and not after_heading and \
            (last.section_path, last.speaker) == scope
        after_heading = False
        body = block['text'].strip()
        tabular = block['kind'] == 'table' or block['chart_row']
        if example_section:
            kind = 'example'
        elif tabular:
            kind = 'table'
        elif EXAMPLE_START.match(body):
            kind = 'example_start'
        elif _is_list_item(body):
            kind = 'list'
        else:
            kind = 'paragraph'

        if same and last.pieces and continues(last.pieces[-1].text, block['text']) \
                and kind in ('paragraph', 'list'):
            last.pieces.append(_whole(block))                 # one sentence over two blocks
            continue
        if kind == 'example':
            if same and last.kind == 'example':
                last.pieces.append(_whole(block))
            else:
                units.append(UnitSpec(*scope, 'example', [_whole(block)]))
            continue
        if kind == 'example_start':
            units.append(UnitSpec(*scope, 'example', [_whole(block)]))
            continue
        if kind == 'table':
            # A chart belongs to the example that introduced it; consecutive rows are one table.
            if same and last.kind in ('table', 'example'):
                last.pieces.append(_whole(block))
            else:
                units.append(UnitSpec(*scope, 'table', [_whole(block)]))
            continue
        if kind == 'list':
            if same and last.kind == 'list':
                last.pieces.append(_whole(block))
            elif same and last.kind == 'paragraph' and len(last.pieces) == 1 \
                    and last.text.rstrip().endswith(':'):
                last.kind = 'list'                            # intro line + its items
                last.pieces.append(_whole(block))
            else:
                units.append(UnitSpec(*scope, 'list', [_whole(block)]))
            continue
        # A paragraph: inline examples run on over their discussion up to a budget.
        if same and last.kind == 'example' and not example_section \
                and last.tokens + count_tokens(block['text']) <= config['example_max']:
            last.pieces.append(_whole(block))
            continue
        units.append(UnitSpec(*scope, 'paragraph', [_whole(block)]))
    return [part for unit in units for part in _cap(unit, config['hard_max'])]


def _cap(unit: UnitSpec, maximum: int) -> list[UnitSpec]:
    """A unit over the hard cap: cut at block boundaries, then sentences (flagged)."""
    if unit.tokens <= maximum:
        return [unit]
    pieces = [p for piece in unit.pieces for p in (
        _sentence_slices(piece.block, maximum) if count_tokens(piece.text) > maximum else [piece])]
    parts, current, size = [], [], 0
    for piece in pieces:
        tokens = count_tokens(piece.text)
        if current and size + tokens > maximum:
            # Prefer to end a part after a piece that closes a sentence.
            cut = max((i for i, p in enumerate(current) if _CLOSED.search(p.text)), default=None)
            if cut is not None and cut < len(current) - 1:
                parts.append(current[:cut + 1])
                current = current[cut + 1:]
                size = sum(count_tokens(p.text) for p in current)
            else:
                parts.append(current)
                current, size = [], 0
        current.append(piece)
        size += tokens
    if current:
        parts.append(current)
    return [UnitSpec(unit.section_path, unit.speaker, unit.kind, part, oversized=True)
            for part in parts]


# ---- children --------------------------------------------------------------------------------

def plan_children(units: list[UnitSpec], config: dict) -> list[ChildSpec]:
    children: list[ChildSpec] = []
    for unit in units:
        last = children[-1] if children else None
        if (last and unit.kind == 'paragraph' and last.kind == 'paragraph'
                and not unit.oversized and not last.oversized
                and (last.section_path, last.speaker) == (unit.section_path, unit.speaker)
                and last.tokens + unit.tokens <= config['child_target']):
            last.pieces.extend(unit.pieces)
            continue
        children.append(ChildSpec(unit.section_path, unit.speaker, unit.kind, list(unit.pieces),
                                  unit.oversized))
    return children


# ---- parents ---------------------------------------------------------------------------------

def _tree(sections: list[dict]) -> dict[str, dict]:
    nodes = {'': {'path': '', 'title': '', 'level': 0, 'parent': None, 'subs': [], 'own': []}}
    for spec in sections:
        nodes[spec['path']] = {'path': spec['path'], 'title': spec['title'], 'level': spec['level'],
                               'parent': spec['parent_path'] or '', 'subs': [], 'own': []}
    for spec in sections:
        nodes[spec['parent_path'] or '']['subs'].append(spec['path'])
    return nodes


def breadcrumb(nodes: dict[str, dict], path: str) -> list[str]:
    trail = []
    while path:
        node = nodes[path]
        if node['title']:
            trail.append(node['title'])
        path = node['parent']
    return list(reversed(trail))


def _render(nodes: dict, children: list[ChildSpec], members: list[int], root: str) -> str:
    """Parent text: heading lines for each section entered, then its children in order."""
    lines, shown = [], set()
    for index in members:
        child = children[index]
        path = child.section_path
        chain = []
        while path and path != nodes[root]['parent'] and path not in shown:
            chain.append(path)
            if path == root:
                break
            path = nodes[path]['parent']
        for section in reversed(chain):
            node = nodes[section]
            if node['title']:
                lines.append(f"{'#' * min(max(node['level'], 1) + 1, 5)} {node['title']}")
            shown.add(section)
        tag = SPEAKER_TAGS.get(child.speaker)
        lines.append(f'[{tag}] {child.text}' if tag else child.text)
    return '\n\n'.join(lines)


def plan_parents(children: list[ChildSpec], sections: list[dict], config: dict) -> list[ParentSpec]:
    nodes = _tree(sections)
    for index, child in enumerate(children):
        nodes[child.section_path]['own'].append(index)
    sizes = {i: c.tokens for i, c in enumerate(children)}
    subtree_cache: dict[str, list[int]] = {}

    def subtree(path: str) -> list[int]:
        if path not in subtree_cache:
            node = nodes[path]
            members = list(node['own'])
            for sub in node['subs']:
                members += subtree(sub)
            subtree_cache[path] = sorted(members)
        return subtree_cache[path]

    parents: list[ParentSpec] = []

    def emit(root: str, members: list[int], kind: str) -> None:
        if not members:
            return
        body = _render(nodes, children, members, root)
        parents.append(ParentSpec(root, members, body, count_tokens(body), kind))
        for index in members:
            children[index].parent = len(parents) - 1

    def assign(path: str) -> None:
        members = subtree(path)
        if not members:
            return
        if path and sum(sizes[i] for i in members) <= config['parent_max']:
            emit(path, members, 'subtree')
            return
        window, size = [], 0
        for index in nodes[path]['own']:
            if window and size + sizes[index] > config['parent_max']:
                emit(path, window, 'window')
                window, size = [], 0
            window.append(index)
            size += sizes[index]
        emit(path, window, 'window')
        for sub in nodes[path]['subs']:
            assign(sub)

    assign('')
    parents.sort(key=lambda p: p.children[0])
    for number, parent in enumerate(parents):
        for index in parent.children:
            children[index].parent = number
    return parents


# ---- metadata --------------------------------------------------------------------------------

def propose_topics(child: ChildSpec) -> list[tuple[str, float]]:
    """Keyword topics for a chunk; status 'proposed', never treated as reviewed."""
    lowered = child.text.lower()
    topics = []
    if child.kind == 'example':
        topics.append(('menh_le', 0.8))
    if child.kind == 'table':
        topics.append(('can_chi', 0.7))
    for topic, words in TOPIC_KEYWORDS.items():
        hits = sum(lowered.count(w) for w in words)
        if hits >= 2:
            topics.append((topic, round(min(0.9, 0.3 + 0.1 * hits), 2)))
    return topics


def child_meta(child: ChildSpec, nodes: dict, book: dict) -> dict:
    pages = sorted({p.block['page'] for p in child.pieces})
    labels = [p.block.get('printed_label') for p in child.pieces if p.block.get('printed_label')]
    origins = sorted({p.block.get('origin') or 'native' for p in child.pieces})
    confs = [p.block['conf'] for p in child.pieces if p.block.get('conf') is not None]
    trail = breadcrumb(nodes, child.section_path)
    meta = {
        'version': chunk_meta.META_VERSION,
        'book_title': book['title'], 'edition': book.get('edition'), 'authors': book.get('authors'),
        'school': book.get('school_label'), 'school_key': book.get('school_key'),
        'source_file': book.get('filename'), 'language': book.get('language', 'vi'),
        'breadcrumb': trail, 'chapter': trail[0] if trail else None,
        'section': trail[1] if len(trail) > 1 else None,
        'subsection': trail[2] if len(trail) > 2 else None,
        'section_path': child.section_path,
        'page_start': pages[0] if pages else None, 'page_end': pages[-1] if pages else None,
        'printed_pages': [labels[0], labels[-1]] if labels else None,
        'speaker_layer': child.speaker, 'unit_kind': child.kind,
        'extraction': origins, 'ocr_confidence': round(sum(confs) / len(confs), 1) if confs else None,
        'tokens': child.tokens, 'oversized_unit': child.oversized,
        'entities': chunk_meta.entities(child.text),
        'charts': chunk_meta.charts_in([(i, p.block['kind'], p.text)
                                        for i, p in enumerate(child.pieces)]),
        'simhash': chunk_meta.simhash(child.text),
    }
    meta['has_chart'] = bool(meta['charts'])
    meta['header'] = chunk_meta.header(book['title'], book.get('school_label'), trail,
                                       (pages[0], pages[-1]) if pages else None)
    return meta


# ---- stage -----------------------------------------------------------------------------------

class ChunkStage:
    name = 'chunk'

    def _config(self, ctx: JobContext) -> dict:
        return {**DEFAULTS, **(ctx.pipeline_config.get('chunk') or {})}

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            ids = conn.execute(text('SELECT page_revision_id FROM generation_pages'
                                    ' WHERE generation_id = :g ORDER BY page_id'),
                               {'g': ctx.generation_id}).scalars().all()
            book = _book(conn, ctx.book_version_id)
        if not ids:
            return []
        material = '|'.join(map(str, ids)) + chunker_version() + chunk_meta.META_VERSION + \
            json.dumps(self._config(ctx), sort_keys=True) + json.dumps(book, sort_keys=True)
        return [Unit('doc', hashlib.sha256(material.encode()).hexdigest())]

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        with ctx.engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT b.id, p.physical_page_number, p.page_kind, b.ordinal, b.kind,"
                " b.attributes->>'role' AS role, (b.attributes->>'level')::int AS level, b.text,"
                " b.page_revision_id, b.start_offset, b.end_offset, b.bbox, b.speaker_layer,"
                " coalesce((b.attributes->>'chart_row')::boolean, false) AS chart_row, r.state,"
                " b.attributes->>'origin' AS origin, (b.attributes->>'conf')::float AS conf,"
                ' r.printed_page_label'
                ' FROM generation_pages gp JOIN pages p ON p.id = gp.page_id'
                ' JOIN page_revisions r ON r.id = gp.page_revision_id'
                ' JOIN blocks b ON b.page_revision_id = r.id WHERE gp.generation_id = :g'
                ' ORDER BY p.page_kind, p.physical_page_number, b.ordinal'),
                {'g': ctx.generation_id}).mappings().all()
            book = _book(conn, ctx.book_version_id)
        refs = [BlockRef(str(r['id']), r['physical_page_number'], r['page_kind'], r['ordinal'],
                         r['kind'], r['role'], r['level'], r['text']) for r in rows]
        sections, assignment = build_sections(refs)
        blocks = [{'id': str(r['id']), 'text': r['text'], 'kind': r['kind'],
                   'revision_id': str(r['page_revision_id']), 'start': r['start_offset'],
                   'end': r['end_offset'], 'bbox': r['bbox'], 'speaker': r['speaker_layer'],
                   'chart_row': r['chart_row'], 'review': r['state'] == 'review_required',
                   'page': r['physical_page_number'], 'printed_label': r['printed_page_label'],
                   'origin': r['origin'], 'conf': r['conf'],
                   'section_path': assignment[str(r['id'])]}
                  for r in rows if not r['role'] and r['state'] != 'excluded'
                  and str(r['id']) in assignment]
        config = self._config(ctx)
        section_dicts = [vars(s) for s in sections]
        children = plan_children(plan_units(blocks, config), config)
        parents = plan_parents(children, section_dicts, config)
        nodes = _tree(section_dicts)
        language = ctx.pipeline_config.get('language') or 'vi'
        result_children = []
        for child in children:
            meta = child_meta(child, nodes, {**book, 'language': language})
            result_children.append({
                'text': child.text, 'tokens': child.tokens, 'kind': DB_KIND[child.kind],
                'speaker': child.speaker, 'section_path': child.section_path,
                'language': language, 'parent': child.parent,
                'quality': 'review_required' if any(p.block['review'] for p in child.pieces)
                else 'accepted',
                'topics': propose_topics(child), 'meta': meta, 'spans': _spans(child)})
        result_parents = []
        for number, parent in enumerate(parents):
            members = [result_children[i] for i in parent.children]
            pages = [m['meta']['page_start'] for m in members if m['meta']['page_start']] + \
                [m['meta']['page_end'] for m in members if m['meta']['page_end']]
            trail = breadcrumb(nodes, parent.root_path)
            result_parents.append({
                'ordinal': number, 'section_path': parent.root_path, 'text': parent.text,
                'tokens': parent.tokens, 'children': parent.children,
                'meta': {'version': chunk_meta.META_VERSION, 'kind': parent.kind,
                         'breadcrumb': trail, 'book_title': book['title'],
                         'school': book.get('school_label'), 'school_key': book.get('school_key'),
                         'page_start': min(pages) if pages else None,
                         'page_end': max(pages) if pages else None,
                         'speakers': sorted({m['speaker'] for m in members}),
                         'has_chart': any(m['meta']['has_chart'] for m in members),
                         'header': chunk_meta.header(book['title'], book.get('school_label'), trail,
                                                     (min(pages), max(pages)) if pages else None)}})
        return {'chunks': result_children, 'parents': result_parents}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        members = []
        for ordinal, chunk in enumerate(result['chunks']):
            chunk_id = self._chunk_row(conn, chunk)
            members.append({'chunk_id': str(chunk_id), 'section_path': chunk['section_path'],
                            'ordinal': ordinal, 'topics': chunk['topics'],
                            'parent': chunk['parent'], 'meta': chunk['meta']})
        output = {'members': members, 'parents': result['parents'],
                  'chunker_version': chunker_version()}
        self.attach(conn, ctx, unit, output)
        return output

    def _chunk_row(self, conn: Connection, chunk: dict):
        content_hash = hashlib.sha256(chunk['text'].encode('utf-8')).hexdigest()
        signature = json.dumps([[s['revision_id'], s['block_id'], s['start'], s['end'],
                                 s['chunk_start'], s['chunk_end']] for s in chunk['spans']])
        existing = conn.execute(text(
            'SELECT c.id FROM chunks c WHERE c.content_hash = :h AND c.speaker_layer = :sp'
            ' AND c.quality_state = :q AND c.kind = :k AND (SELECT jsonb_agg(jsonb_build_array('
            's.page_revision_id::text, s.block_id::text, s.start_offset, s.end_offset,'
            ' s.chunk_start, s.chunk_end) ORDER BY s.ordinal)'
            ' FROM chunk_spans s WHERE s.chunk_id = c.id) = CAST(:sig AS jsonb) LIMIT 1'),
            {'h': content_hash, 'sp': chunk['speaker'], 'q': chunk['quality'], 'k': chunk['kind'],
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
        if conn.execute(text('SELECT 1 FROM generation_chunks WHERE generation_id = :g LIMIT 1'),
                        {'g': ctx.generation_id}).first():
            return       # already attached (a replay of the same unit)
        parent_ids = []
        for parent in output['parents']:
            parent_ids.append(conn.execute(text(
                'INSERT INTO chunk_parents (generation_id, section_id, ordinal, text, token_count,'
                ' content_hash, meta) VALUES (:g, :s, :o, :t, :n, :h, CAST(:m AS jsonb))'
                ' RETURNING id'),
                {'g': ctx.generation_id, 's': sections.get(parent['section_path']),
                 'o': parent['ordinal'], 't': parent['text'], 'n': parent['tokens'],
                 'h': hashlib.sha256(parent['text'].encode('utf-8')).hexdigest(),
                 'm': json.dumps(parent['meta'], ensure_ascii=False)}).scalar_one())
        for member in output['members']:
            conn.execute(text(
                'INSERT INTO generation_chunks (generation_id, chunk_id, section_id, ordinal,'
                ' parent_id) VALUES (:g, :c, :s, :o, :p)'),
                {'g': ctx.generation_id, 'c': member['chunk_id'],
                 's': sections[member['section_path']], 'o': member['ordinal'],
                 'p': parent_ids[member['parent']] if member['parent'] >= 0 else None})
            conn.execute(text(
                'INSERT INTO chunk_meta (generation_id, chunk_id, meta) VALUES (:g, :c,'
                ' CAST(:m AS jsonb))'),
                {'g': ctx.generation_id, 'c': member['chunk_id'],
                 'm': json.dumps(member['meta'], ensure_ascii=False)})
            for topic, confidence in member['topics']:
                if topic in topics:
                    conn.execute(text(
                        'INSERT INTO chunk_classifications (chunk_id, generation_id, topic_id,'
                        " status, confidence, classification_version) VALUES (:c, :g, :t,"
                        " 'proposed', :conf, 'keywords-1')"),
                        {'c': member['chunk_id'], 'g': ctx.generation_id, 't': topics[topic],
                         'conf': confidence})
        counts = {'chunks': len(output['members']), 'parents': len(output['parents']),
                  'chunker_version': output['chunker_version']}
        conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                          ' WHERE id = :g'), {'g': ctx.generation_id, 'c': json.dumps(counts)})
        conn.execute(text('UPDATE ingestion_jobs SET counters = counters || CAST(:c AS jsonb)'
                          ' WHERE id = :j'),
                     {'j': ctx.job_id, 'c': json.dumps({'chunks': counts['chunks'],
                                                        'parents': counts['parents']})})
        # School of each chunk from the version's approved scopes (reviewed, not guessed).
        scopes.classify(conn, ctx.generation_id, ctx.book_version_id)


def _spans(child: ChildSpec) -> list[dict]:
    spans, position = [], 0
    for piece in child.pieces:
        spans.append({'revision_id': piece.block['revision_id'], 'block_id': piece.block['id'],
                      'start': piece.block['start'] + piece.start,
                      'end': piece.block['start'] + piece.end, 'bbox': piece.block['bbox'],
                      'chunk_start': position, 'chunk_end': position + (piece.end - piece.start)})
        position += piece.end - piece.start + len(SEPARATOR)
    return spans


def _book(conn: Connection, version_id) -> dict:
    """Book-level metadata every chunk of this version carries."""
    row = conn.execute(text(
        'SELECT b.title, b.language, v.edition_label,'
        ' (SELECT i.display_name FROM ingestion_batch_items i WHERE i.book_version_id = v.id'
        '  ORDER BY i.created_at LIMIT 1) AS filename,'
        ' (SELECT string_agg(a.name, \', \' ORDER BY ba.ordinal) FROM book_authors ba'
        '  JOIN authors a ON a.id = ba.author_id WHERE ba.book_id = b.id) AS authors,'
        ' s.key AS school_key, s.label AS school_label'
        ' FROM book_versions v JOIN books b ON b.id = v.book_id'
        ' LEFT JOIN LATERAL (SELECT sch.key, sch.label FROM school_scopes sc'
        '  JOIN schools sch ON sch.id = sc.school_id'
        "  WHERE sc.book_version_id = v.id AND sc.state = 'approved'"
        '  ORDER BY sc.first_page IS NULL DESC LIMIT 1) s ON true'
        ' WHERE v.id = :v'), {'v': version_id}).mappings().one()
    return {'title': row['title'], 'language': row['language'], 'edition': row['edition_label'],
            'filename': row['filename'], 'authors': row['authors'],
            'school_key': row['school_key'], 'school_label': row['school_label']}
