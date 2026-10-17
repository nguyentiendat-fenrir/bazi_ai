"""Corpus releases: publication gates and the atomic active pointer (docs/03, 04, 05).

A release pins one generation per book version. Publishing builds a new release
from the active one with this version's generation swapped in and moves the
pointer in the same transaction, all under one corpus lock: a reader that
resolves the pointer once sees the whole old or the whole new snapshot, never a
mix, and two publications never drop each other's book.

Gates: the generation is sealed (``ready``); its version is active and not
``restricted``; every chunk has a lexical entry and a vector in the release's
collection; the embedding profile and lexical profile match the active
release; pages that are not ``accepted`` are published only when the caller
acknowledges exactly their ranges. Publication never approves knowledge.
"""
from __future__ import annotations

import base64
from collections import Counter
from datetime import datetime
import hashlib
import json
import uuid

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from ..retrieval.indexer import LEXICAL_VERSION
from ..retrieval.models import collection_for

SLOT = 'default'


def lock_corpus(conn: Connection) -> None:
    """Serialise publication and activation of the corpus slot."""
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bazi.corpus.' || CAST(:s AS text)))"),
                 {'s': SLOT})


def ranges(numbers) -> list[str]:
    """[1, 2, 3, 7] → ['1-3', '7']."""
    out: list[str] = []
    ordered = sorted(set(numbers))
    start = previous = None
    for number in ordered + [None]:
        if start is not None and number == previous + 1:
            previous = number
            continue
        if start is not None:
            out.append(str(start) if start == previous else f'{start}-{previous}')
        start = previous = number
    return out


def coverage(conn: Connection, generation_id) -> dict:
    """Page coverage of a generation; ``missing`` only for formats with a known page count."""
    known = conn.execute(text("SELECT (coverage->>'total')::int FROM generations WHERE id = :g"),
                         {'g': generation_id}).scalar()
    rows = conn.execute(text(
        'SELECT p.physical_page_number, r.state FROM generation_pages gp'
        ' JOIN pages p ON p.id = gp.page_id JOIN page_revisions r ON r.id = gp.page_revision_id'
        ' WHERE gp.generation_id = :g'), {'g': generation_id}).all()
    states = dict(rows)
    missing = [n for n in range(1, (known or 0) + 1) if n not in states]
    counts = Counter(states.values())
    return {'total': known or len(states), 'accepted': counts['accepted'],
            'review_required': counts['review_required'], 'excluded': counts['excluded'],
            'missing': len(missing),
            'excluded_ranges': ranges([n for n, s in states.items() if s != 'accepted'] + missing)}


def _index_gaps(conn: Connection, generation_id, table: str) -> tuple[int, int]:
    quoted = sql.Identifier(table).as_string(conn.connection.dbapi_connection)
    lexical = conn.execute(text(
        'SELECT count(*) FROM generation_chunks gc WHERE gc.generation_id = :g AND NOT EXISTS'
        ' (SELECT 1 FROM search_entries s WHERE s.chunk_id = gc.chunk_id'
        ' AND s.lexical_profile_version = :lv)'),
        {'g': generation_id, 'lv': LEXICAL_VERSION}).scalar_one()
    vectors = conn.execute(text(
        'SELECT count(*) FROM generation_chunks gc WHERE gc.generation_id = :g AND NOT EXISTS'
        f' (SELECT 1 FROM {quoted} e WHERE e.chunk_id = gc.chunk_id)'),
        {'g': generation_id}).scalar_one()
    return lexical, vectors


def _manifest(conn: Connection, release_id) -> str:
    head = conn.execute(text('SELECT embedding_collection_id, ontology_release_id,'
                             ' lexical_profile_version FROM corpus_releases WHERE id = :r'),
                        {'r': release_id}).one()
    members = conn.execute(text(
        'SELECT m.book_version_id::text, m.generation_id::text, g.manifest_hash'
        ' FROM corpus_members m JOIN generations g ON g.id = m.generation_id'
        ' WHERE m.release_id = :r ORDER BY m.book_version_id'), {'r': release_id}).all()
    material = json.dumps([str(head[0]), str(head[1]), head[2],
                           [[v, g, h.strip()] for v, g, h in members]], separators=(',', ':'))
    return hashlib.sha256(material.encode()).hexdigest()


