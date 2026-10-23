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

Approval gates (docs/06): an assertion needs usable sources (accepted pages,
active versions with usable rights) and approved method/concept if it names
them; a relation needs both assertions approved; a rule needs a valid
``bazi-rule/1`` document, an approved method, usable sources, approved
dependencies and passing positive, negative and missing-fact fixtures. A
decision on a machine candidate closes its review item.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..rules import dsl as rule_dsl
from . import impact
from .cases import validate_payload
from .evidence import sources_usable
from .rules import _fixtures, coverage_problem, run_fixtures

# kind -> (table, has a revision column)
ENTITIES = {'method': ('methods', True), 'concept': ('concepts', True),
            'term': ('terms', False), 'school_scope': ('school_scopes', False),
            'assertion': ('assertions', True), 'assertion_relation': ('assertion_relations', False),
            'rule': ('knowledge_rules', True), 'case_revision': ('case_revisions', True)}
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


def _approved(conn: Connection, table: str, ids: list) -> bool:
    ids = [str(i) for i in ids if i is not None]
    return not ids or conn.execute(text(
        f"SELECT count(*) FROM {table} WHERE id = ANY(CAST(:ids AS uuid[]))"
        " AND state = 'approved'"), {'ids': ids}).scalar_one() == len(set(ids))


def _gate(conn: Connection, kind: str, entity_id) -> str | None:
    """Why ``entity_id`` cannot be approved yet, or ``None``."""
    if kind == 'assertion':
        row = conn.execute(text('SELECT method_id, concept_id FROM assertions WHERE id = :i'),
                           {'i': entity_id}).one()
        evidence = conn.execute(text('SELECT evidence_id FROM assertion_sources'
                                     ' WHERE assertion_id = :i'), {'i': entity_id}).scalars().all()
        if not _approved(conn, 'methods', [row[0]]) or not _approved(conn, 'concepts', [row[1]]):
            return 'the method or concept it names is not approved'
        return sources_usable(conn, evidence)
    if kind == 'assertion_relation':
        ends = conn.execute(text('SELECT from_id, to_id FROM assertion_relations WHERE id = :i'),
                            {'i': entity_id}).one()
        return None if _approved(conn, 'assertions', list(ends)) else \
            'both assertions must be approved first'
    if kind == 'case_revision':
        row = conn.execute(text(
            'SELECT r.chart_payload, r.method_id, c.origin FROM case_revisions r'
            ' JOIN cases c ON c.id = r.case_id WHERE r.id = :i'), {'i': entity_id}).one()
        problems = validate_payload(row[0])
        if problems:
            return '; '.join(problems)
        if not _approved(conn, 'methods', [row[1]]):
            return 'the method is not approved'
        if row[2] == 'book_case':
            evidence = conn.execute(text('SELECT evidence_id FROM case_sources'
                                         ' WHERE case_revision_id = :i'), {'i': entity_id}).scalars().all()
            return sources_usable(conn, evidence)
        return None
    if kind == 'rule':
        row = conn.execute(text('SELECT dsl, method_id FROM knowledge_rules WHERE id = :i'),
                           {'i': entity_id}).one()
        if rule_dsl.validate(row[0]):
            return 'the rule document is not valid bazi-rule/1'
        if not _approved(conn, 'methods', [row[1]]):
            return 'the method is not approved'
        evidence = conn.execute(text('SELECT evidence_id FROM rule_sources WHERE rule_id = :i'),
                                {'i': entity_id}).scalars().all()
        problem = sources_usable(conn, evidence)
        if problem:
            return problem
        requires = conn.execute(text('SELECT requires_id FROM rule_dependencies WHERE rule_id = :i'),
                                {'i': entity_id}).scalars().all()
        if not _approved(conn, 'knowledge_rules', requires):
            return 'a required rule is not approved'
        # No bridge between schools/methods exists yet, so dependencies stay inside one.
        if requires and conn.execute(text(
                'SELECT count(*) FROM knowledge_rules k, knowledge_rules me WHERE me.id = :i'
                ' AND k.id = ANY(:ids) AND (k.school_id, k.method_id)'
                ' IS DISTINCT FROM (me.school_id, me.method_id)'),
                {'i': entity_id, 'ids': list(requires)}).scalar_one():
            return 'a required rule belongs to another school or method'
        return coverage_problem(run_fixtures(row[0], _fixtures(conn, entity_id)))
    return None


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
    if decision == 'approve':
        problem = _gate(conn, kind, entity_id)
        if problem:
            raise AppError(409, 'APPROVAL_BLOCKED', f'cannot approve {kind}: {problem}')
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
    if decision == 'revoke':
        # Answers that relied on it, directly or downstream, are marked stale (docs/06).
        reached = (impact.downstream(conn, kind, entity_id) if kind in impact.ROOTS
                   else {kind: {str(entity_id)}})
        effects['analyses_stale'] = impact.mark_stale(conn, reached, f'{kind} revoked: {reason}')
    if decision in ('approve', 'reject'):
        # A decision on a machine candidate settles its review item.
        conn.execute(text(
            "UPDATE review_items SET state = :s, resolution = coalesce(resolution, '{}'::jsonb)"
            " || CAST(:o AS jsonb) WHERE entity_kind = :k AND entity_id = :i"
            " AND reason_code LIKE 'CANDIDATE%' AND state IN ('open', 'in_progress')"),
            {'s': 'resolved' if decision == 'approve' else 'dismissed', 'k': kind,
             'i': entity_id, 'o': json.dumps({'outcome': {'decision': decision,
                                                          'by': str(principal.user_id)}})})
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, 'knowledge.review', :k, :i, :t, CAST(:d AS jsonb),"
        " 'success')"),
        {'a': principal.user_id, 'k': kind, 'i': entity_id, 't': request_id or '',
         'd': json.dumps({'decision': decision, 'from': row['state'], 'to': steps[-1],
                          'reason': reason, 'base_revision': current})})
    return {'entity_kind': kind, 'entity_id': str(entity_id), 'state': steps[-1],
            'review_id': str(review_id) if review_id else None, **effects}
