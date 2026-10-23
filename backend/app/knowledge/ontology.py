"""Schools, methods, topics, concepts and their aliases (docs/06 · Concept, term).

A concept is ``(school, canonical_key)`` with numbered revisions; aliases
(terms) belong to one concept revision and carry their own review state. A new
concept revision copies the live aliases of its base as drafts, and approving
the revision approves the copies that were already approved before (same form,
language and kind) — nothing new becomes approved without a review. The same
written form may name different concepts in different schools; search returns
each with its school so expansion never crosses schools silently.
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from ..documents.text import fold, nfc

KEY = re.compile(r'^[a-z][a-z0-9_]{0,59}(\.[a-z0-9_]{1,60}){0,3}$')
SCHOOL_KEY = re.compile(r'^[a-z][a-z0-9_]{1,39}$')
LIVE = ('draft', 'in_review', 'approved')


def _key(value: str, pattern=KEY, field: str = 'key') -> str:
    if not pattern.fullmatch(value):
        raise AppError(422, 'VALIDATION_ERROR', f'{field} must be lower-case ASCII words',
                       field_errors=[{'path': f'body.{field}', 'message': 'invalid key'}])
    return value


def _one(conn: Connection, query: str, params: dict, what: str):
    row = conn.execute(text(query), params).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', f'{what} not found')
    return row


def _ref(value):
    return str(value) if value is not None else None


# ---- schools and topics ------------------------------------------------------------

def school_dto(row) -> dict:
    return {'id': str(row['id']), 'key': row['key'], 'label': row['label'],
            'parent_id': _ref(row['parent_id']), 'description': row['description']}


def list_schools(conn: Connection) -> list[dict]:
    return [school_dto(r) for r in conn.execute(text(
        'SELECT id, key, label, parent_id, description FROM schools ORDER BY key')).mappings()]


def get_school(conn: Connection, school_id) -> dict:
    return school_dto(_one(conn, 'SELECT id, key, label, parent_id, description FROM schools'
                                 ' WHERE id = :i', {'i': school_id}, 'School'))


def create_school(conn: Connection, key: str, label: str, parent_id, description: str) -> dict:
    _key(key, SCHOOL_KEY)
    if parent_id is not None:
        get_school(conn, parent_id)
    row = conn.execute(text(
        'INSERT INTO schools (key, label, parent_id, description) VALUES (:k, :l, :p, :d)'
        ' ON CONFLICT (key) DO NOTHING RETURNING id, key, label, parent_id, description'),
        {'k': key, 'l': nfc(label).strip(), 'p': parent_id, 'd': nfc(description).strip()}
    ).mappings().first()
    if row is None:
        raise AppError(409, 'CONFLICT', f'School {key} already exists')
    return school_dto(row)


def list_topics(conn: Connection) -> list[dict]:
    return [{'id': str(r['id']), 'key': r['key'], 'label': r['label'],
             'parent_id': _ref(r['parent_id'])} for r in conn.execute(text(
                 'SELECT id, key, label, parent_id FROM topics ORDER BY key')).mappings()]


def create_topic(conn: Connection, key: str, label: str, parent_id) -> dict:
    _key(key, SCHOOL_KEY)
    row = conn.execute(text(
        'INSERT INTO topics (key, label, parent_id) VALUES (:k, :l, :p) ON CONFLICT (key)'
        ' DO NOTHING RETURNING id, key, label, parent_id'),
        {'k': key, 'l': nfc(label).strip(), 'p': parent_id}).mappings().first()
    if row is None:
        raise AppError(409, 'CONFLICT', f'Topic {key} already exists')
    return {'id': str(row['id']), 'key': row['key'], 'label': row['label'],
            'parent_id': _ref(row['parent_id'])}


# ---- methods -----------------------------------------------------------------------

METHOD_SELECT = ('SELECT m.id, m.school_id, s.key AS school_key, m.key, m.revision,'
                 ' m.description, m.state, m.created_at FROM methods m'
                 ' JOIN schools s ON s.id = m.school_id')


def method_dto(row) -> dict:
    return {'id': str(row['id']), 'school_id': str(row['school_id']),
            'school_key': row['school_key'], 'key': row['key'], 'revision': row['revision'],
            'description': row['description'], 'state': row['state'],
            'created_at': row['created_at']}


def list_methods(conn: Connection, school_id=None, state: str | None = None) -> list[dict]:
    clauses, params = [], {}
    if school_id:
        clauses.append('m.school_id = :school')
        params['school'] = school_id
    if state:
        clauses.append('m.state = :state')
        params['state'] = state
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    return [method_dto(r) for r in conn.execute(text(
        f'{METHOD_SELECT}{where} ORDER BY s.key, m.key, m.revision'), params).mappings()]


def get_method(conn: Connection, method_id) -> dict:
    return method_dto(_one(conn, f'{METHOD_SELECT} WHERE m.id = :i', {'i': method_id}, 'Method'))


def create_method(conn: Connection, school_id, key: str, description: str) -> dict:
    get_school(conn, school_id)
    _key(key, SCHOOL_KEY)
    if conn.execute(text('SELECT 1 FROM methods WHERE school_id = :s AND key = :k'),
                    {'s': school_id, 'k': key}).first():
        raise AppError(409, 'CONFLICT', f'Method {key} exists; add a revision instead')
    method_id = conn.execute(text(
        'INSERT INTO methods (school_id, key, revision, description) VALUES (:s, :k, 1, :d)'
        ' RETURNING id'), {'s': school_id, 'k': key, 'd': nfc(description).strip()}).scalar_one()
    return get_method(conn, method_id)


def revise_method(conn: Connection, method_id, base_revision: int, description: str) -> dict:
    base = get_method(conn, method_id)
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:k))'),
                 {'k': f"method:{base['school_id']}:{base['key']}"})
    latest = conn.execute(text('SELECT max(revision) FROM methods WHERE school_id = :s'
                               ' AND key = :k'),
                          {'s': base['school_id'], 'k': base['key']}).scalar_one()
    if base_revision != latest or base['revision'] != latest:
        raise AppError(412, 'REVISION_MISMATCH', f'Revise the latest revision ({latest})')
    new_id = conn.execute(text(
        'INSERT INTO methods (school_id, key, revision, description) VALUES (:s, :k, :r, :d)'
        ' RETURNING id'), {'s': base['school_id'], 'k': base['key'], 'r': latest + 1,
                           'd': nfc(description).strip()}).scalar_one()
    return get_method(conn, new_id)


# ---- concepts and terms ------------------------------------------------------------

CONCEPT_SELECT = (
    'SELECT c.id, c.school_id, s.key AS school_key, c.canonical_key, c.label, c.description,'
    ' c.revision, c.state, c.created_at FROM concepts c JOIN schools s ON s.id = c.school_id')
TERM_SELECT = (
    'SELECT t.id, t.concept_id, t.form_nfc, t.form_folded, t.language, t.alias_kind, t.state,'
    ' t.evidence_id, t.created_at FROM terms t')


def term_dto(row) -> dict:
    return {'id': str(row['id']), 'concept_id': str(row['concept_id']), 'form': row['form_nfc'],
            'form_folded': row['form_folded'], 'language': row['language'],
            'alias_kind': row['alias_kind'], 'state': row['state'],
            'evidence_id': _ref(row['evidence_id']), 'created_at': row['created_at']}


def concept_dto(row, terms=None) -> dict:
    dto = {'id': str(row['id']), 'school_id': str(row['school_id']),
           'school_key': row['school_key'], 'canonical_key': row['canonical_key'],
           'label': row['label'], 'description': row['description'], 'revision': row['revision'],
           'state': row['state'], 'created_at': row['created_at']}
    if terms is not None:
        dto['terms'] = terms
    return dto


def _terms(conn: Connection, concept_id) -> list[dict]:
    return [term_dto(r) for r in conn.execute(text(
        f'{TERM_SELECT} WHERE t.concept_id = :c ORDER BY t.alias_kind, t.language, t.form_nfc'),
        {'c': concept_id}).mappings()]


def get_concept(conn: Connection, concept_id) -> dict:
    row = _one(conn, f'{CONCEPT_SELECT} WHERE c.id = :i', {'i': concept_id}, 'Concept')
    dto = concept_dto(row, _terms(conn, concept_id))
    dto['revisions'] = [{'id': str(r[0]), 'revision': r[1], 'state': r[2]} for r in conn.execute(
        text('SELECT id, revision, state FROM concepts WHERE school_id = :s AND canonical_key = :k'
             ' ORDER BY revision'), {'s': row['school_id'], 'k': row['canonical_key']})]
    dto['reviews'] = [{'decision': r[0], 'reason': r[1], 'base_revision': r[2],
                       'reviewer_id': str(r[3]), 'created_at': r[4]} for r in conn.execute(text(
                           "SELECT decision, reason, base_revision, reviewer_id, created_at"
                           " FROM reviews WHERE entity_kind = 'concept' AND entity_id = :i"
                           ' ORDER BY created_at'), {'i': concept_id})]
    return dto


def list_concepts(conn: Connection, school_id=None, state: str | None = None,
                  q: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    """Latest revision per concept key; ``q`` matches label or any alias, accent-free."""
    clauses, params = [], {'limit': limit, 'offset': offset}
    if school_id:
        clauses.append('c.school_id = :school')
        params['school'] = school_id
    if state:
        clauses.append('c.state = :state')
        params['state'] = state
    if q:
        # The label is also the canonical term, so terms cover it accent-free.
        clauses.append('(EXISTS (SELECT 1 FROM terms t WHERE t.concept_id = c.id'
                       ' AND position(:q in t.form_folded) > 0)'
                       ' OR position(:q in c.canonical_key) > 0)')
        params['q'] = fold(q)
    where = (' AND ' + ' AND '.join(clauses)) if clauses else ''
    rows = conn.execute(text(
        f'{CONCEPT_SELECT} WHERE c.revision = (SELECT max(revision) FROM concepts x'
        f' WHERE x.school_id = c.school_id AND x.canonical_key = c.canonical_key){where}'
        ' ORDER BY s.key, c.canonical_key LIMIT :limit OFFSET :offset'), params).mappings().all()
    return [concept_dto(r) for r in rows]


def _insert_term(conn: Connection, concept_id, form: str, language: str, alias_kind: str,
                 evidence_id=None):
    form = nfc(form).strip()
    if not form or len(form) > 200:
        raise AppError(422, 'VALIDATION_ERROR', 'term form must have 1-200 characters')
    return conn.execute(text(
        'INSERT INTO terms (concept_id, form_nfc, form_folded, language, alias_kind, evidence_id)'
        ' VALUES (:c, :f, :folded, :lang, :kind, :e) ON CONFLICT DO NOTHING RETURNING id'),
        {'c': concept_id, 'f': form, 'folded': fold(form), 'lang': language, 'kind': alias_kind,
         'e': evidence_id}).scalar()


def create_concept(conn: Connection, school_id, canonical_key: str, label: str,
                   description: str, han: str | None = None) -> dict:
    get_school(conn, school_id)
    _key(canonical_key, field='canonical_key')
    if conn.execute(text('SELECT 1 FROM concepts WHERE school_id = :s AND canonical_key = :k'),
                    {'s': school_id, 'k': canonical_key}).first():
        raise AppError(409, 'CONFLICT', f'Concept {canonical_key} exists in this school;'
                       ' add a revision instead')
    concept_id = conn.execute(text(
        'INSERT INTO concepts (school_id, canonical_key, label, description, revision)'
        ' VALUES (:s, :k, :l, :d, 1) RETURNING id'),
        {'s': school_id, 'k': canonical_key, 'l': nfc(label).strip(),
         'd': nfc(description).strip()}).scalar_one()
    _insert_term(conn, concept_id, label, 'vi', 'canonical')
    if han:
        _insert_term(conn, concept_id, han, 'zh', 'translation_variant')
    return get_concept(conn, concept_id)


def revise_concept(conn: Connection, concept_id, base_revision: int, label: str | None,
                   description: str | None) -> dict:
    base = _one(conn, f'{CONCEPT_SELECT} WHERE c.id = :i', {'i': concept_id}, 'Concept')
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:k))'),
                 {'k': f"concept:{base['school_id']}:{base['canonical_key']}"})
    latest = conn.execute(text('SELECT max(revision) FROM concepts WHERE school_id = :s'
                               ' AND canonical_key = :k'),
                          {'s': base['school_id'], 'k': base['canonical_key']}).scalar_one()
    if base_revision != latest or base['revision'] != latest:
        raise AppError(412, 'REVISION_MISMATCH', f'Revise the latest revision ({latest})')
    new_label = nfc(label).strip() if label else base['label']
    new_id = conn.execute(text(
        'INSERT INTO concepts (school_id, canonical_key, label, description, revision)'
        ' VALUES (:s, :k, :l, :d, :r) RETURNING id'),
        {'s': base['school_id'], 'k': base['canonical_key'], 'l': new_label,
         'd': nfc(description).strip() if description is not None else base['description'],
         'r': latest + 1}).scalar_one()
    _insert_term(conn, new_id, new_label, 'vi', 'canonical')
    for term in _terms(conn, concept_id):
        if term['state'] in LIVE and term['alias_kind'] != 'canonical':
            _insert_term(conn, new_id, term['form'], term['language'], term['alias_kind'],
                         term['evidence_id'])
    return get_concept(conn, new_id)


def create_term(conn: Connection, concept_id, form: str, language: str, alias_kind: str,
                evidence_id=None) -> dict:
    concept = _one(conn, 'SELECT state FROM concepts WHERE id = :i', {'i': concept_id}, 'Concept')
    if concept['state'] not in LIVE:
        raise AppError(409, 'CONFLICT', f"Concept revision is {concept['state']}")
    if alias_kind == 'canonical':
        raise AppError(422, 'VALIDATION_ERROR', 'the canonical form comes from the concept label')
    if evidence_id is not None and not conn.execute(
            text('SELECT 1 FROM evidence_spans WHERE id = :e'), {'e': evidence_id}).first():
        raise AppError(422, 'VALIDATION_ERROR', 'evidence_id does not exist')
    term_id = _insert_term(conn, concept_id, form, language, alias_kind, evidence_id)
    if term_id is None:
        raise AppError(409, 'CONFLICT', 'This alias already exists on the concept')
    return term_dto(_one(conn, f'{TERM_SELECT} WHERE t.id = :i', {'i': term_id}, 'Term'))


def get_term(conn: Connection, term_id) -> dict:
    return term_dto(_one(conn, f'{TERM_SELECT} WHERE t.id = :i', {'i': term_id}, 'Term'))


def search_terms(conn: Connection, q: str | None, school_id=None, concept_id=None,
                 state: str | None = None, limit: int = 50) -> list[dict]:
    """Aliases by accent-free form; each hit names its concept and school."""
    clauses, params = [], {'limit': limit}
    if q:
        # Substring, or a close spelling (typo/missing word) — not loose trigram neighbours.
        clauses.append('(position(:q in t.form_folded) > 0'
                       ' OR similarity(t.form_folded, :q) >= 0.6)')
        params['q'] = fold(q)
    if school_id:
        clauses.append('c.school_id = :school')
        params['school'] = school_id
    if concept_id:
        clauses.append('t.concept_id = :concept')
        params['concept'] = concept_id
    if state:
        clauses.append('t.state = :state')
        params['state'] = state
    where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
    order = 'similarity(t.form_folded, :q) DESC, ' if q else ''
    rows = conn.execute(text(
        'SELECT t.id, t.concept_id, t.form_nfc, t.form_folded, t.language, t.alias_kind,'
        ' t.state, t.evidence_id, t.created_at, c.canonical_key, c.label, c.revision,'
        ' c.state AS concept_state, s.key AS school_key, c.school_id FROM terms t'
        ' JOIN concepts c ON c.id = t.concept_id JOIN schools s ON s.id = c.school_id'
        f'{where} ORDER BY {order}s.key, c.canonical_key, t.form_nfc LIMIT :limit'),
        params).mappings().all()
    return [{**term_dto(r), 'concept': {'canonical_key': r['canonical_key'], 'label': r['label'],
                                        'revision': r['revision'], 'state': r['concept_state'],
                                        'school_id': str(r['school_id']),
                                        'school_key': r['school_key']}} for r in rows]
