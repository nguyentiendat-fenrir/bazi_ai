"""Page corrections: immutable revisions, incremental rebuilds and impact (docs/05).

A correction never edits a revision: it writes revision N+1 (base = N) with the
corrected blocks and schedules an incremental generation — the latest finished
generation's page selection with each page's newest correction swapped in. The
normal pipeline then reuses everything keyed by unchanged inputs (extraction,
OCR, chunks whose text and spans did not change, vectors by content hash), so
only corrected pages are re-chunked and only changed text is re-embedded. The
section tree is rebuilt from headings, so a heading change reshapes exactly the
sections it touches.

Corrections made while that rebuild is still queued join it; while a job of the
version runs, a correction is refused (409) rather than lost. Evidence keeps
citing the old revision (no drift); rules, assertions and case revisions citing
the corrected characters get a SOURCE_CHANGED review item and keep their
reviewed meaning until a reviewer acts.
"""
from __future__ import annotations

import base64
import hashlib
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..ingestion.normalize import normalize
from . import catalog

ACTIVE_JOB = ['queued', 'running', 'retry_wait', 'waiting_review', 'cancel_requested']
FINISHED_JOB = ['succeeded', 'partial']
LIVE = ['draft', 'in_review', 'approved']      # rejected/revoked content needs no flag
# entity kind, link table, link column, entity table
SOURCES = (('rule', 'rule_sources', 'rule_id', 'knowledge_rules'),
           ('assertion', 'assertion_sources', 'assertion_id', 'assertions'),
           ('case_revision', 'case_sources', 'case_revision_id', 'case_revisions'))
IMPACT_KINDS = ('page', 'chunk_added', 'chunk_removed', 'evidence', 'rule', 'assertion',
                'case_revision')

PAGE_SELECT = (
    'SELECT r.id, r.page_id, p.book_version_id, p.physical_page_number, p.page_kind,'
    ' r.revision_no, r.base_revision_id, r.state, r.printed_page_label,'
    ' r.printed_label_verified, r.quality, r.layout, r.normalized_text, r.created_at,'
    ' (SELECT l.id FROM page_revisions l WHERE l.page_id = r.page_id'
    '  ORDER BY l.revision_no DESC LIMIT 1) AS latest_revision_id'
    ' FROM page_revisions r JOIN pages p ON p.id = r.page_id')


# ---- reading ------------------------------------------------------------------------

def _visible(conn: Connection, principal: Principal, version_id, what: str) -> None:
    try:
        catalog.get_version(conn, principal, version_id)
    except AppError as exc:
        if exc.status == 404:
            raise AppError(404, 'NOT_FOUND', f'{what} not found') from None
        raise


def _blocks(conn: Connection, revision_id) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        'SELECT id, ordinal, kind, bbox, start_offset, end_offset, text, table_cells,'
        ' speaker_layer, attributes FROM blocks WHERE page_revision_id = :r ORDER BY ordinal'),
        {'r': revision_id}).mappings()]


