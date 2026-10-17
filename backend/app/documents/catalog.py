"""Books, authors, versions and access grants (docs/04 M002, docs/10 books).

Visibility: reviewers and admins work on the whole library; readers see a book
only through a ``read`` grant to themselves or to their role. Versions are
private by default — the uploader gets ``manage``, reviewers get ``review``.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from .text import fold, nfc

AUTHOR_ROLES = ('author', 'commentator', 'translator', 'editor')
ROLE_ORDER = {'reader': 0, 'reviewer': 1, 'admin': 2}


def visibility_clause(principal: Principal, alias: str = 'b') -> tuple[str, dict]:
    """SQL condition (and params) selecting the books ``principal`` may read."""
    if principal.has_role('reviewer'):
        return 'TRUE', {}
    roles = [r for r, rank in ROLE_ORDER.items() if rank <= ROLE_ORDER[principal.role]]
    return (f'EXISTS (SELECT 1 FROM book_access a WHERE a.book_id = {alias}.id'
            " AND a.permission IN ('read', 'review', 'manage')"
            ' AND (a.user_id = :viewer OR a.role_scope = ANY(:viewer_roles)))',
            {'viewer': principal.user_id, 'viewer_roles': roles})


def _authors(conn: Connection, book_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    rows = conn.execute(text(
        'SELECT ba.book_id, a.id, a.name, ba.role FROM book_authors ba'
        ' JOIN authors a ON a.id = ba.author_id WHERE ba.book_id = ANY(:ids)'
        ' ORDER BY ba.book_id, ba.ordinal'), {'ids': book_ids}).mappings()
    result: dict[uuid.UUID, list[dict]] = {}
    for r in rows:
        result.setdefault(r['book_id'], []).append(
            {'id': str(r['id']), 'name': r['name'], 'role': r['role']})
    return result


def _active_coverage(conn: Connection, book_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Page coverage summed over each book's versions in the active corpus release."""
    rows = conn.execute(text(
        'SELECT v.book_id, g.coverage FROM active_corpus a'
        ' JOIN corpus_members m ON m.release_id = a.release_id'
        ' JOIN book_versions v ON v.id = m.book_version_id'
        " JOIN generations g ON g.id = m.generation_id WHERE a.slot = 'default'"
        ' AND v.book_id = ANY(:ids)'), {'ids': book_ids}).mappings()
    result: dict[uuid.UUID, dict] = {}
    for r in rows:
        total = result.setdefault(r['book_id'], {'versions': 0, 'total': 0, 'accepted': 0,
                                                 'review_required': 0, 'excluded': 0})
        total['versions'] += 1
        for key in ('total', 'accepted', 'review_required', 'excluded'):
            total[key] += int((r['coverage'] or {}).get(key) or 0)
    return result


def book_dtos(conn: Connection, rows: list) -> list[dict]:
    ids = [r['id'] for r in rows]
    authors, coverage = _authors(conn, ids), _active_coverage(conn, ids)
    return [{'id': str(r['id']), 'title': r['title'], 'language': r['language'],
             'description': r['description'], 'authors': authors.get(r['id'], []),
             'versions_count': r['versions_count'], 'active_coverage': coverage.get(r['id']),
             'revision': r['revision']} for r in rows]


BOOK_SELECT = ('SELECT b.id, b.title, b.language, b.description, b.revision, b.created_at,'
               ' (SELECT count(*) FROM book_versions v WHERE v.book_id = b.id) AS versions_count'
               ' FROM books b')


def list_books(conn: Connection, principal: Principal, q: str | None, limit: int,
               after: tuple | None) -> list[dict]:
    where, params = visibility_clause(principal)
    clauses = ['b.deleted_at IS NULL', where]
    if q:
        clauses.append('b.normalized_title LIKE :q')
        params['q'] = f'%{fold(q)}%'
    if after:
        clauses.append('(b.created_at, b.id) > (:after_ts, :after_id)')
        params.update(after_ts=after[0], after_id=after[1])
    rows = conn.execute(text(
        f'{BOOK_SELECT} WHERE {" AND ".join(clauses)} ORDER BY b.created_at, b.id LIMIT :limit'),
        {**params, 'limit': limit}).mappings().all()
    return rows


