"""Knowledge rules: DSL drafts, revisions and fixtures (docs/06 · Quy trình duyệt, docs/08 · B).

A rule is a ``bazi-rule/1`` document plus its sources and dependencies. The
document's ``school_id``/``method_id`` are registry keys resolved here; its
``evidence_ids`` become ``rule_sources`` and ``requires`` becomes
``rule_dependencies`` (the database rejects cycles). Fixtures are facts
snapshots with the status the reviewer expects; they are stored as evaluation
items of the ``rule-fixtures`` dataset so approval can re-run them, and only
while the rule is a draft — what a reviewer approves includes its tests.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..auth.service import Principal
from ..core.errors import AppError
from ..documents.catalog import visibility_clause
from ..rules import dsl as rule_dsl
from .evidence import require_evidence

FIXTURE_DATASET = ('rule-fixtures', '1')
REQUIRED_FIXTURES = ('fired', 'not_matched', 'pending')
SELECT = ('SELECT k.id, k.rule_key, k.revision, k.school_id, s.key AS school_key, k.method_id,'
          ' m.key AS method_key, k.assertion_id, k.dsl, k.dsl_hash, k.fact_schema_version,'
          ' k.state, k.author_id, k.created_at FROM knowledge_rules k'
          ' JOIN schools s ON s.id = k.school_id JOIN methods m ON m.id = k.method_id')


def _ref(value):
    return str(value) if value is not None else None


def rule_dto(row) -> dict:
    return {'id': str(row['id']), 'rule_key': row['rule_key'], 'revision': row['revision'],
            'school_id': str(row['school_id']), 'school_key': row['school_key'],
            'method_id': str(row['method_id']), 'method_key': row['method_key'],
            'assertion_id': _ref(row['assertion_id']), 'dsl': row['dsl'],
            'dsl_hash': row['dsl_hash'].strip(), 'fact_schema_version': row['fact_schema_version'],
            'state': row['state'], 'author_id': str(row['author_id']),
            'created_at': row['created_at']}


def _resolve(conn: Connection, document: dict) -> tuple:
    errors = rule_dsl.validate(document)
    if errors:
        raise AppError(422, 'RULE_INVALID', 'The rule document is not valid bazi-rule/1',
                       field_errors=[{'path': f"body.dsl.{e['path']}", 'message': e['message']}
                                     for e in errors])
    school = conn.execute(text('SELECT id FROM schools WHERE key = :k'),
                          {'k': document['school_id']}).scalar()
    if school is None:
        raise AppError(422, 'VALIDATION_ERROR', f"unknown school {document['school_id']}")
    method = conn.execute(text('SELECT id FROM methods WHERE school_id = :s AND key = :k'
                               ' ORDER BY revision DESC LIMIT 1'),
                          {'s': school, 'k': document['method_id']}).scalar()
    if method is None:
        raise AppError(422, 'VALIDATION_ERROR', f"unknown method {document['method_id']}"
                       ' in this school')
    evidence = require_evidence(conn, document.get('evidence_ids') or [])
    requires = [str(r) for r in dict.fromkeys(document.get('requires') or [])]
    if requires and conn.execute(text(
            'SELECT count(*) FROM knowledge_rules WHERE id = ANY(CAST(:ids AS uuid[]))'),
            {'ids': requires}).scalar_one() != len(requires):
        raise AppError(422, 'VALIDATION_ERROR', 'requires names unknown rule revisions')
    return school, method, evidence, requires


def _insert(conn: Connection, principal: Principal, document: dict, revision: int,
            assertion_id) -> uuid.UUID:
    school, method, evidence, requires = _resolve(conn, document)
    payload = json.dumps(document, ensure_ascii=False)
    rule_id = conn.execute(text(
        'INSERT INTO knowledge_rules (rule_key, revision, school_id, method_id, assertion_id, dsl,'
        ' dsl_hash, fact_schema_version, author_id) VALUES (:k, :r, :s, :m, :a, CAST(:d AS jsonb),'
        ' bazi_sha256_text(CAST(:d AS jsonb)::text), :f, :u) RETURNING id'),
        {'k': document['rule_key'], 'r': revision, 's': school, 'm': method, 'a': assertion_id,
         'd': payload, 'f': document['fact_schema_version'], 'u': principal.user_id}).scalar_one()
    for evidence_id in evidence:
        conn.execute(text('INSERT INTO rule_sources (rule_id, evidence_id) VALUES (:r, :e)'),
                     {'r': rule_id, 'e': evidence_id})
    for required in requires:
        conn.execute(text('INSERT INTO rule_dependencies (rule_id, requires_id) VALUES (:r, :q)'),
                     {'r': rule_id, 'q': required})
    return rule_id


def create_rule(conn: Connection, principal: Principal, document: dict, assertion_id=None) -> dict:
    if conn.execute(text('SELECT 1 FROM knowledge_rules WHERE rule_key = :k'),
                    {'k': document.get('rule_key')}).first():
        raise AppError(409, 'CONFLICT', 'this rule_key exists; add a revision instead')
    return get_rule(conn, principal, _insert(conn, principal, document, 1, assertion_id))


def revise_rule(conn: Connection, principal: Principal, rule_id, base_revision: int,
                document: dict) -> dict:
    base = conn.execute(text(f'{SELECT} WHERE k.id = :i'), {'i': rule_id}).mappings().first()
    if base is None:
        raise AppError(404, 'NOT_FOUND', 'Rule not found')
    if document.get('rule_key') != base['rule_key']:
        raise AppError(422, 'VALIDATION_ERROR', 'a revision keeps the rule_key')
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:k))'),
                 {'k': f"rule:{base['rule_key']}"})
    latest = conn.execute(text('SELECT max(revision) FROM knowledge_rules WHERE rule_key = :k'),
                          {'k': base['rule_key']}).scalar_one()
    if base_revision != latest or base['revision'] != latest:
        raise AppError(412, 'REVISION_MISMATCH', f'Revise the latest revision ({latest})')
    return get_rule(conn, principal,
                    _insert(conn, principal, document, latest + 1, base['assertion_id']))


def _fixtures(conn: Connection, rule_id) -> list[dict]:
    return [{'name': key.split(':', 1)[1], 'facts': item_input['facts'],
             'fired_rules': item_input.get('fired_rules'), 'expect': expected['status']}
            for key, item_input, expected in conn.execute(text(
                'SELECT i.key, i.input, i.expected FROM evaluation_items i'
                ' JOIN evaluation_datasets d ON d.id = i.dataset_id'
                " WHERE d.name = :n AND d.version = :v AND i.key LIKE :prefix ORDER BY i.key"),
                {'n': FIXTURE_DATASET[0], 'v': FIXTURE_DATASET[1], 'prefix': f'{rule_id}:%'})]


def get_rule(conn: Connection, principal: Principal, rule_id) -> dict:
    row = conn.execute(text(f'{SELECT} WHERE k.id = :i'), {'i': rule_id}).mappings().first()
    if row is None or (row['state'] != 'approved' and not principal.has_role('reviewer')):
        raise AppError(404, 'NOT_FOUND', 'Rule not found')
    visible, params = visibility_clause(principal)
    sources = conn.execute(text(
        'SELECT e.id, p.physical_page_number, e.book_version_id, e.page_revision_id,'
        ' substr(r.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset) AS quote'
        ' FROM rule_sources x JOIN evidence_spans e ON e.id = x.evidence_id'
        ' JOIN page_revisions r ON r.id = e.page_revision_id JOIN pages p ON p.id = r.page_id'
        ' JOIN book_versions v ON v.id = e.book_version_id JOIN books b ON b.id = v.book_id'
        f' WHERE x.rule_id = :i AND b.deleted_at IS NULL AND {visible}'
        ' ORDER BY p.physical_page_number'), {**params, 'i': rule_id}).mappings().all()
    requires = conn.execute(text('SELECT requires_id FROM rule_dependencies WHERE rule_id = :i'),
                            {'i': rule_id}).scalars().all()
    reviews = conn.execute(text(
        "SELECT decision, reason, base_revision, reviewer_id, created_at FROM reviews"
        " WHERE entity_kind = 'rule' AND entity_id = :i ORDER BY created_at"),
        {'i': rule_id}).mappings().all()
    return {**rule_dto(row),
            'sources': [{'evidence_id': str(s['id']), 'physical_page_number':
                         s['physical_page_number'], 'book_version_id': str(s['book_version_id']),
                         'page_revision_id': str(s['page_revision_id']), 'quote': s['quote']}
                        for s in sources],
            'requires': [str(r) for r in requires],
            'fixtures': _fixtures(conn, rule_id),
            'reviews': [{**dict(r), 'reviewer_id': str(r['reviewer_id'])} for r in reviews]}


def list_rules(conn: Connection, principal: Principal, state: str | None, school_id,
               method_id, limit: int, offset: int) -> list[dict]:
    clauses, params = [], {'limit': limit, 'offset': offset}
    if not principal.has_role('reviewer'):
        state = 'approved'
    for column, value in (('state', state), ('school_id', school_id), ('method_id', method_id)):
        if value is not None:
            clauses.append(f'k.{column} = :{column}')
            params[column] = value
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    return [rule_dto(r) for r in conn.execute(text(
        f'{SELECT}{where} ORDER BY k.rule_key, k.revision LIMIT :limit OFFSET :offset'),
        params).mappings()]


def run_fixtures(document: dict, fixtures: list[dict]) -> list[dict]:
    results = []
    for fixture in fixtures:
        outcome = rule_dsl.run_rule(document, fixture['facts'],
                                    {'fired_rules': fixture.get('fired_rules')})
        results.append({'name': fixture['name'], 'expect': fixture['expect'],
                        'status': outcome['status'], 'passed': outcome['status'] == fixture['expect']})
    return results


def coverage_problem(results: list[dict]) -> str | None:
    """docs/06: positive, negative and missing-fact fixtures, all passing."""
    missing = [s for s in REQUIRED_FIXTURES if not any(r['expect'] == s for r in results)]
    if missing:
        return f"fixtures missing for: {', '.join(missing)}"
    failed = [r['name'] for r in results if not r['passed']]
    return f"fixtures failing: {', '.join(failed)}" if failed else None


def validate_rule(conn: Connection, principal: Principal, rule_id, fixtures: list[dict]) -> dict:
    row = conn.execute(text('SELECT id, state, dsl FROM knowledge_rules WHERE id = :i FOR UPDATE'),
                       {'i': rule_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Rule not found')
    errors = rule_dsl.validate(row['dsl'])
    if fixtures:
        if row['state'] != 'draft':
            raise AppError(409, 'CONFLICT', 'fixtures are part of a draft; revise the rule')
        names = [f['name'] for f in fixtures]
        if len(set(names)) != len(names):
            raise AppError(422, 'VALIDATION_ERROR', 'fixture names must be unique')
        dataset = conn.execute(text(
            'INSERT INTO evaluation_datasets (name, version) VALUES (:n, :v)'
            ' ON CONFLICT (name, version) DO UPDATE SET name = EXCLUDED.name RETURNING id'),
            {'n': FIXTURE_DATASET[0], 'v': FIXTURE_DATASET[1]}).scalar_one()
        conn.execute(text('DELETE FROM evaluation_items WHERE dataset_id = :d AND key LIKE :p'),
                     {'d': dataset, 'p': f'{rule_id}:%'})
        for fixture in fixtures:
            conn.execute(text(
                "INSERT INTO evaluation_items (dataset_id, key, kind, input, expected,"
                " source_manifest, split) VALUES (:d, :k, 'rule', CAST(:i AS jsonb),"
                " CAST(:e AS jsonb), CAST(:m AS jsonb), 'dev')"),
                {'d': dataset, 'k': f"{rule_id}:{fixture['name']}",
                 'i': json.dumps({'facts': fixture['facts'],
                                  'fired_rules': fixture.get('fired_rules')}),
                 'e': json.dumps({'status': fixture['expect']}),
                 'm': json.dumps({'rule_revision_id': str(rule_id)})})
    stored = _fixtures(conn, rule_id)
    results = run_fixtures(row['dsl'], stored) if not errors else []
    return {'rule_id': str(rule_id), 'valid': not errors, 'errors': errors, 'results': results,
            'approvable_fixtures': coverage_problem(results) is None,
            'problem': coverage_problem(results) if not errors else 'the rule document is invalid'}
