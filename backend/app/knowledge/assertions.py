"""Assertions as read models: list and detail with resolved evidence (docs/06, docs/10).

A source is shown from the immutable revision it cites, so the quote a
reviewer reads is exactly the text the evidence hash covers. Readers see only
approved assertions and only quotes from books they may read; drafts and
machine candidates are for reviewers.
"""
from __future__ import annotations

import base64
from datetime import datetime
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..documents.catalog import visibility_clause
from ..documents.text import fold

SELECT = (
    'SELECT a.id, a.assertion_key, a.revision, a.school_id, s.key AS school_key, a.method_id,'
    ' a.concept_id, a.statement, a.applicability, a.exception_text, a.origin, a.state,'
    ' a.author_id, a.created_at FROM assertions a JOIN schools s ON s.id = a.school_id')


def _ref(value):
    return str(value) if value is not None else None


def assertion_dto(row) -> dict:
    return {'id': str(row['id']), 'assertion_key': row['assertion_key'],
            'revision': row['revision'], 'school_id': str(row['school_id']),
            'school_key': row['school_key'], 'method_id': _ref(row['method_id']),
            'concept_id': _ref(row['concept_id']), 'statement': row['statement'],
            'applicability': row['applicability'] or {}, 'exception_text': row['exception_text'],
            'origin': row['origin'], 'state': row['state'], 'author_id': str(row['author_id']),
            'created_at': row['created_at']}


def list_assertions(conn: Connection, principal: Principal, state: str | None, school_id,
                    book_version_id, q: str | None, limit: int,
                    cursor: str | None) -> tuple[list[dict], str | None]:
    clauses, params = [], {'limit': limit + 1}
    if not principal.has_role('reviewer'):
        state = 'approved'
    if state:
        clauses.append('a.state = :state')
        params['state'] = state
    if school_id:
        clauses.append('a.school_id = :school')
        params['school'] = school_id
    if book_version_id:
        clauses.append('EXISTS (SELECT 1 FROM assertion_sources x JOIN evidence_spans e'
                       ' ON e.id = x.evidence_id WHERE x.assertion_id = a.id'
                       ' AND e.book_version_id = :version)')
        params['version'] = book_version_id
    if q:
        clauses.append("position(:q in lower(unaccent(replace(replace(a.statement, 'Đ', 'D'),"
                       " 'đ', 'd')))) > 0")
        params['q'] = fold(q)
    if cursor:
        try:
            stamp, after = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
            params.update(at=datetime.fromisoformat(stamp), after=uuid.UUID(after))
        except (ValueError, UnicodeDecodeError):
            raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None
        clauses.append('(a.created_at, a.id) > (:at, :after)')
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = conn.execute(text(f'{SELECT}{where} ORDER BY a.created_at, a.id LIMIT :limit'),
                        params).mappings().all()
    page, more = rows[:limit], len(rows) > limit
    next_cursor = (base64.urlsafe_b64encode(
        f"{page[-1]['created_at'].isoformat()}|{page[-1]['id']}".encode()).decode()
        if more else None)
    return [assertion_dto(r) for r in page], next_cursor


def sources(conn: Connection, principal: Principal, assertion_id) -> list[dict]:
    visible, params = visibility_clause(principal)
    rows = conn.execute(text(
        'SELECT x.evidence_id, x.relation, e.book_version_id, e.page_revision_id, r.page_id,'
        ' p.physical_page_number, e.block_id, e.start_offset, e.end_offset, e.speaker_layer,'
        ' e.origin, substr(r.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset)'
        ' AS quote FROM assertion_sources x JOIN evidence_spans e ON e.id = x.evidence_id'
        ' JOIN page_revisions r ON r.id = e.page_revision_id JOIN pages p ON p.id = r.page_id'
        ' JOIN book_versions v ON v.id = e.book_version_id JOIN books b ON b.id = v.book_id'
        f' WHERE x.assertion_id = :a AND b.deleted_at IS NULL AND {visible}'
        ' ORDER BY p.physical_page_number, e.start_offset'),
        {**params, 'a': assertion_id}).mappings().all()
    return [{'evidence_id': str(r['evidence_id']), 'relation': r['relation'],
             'book_version_id': str(r['book_version_id']),
             'page_revision_id': str(r['page_revision_id']), 'page_id': str(r['page_id']),
             'physical_page_number': r['physical_page_number'], 'block_id': str(r['block_id']),
             'start_offset': r['start_offset'], 'end_offset': r['end_offset'],
             'speaker_layer': r['speaker_layer'], 'origin': r['origin'], 'quote': r['quote']}
            for r in rows]


def get_assertion(conn: Connection, principal: Principal, assertion_id) -> dict:
    row = conn.execute(text(f'{SELECT} WHERE a.id = :i'), {'i': assertion_id}).mappings().first()
    if row is None or (row['state'] != 'approved' and not principal.has_role('reviewer')):
        raise AppError(404, 'NOT_FOUND', 'Assertion not found')
    relations = conn.execute(text(
        'SELECT id, from_id, to_id, relation, state FROM assertion_relations'
        ' WHERE from_id = :i OR to_id = :i ORDER BY created_at'), {'i': assertion_id}).mappings()
    return {**assertion_dto(row), 'sources': sources(conn, principal, assertion_id),
            'relations': [{'id': str(r['id']), 'from_id': str(r['from_id']),
                           'to_id': str(r['to_id']), 'relation': r['relation'],
                           'state': r['state']} for r in relations]}
