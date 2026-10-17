"""Review queue: list and resolve review items (docs/05 · quality, docs/10).

Page items (OCR, quality, labels) resolve by acting on the page's latest
revision: ``accept``/``exclude`` set its quality state, ``retry`` changes
nothing; all three schedule an incremental rebuild (as a correction does), so
chunks pick up the new state and OCR re-runs when its inputs changed (engine
installed, config). ``dismiss`` closes any item, page or knowledge, without
side effects. A reviewer names the revision they looked at; a newer one is 412.
"""
from __future__ import annotations

import base64
from datetime import datetime
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from .corrections import lock_page, schedule_rebuild

OPEN = ('open', 'in_progress')
PAGE_STATE = {'accept': 'accepted', 'exclude': 'excluded'}

SELECT = (
    'SELECT i.id, i.generation_id, i.page_revision_id, i.entity_kind, i.entity_id,'
    ' i.reason_code, i.severity, i.state, i.resolution, i.created_at, i.updated_at,'
    ' r.page_id, p.physical_page_number,'
    ' coalesce(g.book_version_id, p.book_version_id) AS book_version_id, b.title AS book_title'
    ' FROM review_items i LEFT JOIN page_revisions r ON r.id = i.page_revision_id'
    ' LEFT JOIN pages p ON p.id = r.page_id LEFT JOIN generations g ON g.id = i.generation_id'
    ' LEFT JOIN book_versions bv ON bv.id = coalesce(g.book_version_id, p.book_version_id)'
    ' LEFT JOIN books b ON b.id = bv.book_id')
SCOPES = {'page': 'i.entity_kind IS NULL AND i.page_revision_id IS NOT NULL',
          'knowledge': 'i.entity_kind IS NOT NULL'}


def _dto(row) -> dict:
    def ref(value):
        return str(value) if value is not None else None
    return {'id': str(row['id']), 'generation_id': ref(row['generation_id']),
            'page_revision_id': ref(row['page_revision_id']), 'page_id': ref(row['page_id']),
            'physical_page_number': row['physical_page_number'],
            'book_version_id': ref(row['book_version_id']), 'book_title': row['book_title'],
            'entity_kind': row['entity_kind'],
            'entity_id': ref(row['entity_id']), 'reason_code': row['reason_code'],
            'severity': row['severity'], 'state': row['state'],
            'resolution': row['resolution'] or {}, 'created_at': row['created_at'],
            'updated_at': row['updated_at']}


def list_items(conn: Connection, state: str | None, reason: str | None, book_version_id,
               generation_id, limit: int, cursor: str | None,
               scope: str | None = None) -> tuple[list[dict], str | None]:
    clauses, params = [SCOPES[scope]] if scope else [], {'limit': limit + 1}
    if state:
        clauses.append('i.state = :state')
        params['state'] = state
    if reason:
        clauses.append('i.reason_code = :reason')
        params['reason'] = reason
    if book_version_id:
        clauses.append('coalesce(g.book_version_id, p.book_version_id) = :version')
        params['version'] = book_version_id
    if generation_id:
        clauses.append('i.generation_id = :generation')
        params['generation'] = generation_id
    if cursor:
        try:
            stamp, item = base64.urlsafe_b64decode(cursor.encode()).decode().split('|')
            params.update(at=datetime.fromisoformat(stamp), after=uuid.UUID(item))
        except (ValueError, UnicodeDecodeError):
            raise AppError(422, 'VALIDATION_ERROR', 'Invalid cursor') from None
        clauses.append('(i.created_at, i.id) > (:at, :after)')
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    rows = conn.execute(text(f'{SELECT}{where} ORDER BY i.created_at, i.id LIMIT :limit'),
                        params).mappings().all()
    page, more = rows[:limit], len(rows) > limit
    next_cursor = (base64.urlsafe_b64encode(
        f"{page[-1]['created_at'].isoformat()}|{page[-1]['id']}".encode()).decode()
        if more else None)
    return [_dto(r) for r in page], next_cursor


def get_item(conn: Connection, item_id: uuid.UUID) -> dict:
    row = conn.execute(text(f'{SELECT} WHERE i.id = :i'), {'i': item_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Review item not found')
    return _dto(row)


def resolve(conn: Connection, principal: Principal, item_id: uuid.UUID, action: str,
            reason: str, base_revision_id: uuid.UUID | None, request_id: str | None) -> dict:
    item = conn.execute(text('SELECT id, state, page_revision_id, entity_kind FROM review_items'
                             ' WHERE id = :i FOR UPDATE'), {'i': item_id}).mappings().first()
    if item is None:
        raise AppError(404, 'NOT_FOUND', 'Review item not found')
    if item['state'] not in OPEN:
        raise AppError(409, 'REVIEW_CLOSED', f"The item is already {item['state']}")
    outcome = {'action': action, 'reason': reason, 'by': str(principal.user_id)}
    job = generation = None
    coalesced = False
    if action != 'dismiss':
        if item['page_revision_id'] is None or item['entity_kind'] is not None:
            raise AppError(422, 'VALIDATION_ERROR', f'{action} applies to page review items;'
                           ' knowledge items are reviewed on their entity')
        page_id = conn.execute(text('SELECT page_id FROM page_revisions WHERE id = :r'),
                               {'r': item['page_revision_id']}).scalar_one()
        page = lock_page(conn, principal, page_id)
        if base_revision_id != page['latest_revision_id']:
            raise AppError(412, 'REVISION_MISMATCH', 'The page has a newer revision; review it',
                           headers={'ETag': f'"{page["latest_revision_id"]}"'})
        if action in PAGE_STATE:
            conn.execute(text('UPDATE page_revisions SET state = :s WHERE id = :r'),
                         {'s': PAGE_STATE[action], 'r': page['latest_revision_id']})
        generation, job, coalesced = schedule_rebuild(
            conn, principal, page['book_version_id'], page_id, page['latest_revision_id'])
        outcome.update(revision_id=str(page['latest_revision_id']), job_id=str(job),
                       generation_id=str(generation))
    conn.execute(text(
        'UPDATE review_items SET state = :s, resolution = coalesce(resolution, CAST(:empty AS'
        ' jsonb)) || CAST(:o AS jsonb) WHERE id = :i'),
        {'s': 'dismissed' if action == 'dismiss' else 'resolved', 'i': item_id, 'empty': '{}',
         'o': json.dumps({'outcome': outcome})})
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, 'review.resolve', 'review_item', :i, :t,"
        " CAST(:d AS jsonb), 'success')"),
        {'a': principal.user_id, 'i': item_id, 't': request_id or '', 'd': json.dumps(outcome)})
    row = conn.execute(text(f'{SELECT} WHERE i.id = :i'), {'i': item_id}).mappings().one()
    return {'item': _dto(row), 'job_id': str(job) if job else None,
            'generation_id': str(generation) if generation else None, 'coalesced': coalesced}
