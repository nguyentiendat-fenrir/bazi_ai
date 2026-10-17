"""Rulesets: frozen snapshots of approved rules per school and method (docs/06, docs/08 · B).

* Build: the named approved revisions (default: the latest approved revision of every
  rule of the school/method), checked as a dependency graph — every ``requires`` must be
  a member and no cycle may exist — then frozen with a manifest hash. The database
  refuses members that are not approved rules of the same school and method.
* Activate: compare-and-swap of the published ruleset of that school/method; the one it
  replaces is retired and every analysis that used it becomes stale.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from ..rules.engine import Member, RuleGraphError, order
from . import impact

SELECT = (
    'SELECT r.id, r.school_id, s.key AS school_key, r.method_id, m.key AS method_key,'
    ' r.version, r.state, r.manifest_hash, r.created_at,'
    ' (SELECT count(*) FROM ruleset_members x WHERE x.ruleset_id = r.id) AS members_count'
    ' FROM rulesets r JOIN schools s ON s.id = r.school_id JOIN methods m ON m.id = r.method_id')


def _dto(row) -> dict:
    return {'id': str(row.id), 'school_id': str(row.school_id), 'school_key': row.school_key,
            'method_id': str(row.method_id), 'method_key': row.method_key,
            'version': row.version, 'state': row.state,
            'manifest_hash': row.manifest_hash.strip() if row.manifest_hash else None,
            'members_count': row.members_count, 'created_at': row.created_at}


def members(conn: Connection, ruleset_id) -> list[Member]:
    rows = conn.execute(text(
        'SELECT k.id, k.rule_key, k.dsl, x.ordinal,'
        ' coalesce(array_agg(rs.evidence_id ORDER BY rs.evidence_id)'
        ' FILTER (WHERE rs.evidence_id IS NOT NULL), ARRAY[]::uuid[]) AS evidence'
        ' FROM ruleset_members x JOIN knowledge_rules k ON k.id = x.rule_id'
        ' LEFT JOIN rule_sources rs ON rs.rule_id = k.id WHERE x.ruleset_id = :r'
        ' GROUP BY k.id, k.rule_key, k.dsl, x.ordinal ORDER BY x.ordinal'), {'r': ruleset_id}).all()
    return [Member(str(r.id), r.rule_key, r.dsl, r.ordinal, tuple(str(e) for e in r.evidence))
            for r in rows]


def get_ruleset(conn: Connection, ruleset_id) -> dict:
    row = conn.execute(text(f'{SELECT} WHERE r.id = :i'), {'i': ruleset_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Ruleset not found')
    return {**_dto(row), 'members': [{'revision_id': m.revision_id, 'rule_key': m.rule_key,
                                      'ordinal': m.ordinal} for m in members(conn, ruleset_id)]}


def list_rulesets(conn: Connection, school_id, method_id, state: str | None) -> list[dict]:
    clauses, params = [], {}
    for column, value in (('r.school_id', school_id), ('r.method_id', method_id),
                          ('r.state', state)):
        if value is not None:
            name = column.split('.')[1]
            clauses.append(f'{column} = :{name}')
            params[name] = value
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    return [_dto(r) for r in conn.execute(text(f'{SELECT}{where} ORDER BY r.created_at DESC'),
                                          params).all()]


def build(conn: Connection, school_id, method_id, version: str,
          revision_ids: list | None) -> dict:
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:k))'),
                 {'k': f'ruleset:{school_id}:{method_id}'})
    if revision_ids is None:
        rows = conn.execute(text(
            "SELECT DISTINCT ON (rule_key) id, rule_key, dsl FROM knowledge_rules"
            " WHERE school_id = :s AND method_id = :m AND state = 'approved'"
            ' ORDER BY rule_key, revision DESC'), {'s': school_id, 'm': method_id}).all()
    else:
        rows = conn.execute(text(
            'SELECT id, rule_key, dsl, state, school_id, method_id FROM knowledge_rules'
            ' WHERE id = ANY(CAST(:ids AS uuid[]))'),
            {'ids': [str(i) for i in dict.fromkeys(revision_ids)]}).all()
        wrong = [str(r.id) for r in rows if r.state != 'approved' or str(r.school_id) != str(
            school_id) or str(r.method_id) != str(method_id)]
        if wrong or len(rows) != len(set(map(str, revision_ids))):
            raise AppError(422, 'VALIDATION_ERROR', 'every member must be an approved revision of'
                           ' this school and method', field_errors=[
                               {'path': 'body.rule_revision_ids', 'message': ', '.join(wrong)
                                or 'unknown revision'}])
        if len({r.rule_key for r in rows}) != len(rows):
            raise AppError(422, 'VALIDATION_ERROR', 'one revision per rule')
    if not rows:
        raise AppError(409, 'RULESET_EMPTY', 'no approved rule for this school and method')
    try:
        ordered = order([Member(str(r.id), r.rule_key, r.dsl, i)
                         for i, r in enumerate(sorted(rows, key=lambda r: r.rule_key))])
    except RuleGraphError as exc:
        raise AppError(409, exc.code, str(exc), field_errors=[
            {'path': 'body.rule_revision_ids', 'message': ', '.join(exc.rules)}]) from None
    if conn.execute(text('SELECT 1 FROM rulesets WHERE school_id = :s AND method_id = :m'
                         ' AND version = :v'), {'s': school_id, 'm': method_id, 'v': version}).first():
        raise AppError(409, 'CONFLICT', f'version {version} exists for this school and method')
    ruleset_id = conn.execute(text(
        'INSERT INTO rulesets (school_id, method_id, version) VALUES (:s, :m, :v) RETURNING id'),
        {'s': school_id, 'm': method_id, 'v': version}).scalar_one()
    for ordinal, member in enumerate(ordered):
        conn.execute(text('INSERT INTO ruleset_members (ruleset_id, rule_id, ordinal)'
                          ' VALUES (:r, :k, :o)'),
                     {'r': ruleset_id, 'k': member.revision_id, 'o': ordinal})
    hashes = dict(conn.execute(text(
        'SELECT id::text, dsl_hash FROM knowledge_rules WHERE id = ANY(CAST(:ids AS uuid[]))'),
        {'ids': [m.revision_id for m in ordered]}).all())
    manifest = hashlib.sha256(json.dumps(
        [[m.revision_id, hashes[m.revision_id].strip()] for m in ordered]).encode()).hexdigest()
    conn.execute(text('UPDATE rulesets SET manifest_hash = :h WHERE id = :r'),
                 {'h': manifest, 'r': ruleset_id})
    return get_ruleset(conn, ruleset_id)


def current(conn: Connection, school_id, method_id) -> uuid.UUID | None:
    return conn.execute(text("SELECT id FROM rulesets WHERE school_id = :s AND method_id = :m"
                             " AND state = 'published'"), {'s': school_id, 'm': method_id}).scalar()


def activate(conn: Connection, ruleset_id, expected_current_id) -> dict:
    row = conn.execute(text('SELECT id, school_id, method_id, state FROM rulesets'
                            ' WHERE id = :r FOR UPDATE'), {'r': ruleset_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Ruleset not found')
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:k))'),
                 {'k': f'ruleset:{row.school_id}:{row.method_id}'})
    active = current(conn, row.school_id, row.method_id)
    if active == row.id:
        return {**get_ruleset(conn, ruleset_id), 'analyses_stale': 0}     # idempotent
    if row.state != 'building':
        raise AppError(409, 'RULESET_RETIRED', 'a retired ruleset cannot be activated again')
    seen = str(active) if active else None
    expected = str(expected_current_id) if expected_current_id else None
    if seen != expected:
        raise AppError(409, 'ACTIVE_CHANGED', 'another ruleset was activated meanwhile; reload')
    stale = 0
    if active is not None:
        conn.execute(text("UPDATE rulesets SET state = 'retired' WHERE id = :r"), {'r': active})
        stale = impact.mark_stale(conn, {'ruleset': {str(active)}}, 'ruleset_superseded')
    conn.execute(text("UPDATE rulesets SET state = 'published' WHERE id = :r"), {'r': ruleset_id})
    return {**get_ruleset(conn, ruleset_id), 'analyses_stale': stale}
