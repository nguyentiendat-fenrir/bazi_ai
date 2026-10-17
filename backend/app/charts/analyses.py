"""Rule analyses of a chart (docs/08 · B, docs/10 · analyses).

An analysis runs one ruleset on the chart's frozen facts (plus an optional ``as_of``
date for the luck/annual pillar functions) and stores the claims, conflicts and one
trace per rule. Its dependencies — the ruleset, every member revision and the chart —
are recorded, so revoking a rule or replacing the ruleset marks it stale; a stale
analysis is history, re-evaluation makes a new one and reports what changed. A
ruleset with a revoked member is refused until a new one is activated. The language
model narrative of docs/09 is added on top later (T039); nothing here calls a model.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.crypto import FieldCipher
from ..core.errors import AppError
from ..knowledge import rulesets
from ..rules.engine import RuleGraphError, run
from . import service

# Engine status → stored trace status (rule_traces.status); the exact one stays in predicates.
TRACE_STATUS = {'fired': 'true', 'not_matched': 'false', 'blocked_exception': 'false',
                'dependency_blocked': 'false', 'pending': 'unknown', 'skipped': 'skipped'}


def _ruleset_for(conn: Connection, school_id, method_id, ruleset_id) -> dict:
    chosen = ruleset_id or rulesets.current(conn, school_id, method_id)
    if chosen is None:
        raise AppError(409, 'NO_ACTIVE_RULESET', 'no ruleset is active for this school and method')
    ruleset = rulesets.get_ruleset(conn, chosen)
    if (school_id and ruleset['school_id'] != str(school_id)) or (
            method_id and ruleset['method_id'] != str(method_id)):
        raise AppError(422, 'VALIDATION_ERROR', 'the ruleset belongs to another school or method')
    if ruleset['state'] == 'retired':
        raise AppError(409, 'RULESET_RETIRED', 'this ruleset was replaced; use the active one')
    revoked = conn.execute(text(
        "SELECT k.rule_key FROM ruleset_members x JOIN knowledge_rules k ON k.id = x.rule_id"
        " WHERE x.ruleset_id = :r AND k.state <> 'approved' ORDER BY k.rule_key"),
        {'r': chosen}).scalars().all()
    if revoked:
        raise AppError(409, 'RULESET_HAS_REVOKED_RULE', 'a member rule is no longer approved;'
                       ' build and activate a new ruleset', field_errors=[
                           {'path': 'ruleset', 'message': ', '.join(revoked)}])
    return ruleset


def run_analysis(conn: Connection, principal: Principal, cipher: FieldCipher, chart_id,
                 school_id=None, method_id=None, ruleset_id=None, as_of: str | None = None) -> dict:
    chart = service.get_chart(conn, principal, cipher, chart_id)       # 404 if not the owner's
    ruleset = _ruleset_for(conn, school_id, method_id, ruleset_id)
    facts = {**chart['facts'], **({'query': {'as_of': as_of}} if as_of else {})}
    members = rulesets.members(conn, ruleset['id'])
    try:
        result = run(members, facts)
    except RuleGraphError as exc:                     # a frozen ruleset was validated
        raise AppError(500, exc.code, str(exc)) from None
    conflict_keys = {c['claim_key'] for c in result['conflicts']}
    analysis_id = uuid.uuid4()
    answer = {'kind': 'rules', 'status': result['status'], 'as_of': as_of,
              'facts_hash': chart['facts_hash'],
              'ruleset': {k: ruleset[k] for k in ('id', 'version', 'manifest_hash', 'school_key',
                                                  'method_key')},
              'claims': result['claims'], 'conflicts': result['conflicts'],
              'counters': result['counters'], 'narrative': None}
    conn.execute(text(
        "INSERT INTO chart_analyses (id, owner_id, chart_id, ruleset_id, answer, status)"
        " VALUES (:id, :o, :c, :r, CAST(:a AS jsonb), 'completed')"),
        {'id': analysis_id, 'o': principal.user_id, 'c': chart['id'], 'r': ruleset['id'],
         'a': json.dumps(answer, ensure_ascii=False)})
    for position, trace in enumerate(result['traces']):
        claims = [c for c in result['claims'] if c['rule_revision_id'] == trace['revision_id']]
        status = TRACE_STATUS[trace['status']]
        if status == 'true' and any(c['claim_key'] in conflict_keys for c in claims):
            status = 'conflict'
        conn.execute(text(
            'INSERT INTO rule_traces (analysis_id, rule_id, status, predicates, emissions,'
            ' conflicts) VALUES (:a, :r, :s, CAST(:p AS jsonb), CAST(:e AS jsonb),'
            ' CAST(:c AS jsonb))'),
            {'a': analysis_id, 'r': trace['revision_id'], 's': status,
             'p': json.dumps({**{k: v for k, v in trace.items() if k not in ('revision_id',)},
                              'position': position}, ensure_ascii=False, default=str),
             'e': json.dumps(claims, ensure_ascii=False),
             'c': json.dumps([c for c in result['conflicts']
                              if c['claim_key'] in {x['claim_key'] for x in claims}],
                             ensure_ascii=False)})
    dependencies = [('ruleset', ruleset['id'], ruleset['manifest_hash']),
                    ('chart', chart['id'], chart['facts_hash'])]
    dependencies += [('rule', m.revision_id, None) for m in members]
    for kind, entity, digest in dependencies:
        conn.execute(text('INSERT INTO analysis_dependencies (analysis_id, dependency_kind,'
                          ' dependency_id, content_hash) VALUES (:a, :k, :i, :h)'),
                     {'a': analysis_id, 'k': kind, 'i': entity, 'h': digest})
    return get_analysis(conn, analysis_id)


SELECT = ('SELECT a.id, a.chart_id, a.ruleset_id, a.status, a.stale_reason, a.answer,'
          ' a.created_at, a.updated_at FROM chart_analyses a')


def _dto(row) -> dict:
    return {'id': str(row.id), 'chart_id': str(row.chart_id),
            'ruleset_id': str(row.ruleset_id) if row.ruleset_id else None, 'status': row.status,
            'stale_reason': row.stale_reason, 'answer': row.answer,
            'created_at': row.created_at, 'updated_at': row.updated_at}


def get_analysis(conn: Connection, analysis_id) -> dict:
    row = conn.execute(text(f'{SELECT} WHERE a.id = :i'), {'i': analysis_id}).first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Analysis not found')    # also another owner's (RLS)
    return _dto(row)


def list_analyses(conn: Connection, chart_id) -> list[dict]:
    return [_dto(r) for r in conn.execute(text(f'{SELECT} WHERE a.chart_id = :c'
                                               ' ORDER BY a.created_at DESC'), {'c': chart_id})]


def trace(conn: Connection, analysis_id, limit: int, cursor: str | None) -> tuple[list, str | None]:
    get_analysis(conn, analysis_id)
    offset = int(cursor) if cursor and cursor.isdigit() else 0
    rows = conn.execute(text(
        "SELECT t.rule_id, k.rule_key, k.revision, k.state, t.status, t.predicates, t.emissions,"
        " t.conflicts FROM rule_traces t JOIN knowledge_rules k ON k.id = t.rule_id"
        " WHERE t.analysis_id = :a ORDER BY (t.predicates->>'position')::int"
        ' LIMIT :n OFFSET :o'), {'a': analysis_id, 'n': limit + 1, 'o': offset}).all()
    items = [{'revision_id': str(r.rule_id), 'rule_key': r.rule_key, 'revision': r.revision,
              # A revoked rule stays visible in history, marked as such.
              'rule_state': r.state, 'status': r.status, 'detail': r.predicates,
              'emissions': r.emissions, 'conflicts': r.conflicts} for r in rows[:limit]]
    return items, (str(offset + limit) if len(rows) > limit else None)


def reevaluate(conn: Connection, principal: Principal, cipher: FieldCipher, analysis_id) -> dict:
    old = get_analysis(conn, analysis_id)
    ruleset = old['answer']['ruleset']
    school = conn.execute(text('SELECT school_id, method_id FROM rulesets WHERE id = :r'),
                          {'r': ruleset['id']}).one()
    fresh = run_analysis(conn, principal, cipher, old['chart_id'], school.school_id,
                         school.method_id, None, old['answer'].get('as_of'))

    def keyed(answer: dict) -> set[tuple[str, str]]:
        return {(c['claim_key'], json.dumps(c['value'])) for c in answer['claims']}
    before, after = keyed(old['answer']), keyed(fresh['answer'])
    return {'analysis': fresh, 'previous_id': old['id'], 'diff': {
        'added': [{'claim_key': k, 'value': json.loads(v)} for k, v in sorted(after - before)],
        'removed': [{'claim_key': k, 'value': json.loads(v)} for k, v in sorted(before - after)],
        'unchanged': len(before & after)}}
