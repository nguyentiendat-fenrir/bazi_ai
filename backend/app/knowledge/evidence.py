"""Evidence spans chosen by a reviewer (docs/04 · evidence_spans, docs/06).

A span is code-point offsets ``[start, end)`` inside one block of an immutable
page revision; its quote hash and speaker layer come from that revision and
block, never from the client, so a citation always means the text it hashes.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..documents import catalog

ORIGINS = ('source_explicit', 'editor_interpretation', 'ai_inferred')


def get_evidence(conn: Connection, principal: Principal, evidence_id) -> dict:
    row = conn.execute(text(
        'SELECT e.id, e.book_version_id, e.page_revision_id, r.page_id, p.physical_page_number,'
        ' e.block_id, e.start_offset, e.end_offset, e.speaker_layer, e.origin,'
        ' substr(r.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset) AS quote'
        ' FROM evidence_spans e JOIN page_revisions r ON r.id = e.page_revision_id'
        ' JOIN pages p ON p.id = r.page_id WHERE e.id = :i'), {'i': evidence_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Evidence not found')
    try:
        catalog.get_version(conn, principal, row['book_version_id'])
    except AppError:
        raise AppError(404, 'NOT_FOUND', 'Evidence not found') from None
    return {key: (str(value) if isinstance(value, uuid.UUID) else value)
            for key, value in dict(row).items()}


def create_evidence(conn: Connection, principal: Principal, page_revision_id, start: int,
                    end: int, origin: str = 'source_explicit') -> dict:
    revision = conn.execute(text(
        'SELECT r.id, p.book_version_id, char_length(r.normalized_text) AS length'
        ' FROM page_revisions r JOIN pages p ON p.id = r.page_id WHERE r.id = :r'),
        {'r': page_revision_id}).mappings().first()
    if revision is None:
        raise AppError(404, 'NOT_FOUND', 'Page revision not found')
    catalog.get_version(conn, principal, revision['book_version_id'])
    if not 0 <= start < end <= revision['length']:
        raise AppError(422, 'VALIDATION_ERROR', 'offsets must satisfy 0 <= start < end <= length')
    block = conn.execute(text(
        'SELECT id, speaker_layer FROM blocks WHERE page_revision_id = :r'
        ' AND start_offset <= :s AND end_offset >= :e ORDER BY ordinal LIMIT 1'),
        {'r': page_revision_id, 's': start, 'e': end}).mappings().first()
    if block is None:
        raise AppError(422, 'VALIDATION_ERROR', 'an evidence span lies inside one block;'
                       ' cite several spans for text across blocks')
    evidence_id = conn.execute(text(
        'INSERT INTO evidence_spans (book_version_id, page_revision_id, block_id, start_offset,'
        ' end_offset, quote_hash, speaker_layer, origin) SELECT :v, r.id, :b, :s, :e,'
        ' bazi_sha256_text(substr(r.normalized_text, :s + 1, :e - :s)), :sp, :o'
        ' FROM page_revisions r WHERE r.id = :r RETURNING id'),
        {'v': revision['book_version_id'], 'r': page_revision_id, 'b': block['id'], 's': start,
         'e': end, 'sp': block['speaker_layer'], 'o': origin}).scalar_one()
    return get_evidence(conn, principal, evidence_id)


def require_evidence(conn: Connection, evidence_ids: list) -> list[str]:
    ids = [str(e) for e in dict.fromkeys(evidence_ids)]
    if ids:
        found = set(conn.execute(text('SELECT id::text FROM evidence_spans'
                                      ' WHERE id = ANY(CAST(:ids AS uuid[]))'),
                                 {'ids': ids}).scalars())
        missing = [e for e in ids if e not in found]
        if missing:
            raise AppError(422, 'VALIDATION_ERROR', f'unknown evidence: {", ".join(missing)}')
    return ids


def sources_usable(conn: Connection, evidence_ids: list) -> str | None:
    """Why cited evidence may not back an approval (docs/06), or ``None``."""
    if not evidence_ids:
        return 'no source evidence'
    bad = conn.execute(text(
        "SELECT count(*) FILTER (WHERE r.state <> 'accepted'),"
        " count(*) FILTER (WHERE v.status <> 'active' OR v.rights_status = 'restricted')"
        ' FROM evidence_spans e JOIN page_revisions r ON r.id = e.page_revision_id'
        ' JOIN book_versions v ON v.id = e.book_version_id'
        ' WHERE e.id = ANY(CAST(:ids AS uuid[]))'), {'ids': [str(e) for e in evidence_ids]}).one()
    if bad[0]:
        return 'a cited page is not accepted'
    if bad[1]:
        return 'a cited book version is withdrawn or restricted'
    return None