def _audit(conn: Connection, actor_id, action: str, release_id, request_id, diff: dict) -> None:
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, :action, 'corpus_release', :r, :t,"
        " CAST(:d AS jsonb), 'success')"),
        {'a': actor_id, 'action': action, 'r': release_id, 't': request_id or '',
         'd': json.dumps(diff)})


def publish(conn: Connection, actor_id, generation_id, allow_partial: bool = False,
            ack_excluded_ranges=(), activate: bool = True, request_id: str | None = None) -> dict:
    lock_corpus(conn)
    gen = conn.execute(text(
        'SELECT g.id, g.book_version_id, g.state, v.status AS version_status, v.rights_status,'
        ' p.embedding_profile_id FROM generations g JOIN book_versions v ON v.id = g.book_version_id'
        ' JOIN pipeline_profiles p ON p.id = g.pipeline_profile_id WHERE g.id = :g FOR UPDATE OF g'),
        {'g': generation_id}).mappings().first()
    if gen is None:
        raise AppError(404, 'NOT_FOUND', 'Generation not found')
    if gen['state'] != 'ready':
        raise AppError(409, 'GENERATION_NOT_READY',
                       f"Generation is {gen['state']}; only a sealed (ready) one can be published")
    if gen['version_status'] != 'active':
        raise AppError(409, 'VERSION_WITHDRAWN', 'This book version is withdrawn')
    if gen['rights_status'] == 'restricted':
        raise AppError(409, 'RIGHTS_RESTRICTED', 'Rights status restricted forbids publication')
    pages = coverage(conn, generation_id)
    if pages['accepted'] == 0:
        raise AppError(409, 'NOTHING_TO_PUBLISH', 'No accepted page in this generation')
    if pages['excluded_ranges'] and not (
            allow_partial and list(ack_excluded_ranges) == pages['excluded_ranges']):
        raise AppError(409, 'PARTIAL_NOT_ACKNOWLEDGED',
                       'Pages not accepted: ' + ', '.join(pages['excluded_ranges']) +
                       '; resend with allow_partial and ack_excluded_ranges equal to these ranges')
    table = collection_for(conn, gen['embedding_profile_id'])
    if table is None:
        raise AppError(409, 'INDEX_INCOMPLETE', 'The embedding collection is not provisioned')
    collection_id = conn.execute(text(
        "SELECT id FROM embedding_collections WHERE profile_id = :p AND state = 'ready'"),
        {'p': gen['embedding_profile_id']}).scalar_one()
    lexical, vectors = _index_gaps(conn, generation_id, table)
    if lexical or vectors:
        raise AppError(409, 'INDEX_INCOMPLETE',
                       f'{lexical} chunks lack lexical entries and {vectors} lack vectors')
    active = conn.execute(text(
        'SELECT a.release_id, r.embedding_collection_id, r.ontology_release_id,'
        ' r.lexical_profile_version FROM active_corpus a JOIN corpus_releases r'
        ' ON r.id = a.release_id WHERE a.slot = :s FOR UPDATE OF a'), {'s': SLOT}).mappings().first()
    if active and active['embedding_collection_id'] != collection_id:
        raise AppError(409, 'EMBEDDING_PROFILE_MISMATCH', 'The active release uses another'
                       ' embedding profile; switching profiles needs a full new release')
    if active and active['lexical_profile_version'] != LEXICAL_VERSION:
        raise AppError(409, 'LEXICAL_PROFILE_MISMATCH', 'The active release uses another'
                       ' lexical profile')
    ontology = active['ontology_release_id'] if active else conn.execute(text(
        "SELECT id FROM ontology_releases WHERE state = 'published'"
        ' ORDER BY created_at DESC LIMIT 1')).scalar()
    if ontology is None:
        raise AppError(409, 'ONTOLOGY_MISSING', 'No published ontology release')
    parent = active['release_id'] if active else None
    release_id = conn.execute(text(
        'INSERT INTO corpus_releases (parent_id, embedding_collection_id, ontology_release_id,'
        ' lexical_profile_version) VALUES (:p, :c, :o, :lv) RETURNING id'),
        {'p': parent, 'c': collection_id, 'o': ontology, 'lv': LEXICAL_VERSION}).scalar_one()
    if parent:
        # Withdrawn versions and generations drop out instead of being carried along.
        conn.execute(text(
            'INSERT INTO corpus_members (release_id, book_version_id, generation_id)'
            ' SELECT :r, m.book_version_id, m.generation_id FROM corpus_members m'
            ' JOIN generations g ON g.id = m.generation_id'
            ' JOIN book_versions v ON v.id = m.book_version_id'
            " WHERE m.release_id = :parent AND m.book_version_id <> :v"
            " AND g.state IN ('ready', 'published') AND v.status = 'active'"),
            {'r': release_id, 'parent': parent, 'v': gen['book_version_id']})
    conn.execute(text('INSERT INTO corpus_members (release_id, book_version_id, generation_id)'
                      ' VALUES (:r, :v, :g)'),
                 {'r': release_id, 'v': gen['book_version_id'], 'g': generation_id})
    conn.execute(text("UPDATE corpus_releases SET state = 'ready', manifest_hash = :m"
                      ' WHERE id = :r'), {'r': release_id, 'm': _manifest(conn, release_id)})
    conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                      ' WHERE id = :g'),
                 {'g': generation_id, 'c': json.dumps({'publication': {
                     **pages, 'release_id': str(release_id),
                     'acknowledged_partial': bool(pages['excluded_ranges'])}})})
    _audit(conn, actor_id, 'corpus.publish', release_id, request_id,
           {'generation_id': str(generation_id), 'parent_id': str(parent) if parent else None,
            'excluded_ranges': pages['excluded_ranges']})
    if activate:
        activate_release(conn, actor_id, release_id, parent, request_id)
    return {'release': get_release(conn, release_id), 'activated': activate, 'coverage': pages}