def get_book(conn: Connection, principal: Principal, book_id: uuid.UUID) -> dict:
    where, params = visibility_clause(principal)
    row = conn.execute(text(f'{BOOK_SELECT} WHERE b.id = :id AND b.deleted_at IS NULL'
                            f' AND {where}'), {**params, 'id': book_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Book not found')  # hides existence of private books
    return book_dtos(conn, [row])[0]


def _author_id(conn: Connection, name: str) -> uuid.UUID:
    name = nfc(name).strip()
    existing = conn.execute(text('SELECT id FROM authors WHERE normalized_name = :n AND name = :name'
                                 ' ORDER BY created_at LIMIT 1'),
                            {'n': fold(name), 'name': name}).scalar()
    return existing or conn.execute(text(
        'INSERT INTO authors (name, normalized_name) VALUES (:name, :n) RETURNING id'),
        {'name': name, 'n': fold(name)}).scalar_one()


def create_book(conn: Connection, principal: Principal, title: str, language: str,
                description: str | None, authors: list[dict]) -> uuid.UUID:
    title = nfc(title).strip()
    book_id = conn.execute(text(
        'INSERT INTO books (title, normalized_title, language, description, created_by)'
        ' VALUES (:title, :norm, :language, :description, :user) RETURNING id'),
        {'title': title, 'norm': fold(title), 'language': language,
         'description': nfc(description) if description else None,
         'user': principal.user_id}).scalar_one()
    for ordinal, author in enumerate(authors):
        conn.execute(text('INSERT INTO book_authors (book_id, author_id, role, ordinal)'
                          ' VALUES (:book, :author, :role, :ordinal) ON CONFLICT DO NOTHING'),
                     {'book': book_id, 'author': _author_id(conn, author['name']),
                      'role': author['role'], 'ordinal': ordinal})
    # Private by default: the creator manages it, reviewers may review it.
    conn.execute(text("INSERT INTO book_access (book_id, user_id, role_scope, permission)"
                      " VALUES (:book, :user, NULL, 'manage'), (:book, NULL, 'reviewer', 'review')"
                      ' ON CONFLICT DO NOTHING'), {'book': book_id, 'user': principal.user_id})
    return book_id


def update_book(conn: Connection, book_id: uuid.UUID, changes: dict) -> None:
    allowed = {k: v for k, v in changes.items()
               if k in ('title', 'language', 'description') and v is not None}
    if 'title' in allowed:
        allowed['title'] = nfc(allowed['title']).strip()
        allowed['normalized_title'] = fold(allowed['title'])
    if not allowed:
        return
    assignments = ', '.join(f'{k} = :{k}' for k in allowed)
    conn.execute(text(f'UPDATE books SET {assignments}, revision = revision + 1 WHERE id = :id'),
                 {**allowed, 'id': book_id})


def book_revision(conn: Connection, book_id: uuid.UUID) -> int | None:
    return conn.execute(text('SELECT revision FROM books WHERE id = :id AND deleted_at IS NULL'
                             ' FOR UPDATE'), {'id': book_id}).scalar()


def list_access(conn: Connection, book_id: uuid.UUID) -> list[dict]:
    return [{'user_id': str(r['user_id']) if r['user_id'] else None,
             'role_scope': r['role_scope'], 'permission': r['permission']}
            for r in conn.execute(text(
                'SELECT user_id, role_scope, permission FROM book_access WHERE book_id = :b'
                ' ORDER BY role_scope NULLS FIRST, user_id, permission'),
                {'b': book_id}).mappings()]


def replace_access(conn: Connection, principal: Principal, book_id: uuid.UUID,
                   grants: list[dict], request_id: str | None) -> None:
    before = list_access(conn, book_id)
    conn.execute(text('DELETE FROM book_access WHERE book_id = :b'), {'b': book_id})
    for grant in grants:
        conn.execute(text('INSERT INTO book_access (book_id, user_id, role_scope, permission)'
                          ' VALUES (:b, :u, :r, :p) ON CONFLICT DO NOTHING'),
                     {'b': book_id, 'u': grant.get('user_id'), 'r': grant.get('role_scope'),
                      'p': grant['permission']})
    # The book revision guards concurrent edits (If-Match); access changes invalidate
    # cached retrieval immediately (docs/05 withdrawal).
    conn.execute(text('UPDATE books SET revision = revision + 1 WHERE id = :b'), {'b': book_id})
    conn.execute(text('UPDATE active_corpus SET visibility_epoch = visibility_epoch + 1'))
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:actor, 'book.access.replace', 'book', :b, :trace,"
        " CAST(:diff AS jsonb), 'success')"),
        {'actor': principal.user_id, 'b': book_id, 'trace': request_id or '',
         'diff': json.dumps({'before': before, 'after': list_access(conn, book_id)})})


VERSION_SELECT = (
    'SELECT v.id, v.book_id, v.edition_label, v.version_no, v.status, v.rights_status,'
    ' v.external_processing_allowed, v.created_at, o.sha256, o.size_bytes, o.detected_mime,'
    ' g.id AS generation_id, g.coverage'
    ' FROM book_versions v JOIN objects o ON o.id = v.object_id'
    ' LEFT JOIN LATERAL (SELECT id, coverage FROM generations WHERE book_version_id = v.id'
    '   ORDER BY created_at DESC LIMIT 1) g ON TRUE')


def version_dto(row) -> dict:
    coverage = row['coverage'] or {}
    return {'id': str(row['id']), 'book_id': str(row['book_id']),
            'edition_label': row['edition_label'], 'version_no': row['version_no'],
            'sha256': row['sha256'].strip(), 'size_bytes': row['size_bytes'],
            'mime': row['detected_mime'], 'status': row['status'],
            'rights_status': row['rights_status'],
            'external_processing_allowed': row['external_processing_allowed'],
            'coverage': {k: int(coverage.get(k, 0))
                         for k in ('total', 'accepted', 'excluded', 'failed')},
            'current_generation_id': str(row['generation_id']) if row['generation_id'] else None}


def list_versions(conn: Connection, book_id: uuid.UUID) -> list[dict]:
    return [version_dto(r) for r in conn.execute(text(
        f'{VERSION_SELECT} WHERE v.book_id = :b ORDER BY v.version_no'), {'b': book_id}).mappings()]


def get_version(conn: Connection, principal: Principal, version_id: uuid.UUID) -> dict:
    row = conn.execute(text(f'{VERSION_SELECT} WHERE v.id = :id'), {'id': version_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Version not found')
    get_book(conn, principal, row['book_id'])  # same visibility as its book
    return version_dto(row)
