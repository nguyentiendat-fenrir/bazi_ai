"""School scopes of book versions and the chunk classifications they produce (docs/06).

A reviewer assigns the school a version speaks for, or the school of an inclusive
page range inside it (an appendix quoting another school). Page ranges must not
overlap each other; the version-wide scope is the fallback. When a generation is
chunked, every chunk gets the school of the narrowest approved scope covering its
first page, as a ``reviewed`` classification of that generation — retrieval
filters on it, and a later scope change needs a new generation (no drift).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..documents import catalog
from ..documents.text import nfc

CLASSIFICATION_VERSION = 'school-scope-1'
LIVE = ['draft', 'in_review', 'approved']

SELECT = ('SELECT sc.id, sc.book_version_id, sc.school_id, s.key AS school_key, sc.first_page,'
          ' sc.last_page, sc.state, sc.reason, sc.created_by, sc.created_at'
          ' FROM school_scopes sc JOIN schools s ON s.id = sc.school_id')


def scope_dto(row) -> dict:
    return {'id': str(row['id']), 'book_version_id': str(row['book_version_id']),
            'school_id': str(row['school_id']), 'school_key': row['school_key'],
            'first_page': row['first_page'], 'last_page': row['last_page'],
            'state': row['state'], 'reason': row['reason'],
            'created_by': str(row['created_by']), 'created_at': row['created_at']}


def list_scopes(conn: Connection, principal: Principal, version_id) -> list[dict]:
    catalog.get_version(conn, principal, version_id)
    return [scope_dto(r) for r in conn.execute(text(
        f'{SELECT} WHERE sc.book_version_id = :v ORDER BY sc.first_page NULLS FIRST,'
        ' sc.created_at'), {'v': version_id}).mappings()]


def create_scope(conn: Connection, principal: Principal, version_id, school_id,
                 first_page: int | None, last_page: int | None, reason: str) -> dict:
    catalog.get_version(conn, principal, version_id)
    if not conn.execute(text('SELECT 1 FROM schools WHERE id = :s'), {'s': school_id}).first():
        raise AppError(404, 'NOT_FOUND', 'School not found')
    if (first_page is None) != (last_page is None) or (
            first_page is not None and not 1 <= first_page <= last_page):
        raise AppError(422, 'VALIDATION_ERROR', 'give both first_page and last_page'
                       ' (1 <= first <= last) or neither for the whole version')
    conn.execute(text('SELECT 1 FROM book_versions WHERE id = :v FOR UPDATE'), {'v': version_id})
    if first_page is None:
        clash = conn.execute(text(
            'SELECT 1 FROM school_scopes WHERE book_version_id = :v AND first_page IS NULL'
            ' AND state = ANY(:live)'), {'v': version_id, 'live': LIVE}).first()
    else:
        clash = conn.execute(text(
            'SELECT 1 FROM school_scopes WHERE book_version_id = :v AND first_page IS NOT NULL'
            ' AND state = ANY(:live) AND first_page <= :last AND last_page >= :first'),
            {'v': version_id, 'live': LIVE, 'first': first_page, 'last': last_page}).first()
    if clash:
        raise AppError(409, 'CONFLICT', 'A live scope already covers these pages; reject or'
                       ' revoke it first')
    scope_id = conn.execute(text(
        'INSERT INTO school_scopes (book_version_id, school_id, first_page, last_page, reason,'
        ' created_by) VALUES (:v, :s, :f, :l, :r, :u) RETURNING id'),
        {'v': version_id, 's': school_id, 'f': first_page, 'l': last_page,
         'r': nfc(reason).strip(), 'u': principal.user_id}).scalar_one()
    return scope_dto(conn.execute(text(f'{SELECT} WHERE sc.id = :i'),
                                  {'i': scope_id}).mappings().one())


def classify(conn: Connection, generation_id, version_id) -> int:
    """School classification of a building generation's chunks from approved scopes."""
    return conn.execute(text(
        'INSERT INTO chunk_classifications (chunk_id, generation_id, school_id, status,'
        ' confidence, classification_version)'
        " SELECT f.chunk_id, :g, f.school_id, 'reviewed', 1, :cv FROM ("
        '  SELECT first.chunk_id, (SELECT sc.school_id FROM school_scopes sc'
        "   WHERE sc.book_version_id = :v AND sc.state = 'approved' AND (sc.first_page IS NULL"
        '   OR first.page BETWEEN sc.first_page AND sc.last_page)'
        '   ORDER BY sc.first_page IS NULL, sc.last_page - sc.first_page LIMIT 1) AS school_id'
        '  FROM (SELECT gc.chunk_id, min(p.physical_page_number) AS page'
        '   FROM generation_chunks gc JOIN chunk_spans s ON s.chunk_id = gc.chunk_id'
        '   JOIN page_revisions r ON r.id = s.page_revision_id JOIN pages p ON p.id = r.page_id'
        '   WHERE gc.generation_id = :g GROUP BY gc.chunk_id) first) f'
        ' WHERE f.school_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM chunk_classifications x'
        '  WHERE x.generation_id = :g AND x.chunk_id = f.chunk_id'
        '  AND x.classification_version = :cv)'),
        {'g': generation_id, 'v': version_id, 'cv': CLASSIFICATION_VERSION}).rowcount