def activate_release(conn: Connection, actor_id, release_id, expected_active_id,
                     request_id: str | None = None) -> dict:
    """Compare-and-swap the active pointer to a ready release."""
    lock_corpus(conn)
    current = conn.execute(text('SELECT release_id FROM active_corpus WHERE slot = :s FOR UPDATE'),
                           {'s': SLOT}).scalar()
    release = conn.execute(text('SELECT state FROM corpus_releases WHERE id = :r FOR UPDATE'),
                           {'r': release_id}).scalar()
    if release is None:
        raise AppError(404, 'NOT_FOUND', 'Corpus release not found')
    if current == release_id:
        return get_release(conn, release_id)        # already active: a retried request
    if current != expected_active_id:
        raise AppError(409, 'ACTIVE_CHANGED',
                       f'The active release is {current or "none"}; reload and confirm again')
    if release != 'ready':
        raise AppError(409, 'RELEASE_NOT_READY', f'Release is {release}; only ready ones activate')
    conn.execute(text("UPDATE corpus_releases SET state = 'active' WHERE id = :r"),
                 {'r': release_id})
    if current is None:
        conn.execute(text('INSERT INTO active_corpus (slot, release_id) VALUES (:s, :r)'),
                     {'s': SLOT, 'r': release_id})
    else:
        conn.execute(text('UPDATE active_corpus SET release_id = :r WHERE slot = :s'),
                     {'s': SLOT, 'r': release_id})
        conn.execute(text("UPDATE corpus_releases SET state = 'retired' WHERE id = :r"),
                     {'r': current})
    # Generation states follow membership of the active release (history keeps its own).
    conn.execute(text(
        "UPDATE generations SET state = 'published' WHERE state = 'ready' AND id IN"
        ' (SELECT generation_id FROM corpus_members WHERE release_id = :r)'), {'r': release_id})
    if current is not None:
        conn.execute(text(
            "UPDATE generations SET state = 'superseded' WHERE state = 'published' AND id IN"
            ' (SELECT generation_id FROM corpus_members WHERE release_id = :old) AND id NOT IN'
            ' (SELECT generation_id FROM corpus_members WHERE release_id = :r)'),
            {'r': release_id, 'old': current})
    _audit(conn, actor_id, 'corpus.activate', release_id, request_id,
           {'from': str(current) if current else None, 'to': str(release_id)})
    return get_release(conn, release_id)


# ---- reading ------------------------------------------------------------------------

RELEASE_SELECT = (
    'SELECT r.id, r.parent_id, r.state, r.manifest_hash, r.embedding_collection_id,'
    ' r.ontology_release_id, r.lexical_profile_version, r.created_at,'
    ' (SELECT count(*) FROM corpus_members m WHERE m.release_id = r.id) AS members_count,'
    ' EXISTS (SELECT 1 FROM active_corpus a WHERE a.release_id = r.id) AS active'
    ' FROM corpus_releases r')


