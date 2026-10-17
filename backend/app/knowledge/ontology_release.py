"""Ontology releases: frozen snapshots of approved concepts and aliases (docs/06, docs/03).

A release holds, for every concept key, its latest approved revision and that
revision's approved aliases; nothing in draft or review gets in, and the
database re-checks each member. Publishing a release retires the previous one
and, when a corpus is active, pins it through a new corpus release with the
same generations (no document is re-processed or re-embedded), activated in
the same transaction under the corpus lock. Retrieval expansion reads aliases
from the ontology release the active corpus pins.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import re

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError
from ..documents import releases

VERSION = re.compile(r'^[a-z0-9][a-z0-9._-]{0,63}$')
SNAPSHOT = (
    'SELECT c.id AS concept_id, s.key AS school_key, c.canonical_key, c.revision,'
    ' t.id AS term_id, t.form_nfc, t.language, t.alias_kind FROM concepts c'
    ' JOIN schools s ON s.id = c.school_id'
    " LEFT JOIN terms t ON t.concept_id = c.id AND t.state = 'approved'"
    " WHERE c.state = 'approved' AND c.revision = (SELECT max(x.revision) FROM concepts x"
    "  WHERE x.school_id = c.school_id AND x.canonical_key = c.canonical_key"
    "  AND x.state = 'approved')"
    ' ORDER BY s.key, c.canonical_key, t.form_nfc, t.language, t.alias_kind')
MEMBERS = (
    'SELECT c.id AS concept_id, s.key AS school_key, c.canonical_key, c.revision,'
    ' t.id AS term_id, t.form_nfc, t.language, t.alias_kind FROM ontology_members m'
    ' JOIN concepts c ON c.id = m.concept_id JOIN schools s ON s.id = c.school_id'
    ' LEFT JOIN terms t ON t.id = m.term_id WHERE m.release_id = :r'
    ' ORDER BY s.key, c.canonical_key, t.form_nfc, t.language, t.alias_kind')


def _lines(rows) -> tuple[set, set]:
    concepts = {(r['school_key'], r['canonical_key'], r['revision']) for r in rows}
    terms = {(r['school_key'], r['canonical_key'], r['form_nfc'], r['language'], r['alias_kind'])
             for r in rows if r['term_id'] is not None}
    return concepts, terms


def _manifest(rows) -> str:
    concepts, terms = _lines(rows)
    material = '\n'.join(sorted('|'.join(map(str, c)) for c in concepts) +
                         sorted('|'.join(map(str, t)) for t in terms))
    return hashlib.sha256(material.encode('utf-8')).hexdigest()


def current(conn: Connection):
    return conn.execute(text(
        "SELECT id, version, manifest_hash FROM ontology_releases WHERE state = 'published'"
        ' ORDER BY created_at DESC LIMIT 1')).mappings().first()


def preview(conn: Connection) -> dict:
    """What publishing now would add and remove, relative to the current release."""
    rows = conn.execute(text(SNAPSHOT)).mappings().all()
    base = current(conn)
    old = conn.execute(text(MEMBERS), {'r': base['id']}).mappings().all() if base else []
    new_concepts, new_terms = _lines(rows)
    old_concepts, old_terms = _lines(old)
    as_keys = lambda items: sorted(f'{s}.{k}@{r}' for s, k, r in items)
    as_terms = lambda items: sorted(f'{s}.{k}: {f} ({lang}, {kind})'
                                    for s, k, f, lang, kind in items)
    return {'base_release_id': str(base['id']) if base else None,
            'base_version': base['version'] if base else None,
            'manifest_hash': _manifest(rows), 'changed': _manifest(rows) != (
                _manifest(old) if base else None),
            'concepts': {'added': as_keys(new_concepts - old_concepts),
                         'removed': as_keys(old_concepts - new_concepts),
                         'total': len(new_concepts)},
            'terms': {'added': as_terms(new_terms - old_terms),
                      'removed': as_terms(old_terms - new_terms), 'total': len(new_terms)}}


def release_dto(conn: Connection, release_id) -> dict:
    row = conn.execute(text(
        'SELECT r.id, r.version, r.state, r.manifest_hash, r.created_at,'
        ' (SELECT count(DISTINCT concept_id) FROM ontology_members WHERE release_id = r.id)'
        ' AS concepts, (SELECT count(term_id) FROM ontology_members WHERE release_id = r.id)'
        ' AS terms, EXISTS (SELECT 1 FROM active_corpus a JOIN corpus_releases c'
        ' ON c.id = a.release_id WHERE c.ontology_release_id = r.id) AS pinned'
        ' FROM ontology_releases r WHERE r.id = :r'), {'r': release_id}).mappings().first()
    if row is None:
        raise AppError(404, 'NOT_FOUND', 'Ontology release not found')
    return {'id': str(row['id']), 'version': row['version'], 'state': row['state'],
            'manifest_hash': row['manifest_hash'].strip() if row['manifest_hash'] else None,
            'created_at': row['created_at'], 'concepts': row['concepts'], 'terms': row['terms'],
            'pinned_by_active_corpus': row['pinned']}


def list_releases(conn: Connection) -> list[dict]:
    ids = conn.execute(text('SELECT id FROM ontology_releases ORDER BY created_at DESC')).scalars()
    return [release_dto(conn, i) for i in ids.all()]


def publish(conn: Connection, actor_id, version: str | None, request_id: str | None) -> dict:
    releases.lock_corpus(conn)
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('bazi.ontology'))"))
    diff = preview(conn)
    if not diff['changed']:
        raise AppError(409, 'NO_CHANGE', 'Approved concepts and aliases match the current release')
    if version is None:
        stamp = date.today().strftime('%Y%m%d')
        taken = conn.execute(text('SELECT count(*) FROM ontology_releases WHERE version LIKE :p'),
                             {'p': f'onto-{stamp}-%'}).scalar_one()
        version = f'onto-{stamp}-{taken + 1}'
    if not VERSION.fullmatch(version):
        raise AppError(422, 'VALIDATION_ERROR', 'version: lower-case letters, digits, . _ -')
    release_id = conn.execute(text(
        'INSERT INTO ontology_releases (version) VALUES (:v) ON CONFLICT (version) DO NOTHING'
        ' RETURNING id'), {'v': version}).scalar()
    if release_id is None:
        raise AppError(409, 'CONFLICT', f'ontology release {version} exists')
    rows = conn.execute(text(SNAPSHOT)).mappings().all()
    for concept_id in dict.fromkeys(r['concept_id'] for r in rows):
        conn.execute(text('INSERT INTO ontology_members (release_id, concept_id) VALUES (:r, :c)'),
                     {'r': release_id, 'c': concept_id})
    for row in rows:
        if row['term_id'] is not None:
            conn.execute(text('INSERT INTO ontology_members (release_id, concept_id, term_id)'
                              ' VALUES (:r, :c, :t)'),
                         {'r': release_id, 'c': row['concept_id'], 't': row['term_id']})
    conn.execute(text("UPDATE ontology_releases SET state = 'retired'"
                      " WHERE state = 'published' AND id <> :r"), {'r': release_id})
    conn.execute(text("UPDATE ontology_releases SET state = 'published', manifest_hash = :m"
                      ' WHERE id = :r'), {'r': release_id, 'm': _manifest(rows)})
    corpus = releases.repin_ontology(conn, actor_id, release_id, request_id)
    conn.execute(text(
        "INSERT INTO audit_logs (actor_id, action, target_kind, target_id, trace_id,"
        " redacted_diff, outcome) VALUES (:a, 'ontology.publish', 'ontology_release', :r, :t,"
        " CAST(:d AS jsonb), 'success')"),
        {'a': actor_id, 'r': release_id, 't': request_id or '',
         'd': json.dumps({'version': version, 'concepts_added': len(diff['concepts']['added']),
                          'terms_added': len(diff['terms']['added']),
                          'corpus_release_id': corpus})})
    return {'release': release_dto(conn, release_id), 'diff': diff,
            'corpus_release_id': corpus}
