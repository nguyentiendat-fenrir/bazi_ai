"""Review decisions on knowledge entities (docs/06 · Quy trình duyệt, docs/10 ``POST /reviews``).

``submit`` (draft → in_review) and ``return`` (in_review → draft) move work
between author and reviewer; ``approve``, ``reject`` and ``revoke`` are recorded
in the append-only ``reviews`` table in the same transaction as the state
change, which the database requires. A draft may be approved or rejected
directly (it passes through in_review). The caller names the revision it
reviewed: a newer one answers 412, so two reviewers never decide on different
content. Approving a concept revision approves its canonical label and the
aliases it carried over unchanged from an approved earlier revision; approving
or revoking a school scope rebuilds the version so classifications follow.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError

# kind -> (table, has a revision column)
ENTITIES = {'method': ('methods', True), 'concept': ('concepts', True),
            'term': ('terms', False), 'school_scope': ('school_scopes', False)}
FLOW = {'submit': {'draft': ['in_review']},
        'return': {'in_review': ['draft']},
        'approve': {'draft': ['in_review', 'approved'], 'in_review': ['approved']},
        'reject': {'draft': ['in_review', 'rejected'], 'in_review': ['rejected']},
        'revoke': {'approved': ['revoked']}}
RECORDED = ('approve', 'reject', 'revoke')


def _record(conn: Connection, principal: Principal, kind: str, entity_id, decision: str,
            reason: str, base_revision: int) -> uuid.UUID:
    return conn.execute(text(
        'INSERT INTO reviews (entity_kind, entity_id, reviewer_id, decision, reason,'
        ' base_revision) VALUES (:k, :i, :u, :d, :r, :b) RETURNING id'),
        {'k': kind, 'i': entity_id, 'u': principal.user_id, 'd': decision, 'r': reason,
         'b': base_revision}).scalar_one()


def _carried_terms(conn: Connection, principal: Principal, concept_id, revision: int) -> int:
    terms = conn.execute(text(
        "SELECT t.id FROM terms t JOIN concepts c ON c.id = t.concept_id"
        " WHERE t.concept_id = :c AND t.state = 'draft' AND (t.alias_kind = 'canonical' OR EXISTS"
        ' (SELECT 1 FROM terms o JOIN concepts oc ON oc.id = o.concept_id'
        '  WHERE oc.school_id = c.school_id AND oc.canonical_key = c.canonical_key'
        "  AND oc.revision < c.revision AND o.state = 'approved' AND o.form_nfc = t.form_nfc"
        '  AND o.language = t.language AND o.alias_kind = t.alias_kind))'),
        {'c': concept_id}).scalars().all()
    for term_id in terms:
        _record(conn, principal, 'term', term_id, 'approve',
                f'approved with concept revision {revision}', 1)
        for state in ('in_review', 'approved'):
            conn.execute(text('UPDATE terms SET state = :s WHERE id = :i'),
                         {'s': state, 'i': term_id})
    return len(terms)


def _rebuild(conn: Connection, principal: Principal, scope_id) -> dict:
    from ..ingestion.jobs import process_version
    version_id = conn.execute(text('SELECT book_version_id FROM school_scopes WHERE id = :i'),
                              {'i': scope_id}).scalar_one()
    if not conn.execute(text(
            "SELECT 1 FROM generations WHERE book_version_id = :v AND state IN ('ready',"
            " 'published')"), {'v': version_id}).first():
        return {'rebuild': 'not_processed'}       # the first build classifies anyway
    try:
        with conn.begin_nested():
            job = process_version(conn, principal.user_id, version_id)
    except AppError as exc:
        return {'rebuild': exc.code}               # e.g. JOB_ACTIVE: reprocess later
    return {'rebuild': 'queued', 'job_id': job['id']}


def decide(conn: Connection, principal: Principal, kind: str, entity_id: uuid.UUID,
           decision: str, base_revision: int, reason: str, request_id: str | None) -> dict:
    if kind not in ENTITIES:
        raise AppError(422, 'VALIDATION_ERROR', f'{kind} is not reviewed through this endpoint')
    table, has_revision = ENTITIES[kind]
    row = conn.execute(text(
        f"SELECT id, state{', revision' if has_revision else ''} FROM {table}"
        ' WHERE id = :i FOR UPDATE'), {'i': entity_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', f'{kind} not found')
    current = row['revision'] if has_revision else 1
    if base_revision != current:
        raise AppError(412, 'REVISION_MISMATCH', f'{kind} is at revision {current}')
    steps = FLOW[decision].get(row['state'])
    if steps is None:
        raise AppError(409, 'INVALID_TRANSITION', f"{kind} is {row['state']}; cannot {decision}")
    review_id = (_record(conn, principal, kind, entity_id, decision, reason, current)
                 if decision in RECORDED else None)
    for state in steps:
        conn.execute(text(f'UPDATE {table} SET state = :s WHERE id = :i'),
                     {'s': state, 'i': entity_id})
    effects: dict = {}
    if kind == 'concept' and decision == 'approve':
        effects['terms_approved'] = _carried_terms(conn, principal, entity_id, current)
    if kind == 'school_scope' and decision in ('approve', 'revoke'):
        effects.update(_rebuild(conn, principal, entity_id))
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, 'knowledge.review', :k, :i, :t, CAST(:d AS jsonb),"
        " 'success')"),
        {'a': principal.user_id, 'k': kind, 'i': entity_id, 't': request_id or '',
         'd': json.dumps({'decision': decision, 'from': row['state'], 'to': steps[-1],
                          'reason': reason, 'base_revision': current})})
    return {'entity_kind': kind, 'entity_id': str(entity_id), 'state': steps[-1],
            'review_id': str(review_id) if review_id else None, **effects}