def _release_dto(row) -> dict:
    return {'id': str(row['id']), 'parent_id': str(row['parent_id']) if row['parent_id'] else None,
            'state': row['state'],
            'manifest_hash': row['manifest_hash'].strip() if row['manifest_hash'] else None,
            'embedding_collection_id': str(row['embedding_collection_id']),
            'ontology_release_id': str(row['ontology_release_id']),
            'lexical_profile_version': row['lexical_profile_version'],
            'created_at': row['created_at'], 'members_count': row['members_count'],
            'active': row['active']}


def get_release(conn: Connection, release_id, members: bool = False) -> dict:
    row = conn.execute(text(f'{RELEASE_SELECT} WHERE r.id = :r'),
                       {'r': release_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Corpus release not found')
    dto = _release_dto(row)
    if members:
        dto['members'] = [{'book_version_id': str(v), 'generation_id': str(g)} for v, g in
                          conn.execute(text(
                              'SELECT book_version_id, generation_id FROM corpus_members'
                              ' WHERE release_id = :r ORDER BY book_version_id'),
                              {'r': release_id})]
    return dto


def list_releases(conn: Connection, limit: int, cursor: str | None) -> tuple[dict, str | None]:
    after = None
    if cursor:
        try:
            stamp, release = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
            after = (datetime.fromisoformat(stamp), uuid.UUID(release))
        except (ValueError, UnicodeDecodeError):
            raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None
    where = ' WHERE (r.created_at, r.id) < (:at, :id)' if after else ''
    rows = conn.execute(text(f'{RELEASE_SELECT}{where} ORDER BY r.created_at DESC, r.id DESC'
                             ' LIMIT :limit'),
                        {'limit': limit + 1, **({'at': after[0], 'id': after[1]} if after else {})}
                        ).mappings().all()
    page, more = rows[:limit], len(rows) > limit
    active = conn.execute(text('SELECT release_id, visibility_epoch FROM active_corpus'
                               ' WHERE slot = :s'), {'s': SLOT}).first()
    view = {'active': {'release_id': str(active[0]), 'visibility_epoch': active[1]}
            if active else None,
            'releases': [_release_dto(r) for r in page]}
    next_cursor = (base64.urlsafe_b64encode(
        f"{page[-1]['created_at'].isoformat()}|{page[-1]['id']}".encode()).decode()
        if more else None)
    return view, next_cursor


def generation_view(conn: Connection, generation_id) -> dict:
    gen = conn.execute(text(
        'SELECT id, book_version_id, pipeline_profile_id, base_generation_id, state,'
        ' manifest_hash, created_at FROM generations WHERE id = :g'),
        {'g': generation_id}).mappings().first()
    if gen is None:
        raise AppError(404, 'NOT_FOUND', 'Generation not found')
    job = conn.execute(text('SELECT id, state, counters FROM ingestion_jobs WHERE generation_id = :g'
                            ' ORDER BY created_at DESC LIMIT 1'),
                       {'g': generation_id}).mappings().first()
    reviews = dict(conn.execute(text(
        "SELECT severity, count(*) FROM review_items WHERE generation_id = :g"
        " AND state IN ('open', 'in_progress') GROUP BY severity"), {'g': generation_id}).all())
    releases = conn.execute(text(
        'SELECT m.release_id, EXISTS (SELECT 1 FROM active_corpus a WHERE a.release_id ='
        ' m.release_id) FROM corpus_members m WHERE m.generation_id = :g'),
        {'g': generation_id}).all()
    return {
        'id': str(gen['id']), 'book_version_id': str(gen['book_version_id']),
        'pipeline_profile_id': str(gen['pipeline_profile_id']),
        'base_generation_id': str(gen['base_generation_id']) if gen['base_generation_id'] else None,
        'state': gen['state'],
        'manifest_hash': gen['manifest_hash'].strip() if gen['manifest_hash'] else None,
        'created_at': gen['created_at'], 'coverage': coverage(conn, generation_id),
        'open_review_items': reviews,
        'job': {'id': str(job['id']), 'state': job['state'], 'counters': job['counters']}
        if job else None,
        'release_ids': [str(r) for r, _ in releases],
        'in_active_release': any(active for _, active in releases)}