def get_revision(conn: Connection, principal: Principal, revision_id: uuid.UUID) -> dict:
    row = conn.execute(text(f'{PAGE_SELECT} WHERE r.id = :r'), {'r': revision_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Page revision not found')
    _visible(conn, principal, row['book_version_id'], 'Page revision')
    layout = row['layout'] or {}
    return {
        'id': str(row['id']), 'page_id': str(row['page_id']),
        'book_version_id': str(row['book_version_id']),
        'physical_page_number': row['physical_page_number'], 'page_kind': row['page_kind'],
        'revision_no': row['revision_no'],
        'base_revision_id': str(row['base_revision_id']) if row['base_revision_id'] else None,
        'latest_revision_id': str(row['latest_revision_id']),
        'is_latest': row['latest_revision_id'] == row['id'], 'state': row['state'],
        'printed_page_label': row['printed_page_label'],
        'printed_label_verified': row['printed_label_verified'], 'quality': row['quality'] or {},
        'layout': {k: layout.get(k) for k in ('width', 'height', 'rotation', 'page_class')},
        'text': row['normalized_text'], 'created_at': row['created_at'],
        'blocks': [{**b, 'id': str(b['id'])} for b in _blocks(conn, row['id'])]}


def _encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def _decode(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None


def list_pages(conn: Connection, principal: Principal, version_id: uuid.UUID, limit: int,
               cursor: str | None) -> tuple[list[dict], str | None]:
    """Pages of a version with their latest revision, in (kind, number) order."""
    _visible(conn, principal, version_id, 'Version')
    after = _decode(cursor)
    kind, number = after.split('|', 1) if after and '|' in after else ('', '0')
    if not number.isdigit():
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor')
    rows = conn.execute(text(
        'SELECT p.id, p.physical_page_number, p.page_kind, l.id AS revision_id, l.revision_no,'
        ' l.state, l.printed_page_label, l.printed_label_verified, l.quality'
        ' FROM pages p JOIN LATERAL (SELECT r.* FROM page_revisions r WHERE r.page_id = p.id'
        '  ORDER BY r.revision_no DESC LIMIT 1) l ON TRUE'
        ' WHERE p.book_version_id = :v AND (p.page_kind, p.physical_page_number) > (:k, :n)'
        ' ORDER BY p.page_kind, p.physical_page_number LIMIT :limit'),
        {'v': version_id, 'k': kind, 'n': int(number), 'limit': limit + 1}).mappings().all()
    page, more = rows[:limit], len(rows) > limit
    items = [{'page_id': str(r['id']), 'physical_page_number': r['physical_page_number'],
              'page_kind': r['page_kind'], 'revision_id': str(r['revision_id']),
              'revision_no': r['revision_no'], 'state': r['state'],
              'printed_page_label': r['printed_page_label'],
              'printed_label_verified': r['printed_label_verified'],
              'quality': r['quality'] or {}} for r in page]
    next_cursor = (_encode(f"{page[-1]['page_kind']}|{page[-1]['physical_page_number']}")
                   if more else None)
    return items, next_cursor


# ---- correcting ---------------------------------------------------------------------

def lock_page(conn: Connection, principal: Principal, page_id: uuid.UUID) -> dict:
    """Serialise corrections of one page; returns its latest revision id and version."""
    page = conn.execute(text('SELECT id, book_version_id FROM pages WHERE id = :p FOR UPDATE'),
                        {'p': page_id}).mappings().first()
    latest = conn.execute(text('SELECT id FROM page_revisions WHERE page_id = :p'
                               ' ORDER BY revision_no DESC LIMIT 1'), {'p': page_id}).scalar()
    if page is None or latest is None:
        raise AppError(404, 'NOT_FOUND', 'Page not found')
    _visible(conn, principal, page['book_version_id'], 'Page')
    return {'page_id': page['id'], 'book_version_id': page['book_version_id'],
            'latest_revision_id': latest}


def changed_range(old: str, new: str) -> tuple[int, int]:
    """``[start, end)`` of ``old`` replaced by the edit (empty for a pure insertion)."""
    limit = min(len(old), len(new))
    prefix = 0
    while prefix < limit and old[prefix] == new[prefix]:
        prefix += 1
    suffix = 0
    while suffix < limit - prefix and old[-1 - suffix] == new[-1 - suffix]:
        suffix += 1
    return prefix, len(old) - suffix


def _meaning(block: dict) -> tuple:
    attributes = block['attributes']
    return (block['kind'], block['speaker_layer'], attributes.get('level'), attributes.get('role'))


def apply_changes(blocks: list[dict], changes: list[dict]) -> tuple[list[dict], dict]:
    """Corrected copies of ``blocks`` and ``{ordinal: changed text range | None}``.

    ``None`` means the block's meaning changed as a whole (kind, level, role or
    speaker), so everything citing it is affected, not only edited characters.
    """
    by_ordinal = {b['ordinal']: {**b, 'attributes': dict(b['attributes'] or {})} for b in blocks}
    touched: dict[int, tuple[int, int] | None] = {}
    for change in changes:
        ordinal = change['ordinal']
        if ordinal in touched or ordinal not in by_ordinal:
            raise AppError(422, 'VALIDATION_ERROR',
                           f'block {ordinal} is not on this revision or is changed twice')
        block = by_ordinal[ordinal]
        before = {**block, 'attributes': dict(block['attributes'])}
        attributes = block['attributes']
        if change.get('text') is not None:
            new_text = normalize(change['text'])[0].strip()
            if not new_text:
                raise AppError(422, 'VALIDATION_ERROR', f'block {ordinal} cannot become empty')
            if (block['table_cells'] is not None and change.get('table_cells') is None
                    and new_text != block['text']):
                raise AppError(422, 'VALIDATION_ERROR',
                               f'block {ordinal} is a table: send table_cells with its text')
            block['text'] = new_text
        if change.get('table_cells') is not None:
            block['table_cells'] = [[normalize(cell)[0].strip() for cell in row]
                                    for row in change['table_cells']]
        if change.get('kind') is not None:
            block['kind'] = change['kind']
        if block['kind'] != 'heading':
            attributes.pop('level', None)
            attributes.pop('heading_rule', None)
        elif change.get('level') is not None or before['kind'] != 'heading':
            attributes['level'] = change.get('level') or attributes.get('level') or 2
            attributes['heading_rule'] = 'reviewer'
        if change.get('role') == 'body':
            attributes.pop('role', None)
        elif change.get('role') is not None:
            attributes['role'] = change['role']
        if change.get('speaker_layer') is not None:
            block['speaker_layer'] = change['speaker_layer']
            attributes['speaker_reviewed'] = True
        if block == before:
            touched[ordinal] = ()          # no-op change: remembered only to catch repeats
        elif _meaning(block) != _meaning(before) or block['text'] == before['text']:
            touched[ordinal] = None
        else:
            touched[ordinal] = changed_range(before['text'], block['text'])
    touched = {o: span for o, span in touched.items() if span != ()}
    if not touched:
        raise AppError(422, 'NO_CHANGE', 'The changes leave the page as it is')
    return [by_ordinal[o] for o in sorted(by_ordinal)], touched


def correct_page(conn: Connection, principal: Principal, page: dict, base_revision_id: uuid.UUID,
                 changes: list[dict], reason: str, request_id: str | None) -> dict:
    """Write the corrected revision and schedule its rebuild; ``page`` from :func:`lock_page`."""
    if page['latest_revision_id'] != base_revision_id:
        raise AppError(412, 'REVISION_MISMATCH', 'The page has a newer revision; reload it',
                       headers={'ETag': f'"{page["latest_revision_id"]}"'})
    base = conn.execute(text(
        'SELECT id, revision_no, raw_text, offset_map, layout, printed_page_label,'
        ' printed_label_verified, quality, state, rendered_object_id FROM page_revisions'
        ' WHERE id = :r'), {'r': base_revision_id}).mappings().one()
    blocks = _blocks(conn, base['id'])
    updated, touched = apply_changes(blocks, changes)
    references = [entry[2] if len(entry) > 2 else None for entry in base['offset_map'] or []]
    aligned = len(references) == len(updated)
    position, parts, offset_map = 0, [], []
    for index, block in enumerate(updated):   # blocks are joined by one blank line
        block['start_offset'], block['end_offset'] = position, position + len(block['text'])
        offset_map.append([block['start_offset'], block['end_offset'],
                           references[index] if aligned else block['ordinal']])
        parts.append(block['text'])
        position = block['end_offset'] + 2
    normalized = '\n\n'.join(parts)
    quality = {**(base['quality'] or {}),
               'correction': {'base_revision_id': str(base['id']), 'blocks': sorted(touched)}}
    revision_id = conn.execute(text(
        'INSERT INTO page_revisions (page_id, revision_no, base_revision_id, raw_text,'
        ' normalized_text, offset_map, layout, printed_page_label, printed_label_verified,'
        ' text_hash, quality, state, rendered_object_id) VALUES (:p, :no, :base, :raw, :norm,'
        ' CAST(:map AS jsonb), CAST(:layout AS jsonb), :label, :verified, :hash,'
        ' CAST(:quality AS jsonb), :state, :rendered) RETURNING id'),
        {'p': page['page_id'], 'no': base['revision_no'] + 1, 'base': base['id'],
         'raw': base['raw_text'], 'norm': normalized, 'map': json.dumps(offset_map),
         'layout': json.dumps(base['layout']), 'label': base['printed_page_label'],
         'verified': base['printed_label_verified'],
         'hash': hashlib.sha256(normalized.encode('utf-8')).hexdigest(),
         'quality': json.dumps(quality), 'state': base['state'],
         'rendered': base['rendered_object_id']}).scalar_one()
    insert = text(
        'INSERT INTO blocks (page_revision_id, ordinal, kind, bbox, start_offset, end_offset,'
        ' text, table_cells, speaker_layer, attributes) VALUES (:r, :o, :k, CAST(:b AS jsonb),'
        ' :s, :e, :t, CAST(:cells AS jsonb), :sp, CAST(:a AS jsonb))')
    for block in updated:
        conn.execute(insert, {
            'r': revision_id, 'o': block['ordinal'], 'k': block['kind'],
            'b': json.dumps(block['bbox']), 's': block['start_offset'], 'e': block['end_offset'],
            't': block['text'], 'sp': block['speaker_layer'], 'a': json.dumps(block['attributes']),
            'cells': json.dumps(block['table_cells']) if block['table_cells'] is not None else None})
    generation, job, coalesced = _schedule(conn, principal, page['book_version_id'],
                                           page['page_id'], revision_id)
    old = {b['ordinal']: b for b in blocks}
    affected = _flag_sources(conn, generation, page['page_id'], revision_id,
                             [(old[o], span) for o, span in sorted(touched.items())])
    conn.execute(text(
        "UPDATE generations SET coverage = jsonb_set(coverage, '{incremental,corrections}',"
        " coalesce(coverage #> '{incremental,corrections}', '[]'::jsonb) || CAST(:c AS jsonb))"
        ' WHERE id = :g'),
        {'g': generation, 'c': json.dumps([{
            'page_id': str(page['page_id']), 'revision_id': str(revision_id),
            'base_revision_id': str(base['id']), 'blocks': sorted(touched),
            'evidence': affected['evidence']}])})
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, 'page.correct', 'page_revision', :r, :t,"
        " CAST(:d AS jsonb), 'success')"),
        {'a': principal.user_id, 'r': revision_id, 't': request_id or '',
         'd': json.dumps({'base_revision_id': str(base['id']), 'blocks': sorted(touched),
                          'reason': reason})})
    return {'revision': {'id': str(revision_id), 'page_id': str(page['page_id']),
                         'revision_no': base['revision_no'] + 1,
                         'base_revision_id': str(base['id'])},
            'changed_blocks': sorted(touched), 'generation_id': str(generation),
            'job_id': str(job), 'coalesced': coalesced, 'source_changed': affected}


def lock_version(conn: Connection, version_id) -> None:
    """Serialise job scheduling per book version (one active job per profile)."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bazi.version.' || CAST(:v AS text)))"),
                 {'v': str(version_id)})


def _schedule(conn: Connection, principal: Principal, version_id, page_id, revision_id):
    lock_version(conn, version_id)
    base = conn.execute(text(
        "SELECT g.id, g.pipeline_profile_id FROM generations g WHERE g.book_version_id = :v"
        " AND g.state <> 'withdrawn' AND EXISTS (SELECT 1 FROM ingestion_jobs j"
        ' WHERE j.generation_id = g.id AND j.state = ANY(:done))'
        ' ORDER BY g.created_at DESC LIMIT 1'),
        {'v': version_id, 'done': FINISHED_JOB}).mappings().first()
    if base is None:
        raise AppError(409, 'NOT_PROCESSED', 'This version has no processed generation yet')
    active = conn.execute(text(
        "SELECT j.id, j.state, j.generation_id, g.coverage ? 'incremental' AS incremental"
        ' FROM ingestion_jobs j JOIN generations g ON g.id = j.generation_id'
        ' WHERE j.book_version_id = :v AND j.pipeline_profile_id = :p AND j.state = ANY(:active)'
        ' FOR UPDATE OF j'),
        {'v': version_id, 'p': base['pipeline_profile_id'], 'active': ACTIVE_JOB}).mappings().first()
    if active is not None:
        # A queued rebuild has not read its pages yet (the worker locks the job row to
        # start it): this correction joins it. A running job would miss it.
        if active['state'] == 'queued' and active['incremental']:
            conn.execute(text('DELETE FROM generation_pages WHERE generation_id = :g'
                              ' AND page_id = :p'), {'g': active['generation_id'], 'p': page_id})
            conn.execute(text('INSERT INTO generation_pages (generation_id, page_revision_id,'
                              ' page_id) VALUES (:g, :r, :p)'),
                         {'g': active['generation_id'], 'r': revision_id, 'p': page_id})
            return active['generation_id'], active['id'], True
        raise AppError(409, 'JOB_ACTIVE', 'A job of this version is running; retry the'
                       ' correction when it finishes')
    generation = conn.execute(text(
        'INSERT INTO generations (book_version_id, pipeline_profile_id, base_generation_id,'
        ' coverage) VALUES (:v, :p, :b, CAST(:c AS jsonb)) RETURNING id'),
        {'v': version_id, 'p': base['pipeline_profile_id'], 'b': base['id'],
         'c': json.dumps({'incremental': {'base_generation_id': str(base['id']),
                                          'corrections': []}})}).scalar_one()
    # Each page keeps its base link unless its newest revision is a correction
    # (earlier corrections whose own rebuild failed are carried along too).
    conn.execute(text(
        'INSERT INTO generation_pages (generation_id, page_revision_id, page_id)'
        " SELECT :g, CASE WHEN l.quality ? 'correction' THEN l.id ELSE gp.page_revision_id END,"
        ' gp.page_id FROM generation_pages gp JOIN LATERAL (SELECT r.id, r.quality'
        '  FROM page_revisions r WHERE r.page_id = gp.page_id ORDER BY r.revision_no DESC'
        '  LIMIT 1) l ON TRUE WHERE gp.generation_id = :base'),
        {'g': generation, 'base': base['id']})
    conn.execute(text('INSERT INTO generation_pages (generation_id, page_revision_id, page_id)'
                      ' VALUES (:g, :r, :p) ON CONFLICT (generation_id, page_id) DO NOTHING'),
                 {'g': generation, 'r': revision_id, 'p': page_id})
    job = conn.execute(text(
        'INSERT INTO ingestion_jobs (book_version_id, generation_id, pipeline_profile_id,'
        ' requested_by) VALUES (:v, :g, :p, :u) RETURNING id'),
        {'v': version_id, 'g': generation, 'p': base['pipeline_profile_id'],
         'u': principal.user_id}).scalar_one()
    conn.execute(text("INSERT INTO outbox_events (topic, payload) VALUES ('ingestion.job.queued',"
                      ' CAST(:p AS jsonb))'), {'p': json.dumps({'job_id': str(job)})})
    return generation, job, False


def _overlaps(start: int, end: int, span: tuple[int, int] | None) -> bool:
    if span is None:
        return True
    low, high = span
    if low == high:                  # insertion point: touches what it lands in or next to
        return start <= low <= end
    return start < high and end > low


def _flag_sources(conn: Connection, generation_id, page_id, revision_id,
                  touched: list[tuple[dict, tuple[int, int] | None]]) -> dict:
    """Evidence on the corrected characters, and review items for what cites it.

    Evidence may sit on any earlier revision of the page carrying the same block
    (OCR merges and corrections keep ordinals and copy untouched text).
    """
    evidence: set[str] = set()
    for block, span in touched:
        rows = conn.execute(text(
            'SELECT e.id, e.start_offset - b.start_offset, e.end_offset - b.start_offset'
            ' FROM evidence_spans e JOIN blocks b ON b.id = e.block_id'
            ' JOIN page_revisions r ON r.id = e.page_revision_id'
            ' WHERE r.page_id = :p AND b.ordinal = :o AND b.text = :t'),
            {'p': page_id, 'o': block['ordinal'], 't': block['text']}).all()
        evidence.update(str(eid) for eid, start, end in rows if _overlaps(start, end, span))
    affected: dict = {'evidence': sorted(evidence), 'rule': [], 'assertion': [],
                      'case_revision': []}
    if not evidence:
        return affected
    for kind, links, column, table in SOURCES:
        cited = conn.execute(text(
            f'SELECT s.{column}, array_agg(s.evidence_id::text ORDER BY s.evidence_id)'
            f' FROM {links} s JOIN {table} t ON t.id = s.{column}'
            ' WHERE s.evidence_id = ANY(CAST(:e AS uuid[])) AND t.state = ANY(:live)'
            f' GROUP BY s.{column} ORDER BY s.{column}'),
            {'e': sorted(evidence), 'live': LIVE}).all()
        for entity_id, evidence_ids in cited:
            affected[kind].append(str(entity_id))
            if conn.execute(text(
                    "SELECT 1 FROM review_items WHERE generation_id = :g AND entity_kind = :k"
                    " AND entity_id = :id AND reason_code = 'SOURCE_CHANGED'"),
                    {'g': generation_id, 'k': kind, 'id': entity_id}).first():
                continue
            conn.execute(text(
                'INSERT INTO review_items (generation_id, page_revision_id, entity_kind, entity_id,'
                " reason_code, severity, resolution) VALUES (:g, :r, :k, :id, 'SOURCE_CHANGED',"
                " 'high', CAST(:d AS jsonb))"),
                {'g': generation_id, 'r': revision_id, 'k': kind, 'id': entity_id,
                 'd': json.dumps({'evidence': evidence_ids})})
    return affected


# ---- impact -------------------------------------------------------------------------

_DIFF = {
    'page': 'SELECT gp.page_id::text FROM generation_pages gp WHERE gp.generation_id = :g'
            ' AND NOT EXISTS (SELECT 1 FROM generation_pages o WHERE o.generation_id = :b'
            ' AND o.page_id = gp.page_id AND o.page_revision_id = gp.page_revision_id)',
    'chunk_added': 'SELECT chunk_id::text FROM generation_chunks WHERE generation_id = :g'
                   ' EXCEPT SELECT chunk_id::text FROM generation_chunks WHERE generation_id = :b',
    'chunk_removed': 'SELECT chunk_id::text FROM generation_chunks WHERE generation_id = :b'
                     ' EXCEPT SELECT chunk_id::text FROM generation_chunks WHERE generation_id = :g',
    'section_added': 'SELECT path, title FROM sections WHERE generation_id = :g'
                     ' EXCEPT SELECT path, title FROM sections WHERE generation_id = :b',
    'section_removed': 'SELECT path, title FROM sections WHERE generation_id = :b'
                       ' EXCEPT SELECT path, title FROM sections WHERE generation_id = :g',
}


def impact(conn: Connection, generation_id: uuid.UUID, kind: str | None = None,
           limit: int = 100, cursor: str | None = None) -> dict:
    """What a generation changes relative to its base: counters, plus one ID list paged.

    Analyses that depend on changed sources are counted by the dependency graph
    (T024), which can see every owner's analyses; this view stays per-corpus.
    """
    gen = conn.execute(text('SELECT id, base_generation_id, state, coverage FROM generations'
                            ' WHERE id = :g'), {'g': generation_id}).mappings().first()
    if gen is None:
        raise AppError(404, 'NOT_FOUND', 'Generation not found')
    params = {'g': generation_id, 'b': gen['base_generation_id']}
    job = conn.execute(text('SELECT id, state, counters FROM ingestion_jobs WHERE generation_id = :g'
                            ' ORDER BY created_at DESC LIMIT 1'), params).mappings().first()
    counts = {key: conn.execute(text(f'SELECT count(*) FROM ({query}) q'), params).scalar_one()
              for key, query in _DIFF.items()}
    counts['chunk_reused'] = conn.execute(text(
        'SELECT count(*) FROM generation_chunks a JOIN generation_chunks b'
        ' ON b.chunk_id = a.chunk_id AND b.generation_id = :b WHERE a.generation_id = :g'),
        params).scalar_one()
    flagged = dict(conn.execute(text(
        "SELECT entity_kind, count(*) FROM review_items WHERE generation_id = :g"
        " AND reason_code = 'SOURCE_CHANGED' GROUP BY entity_kind"), params).all())
    corrections = ((gen['coverage'] or {}).get('incremental') or {}).get('corrections') or []
    evidence = sorted({e for c in corrections for e in c.get('evidence', [])})
    counts.update({key: flagged.get(key, 0) for key in ('rule', 'assertion', 'case_revision')})
    counts['evidence'] = len(evidence)
    result = {'generation_id': str(gen['id']),
              'base_generation_id': str(gen['base_generation_id'])
              if gen['base_generation_id'] else None,
              'state': gen['state'],
              'job': {'id': str(job['id']), 'state': job['state'], 'counters': job['counters']}
              if job else None,
              'counts': counts, 'kind': kind, 'ids': [], 'next_cursor': None}
    if kind is None:
        return result
    offset = _decode(cursor) or '0'
    if not offset.isdigit():
        raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor')
    start = int(offset)
    if kind == 'evidence':
        ids = evidence[start:start + limit + 1]
    elif kind in ('page', 'chunk_added', 'chunk_removed'):
        ids = conn.execute(text(f'SELECT id FROM ({_DIFF[kind]}) q(id) ORDER BY id'
                                ' LIMIT :limit OFFSET :offset'),
                           {**params, 'limit': limit + 1, 'offset': start}).scalars().all()
    else:
        ids = conn.execute(text(
            "SELECT entity_id::text FROM review_items WHERE generation_id = :g"
            " AND reason_code = 'SOURCE_CHANGED' AND entity_kind = :k ORDER BY entity_id"
            ' LIMIT :limit OFFSET :offset'),
            {**params, 'k': kind, 'limit': limit + 1, 'offset': start}).scalars().all()
    result['ids'] = list(ids[:limit])
    result['next_cursor'] = _encode(str(start + limit)) if len(ids) > limit else None
    return result
