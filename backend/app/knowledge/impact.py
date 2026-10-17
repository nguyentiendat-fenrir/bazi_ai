"""Dependency impact graph (docs/06 · Impact analysis; docs/10 ``GET /knowledge/impact``).

Walks downstream from one entity: a page revision's evidence, the assertions,
rules and cases citing it, rules built on an assertion, rules requiring a
rule, rulesets holding them, concepts' aliases and ontology releases, corpus
releases pinning a generation or an ontology… Analyses and chat runs that
depended on anything reached are counted through a definer function: they
belong to their owners, so the reviewer learns how many, never which.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError

MAX_DEPTH = 6
SAMPLE = 100
# parent kind -> [(child kind, query returning child ids for :ids)]
EDGES: dict[str, list[tuple[str, str]]] = {
    'book_version': [
        ('generation', 'SELECT id FROM generations WHERE book_version_id = ANY(:ids)'),
        ('evidence', 'SELECT id FROM evidence_spans WHERE book_version_id = ANY(:ids)')],
    'page_revision': [
        ('evidence', 'SELECT id FROM evidence_spans WHERE page_revision_id = ANY(:ids)')],
    'evidence': [
        ('assertion', 'SELECT assertion_id FROM assertion_sources WHERE evidence_id = ANY(:ids)'),
        ('rule', 'SELECT rule_id FROM rule_sources WHERE evidence_id = ANY(:ids)'),
        ('case_revision', 'SELECT case_revision_id FROM case_sources WHERE evidence_id = ANY(:ids)'),
        ('term', 'SELECT id FROM terms WHERE evidence_id = ANY(:ids)')],
    'assertion': [
        ('rule', 'SELECT id FROM knowledge_rules WHERE assertion_id = ANY(:ids)'),
        ('assertion_relation', 'SELECT id FROM assertion_relations'
                               ' WHERE from_id = ANY(:ids) OR to_id = ANY(:ids)')],
    'rule': [
        ('rule', 'SELECT rule_id FROM rule_dependencies WHERE requires_id = ANY(:ids)'),
        ('ruleset', 'SELECT ruleset_id FROM ruleset_members WHERE rule_id = ANY(:ids)')],
    'method': [
        ('assertion', 'SELECT id FROM assertions WHERE method_id = ANY(:ids)'),
        ('rule', 'SELECT id FROM knowledge_rules WHERE method_id = ANY(:ids)'),
        ('case_revision', 'SELECT id FROM case_revisions WHERE method_id = ANY(:ids)'),
        ('ruleset', 'SELECT id FROM rulesets WHERE method_id = ANY(:ids)')],
    'concept': [
        ('term', 'SELECT id FROM terms WHERE concept_id = ANY(:ids)'),
        ('assertion', 'SELECT id FROM assertions WHERE concept_id = ANY(:ids)'),
        ('ontology_release', 'SELECT release_id FROM ontology_members WHERE concept_id = ANY(:ids)')],
    'term': [
        ('ontology_release', 'SELECT release_id FROM ontology_members WHERE term_id = ANY(:ids)')],
    'school_scope': [
        ('generation', "SELECT DISTINCT g.id FROM generations g JOIN school_scopes s"
                       " ON s.book_version_id = g.book_version_id WHERE s.id = ANY(:ids)")],
    'chunk': [
        ('generation', 'SELECT generation_id FROM generation_chunks WHERE chunk_id = ANY(:ids)')],
    'generation': [
        ('corpus_release', 'SELECT release_id FROM corpus_members WHERE generation_id = ANY(:ids)')],
    'ontology_release': [
        ('corpus_release', 'SELECT id FROM corpus_releases WHERE ontology_release_id = ANY(:ids)')],
}
ROOTS = {'book_version': 'book_versions', 'page_revision': 'page_revisions',
         'evidence': 'evidence_spans', 'assertion': 'assertions', 'rule': 'knowledge_rules',
         'method': 'methods', 'concept': 'concepts', 'term': 'terms',
         'school_scope': 'school_scopes', 'chunk': 'chunks', 'generation': 'generations',
         'ontology_release': 'ontology_releases', 'case_revision': 'case_revisions',
         'corpus_release': 'corpus_releases'}


def downstream(conn: Connection, kind: str, entity_id, depth: int = MAX_DEPTH) -> dict[str, set]:
    """Every entity reachable downstream of ``(kind, entity_id)``, by kind (root included)."""
    reached: dict[str, set] = {kind: {str(entity_id)}}
    frontier = {kind: {str(entity_id)}}
    for _ in range(depth):
        following: dict[str, set] = {}
        for parent, ids in frontier.items():
            for child, query in EDGES.get(parent, []):
                found = {str(r) for r in conn.execute(text(
                    query.replace(':ids', 'CAST(:ids AS uuid[])')), {'ids': sorted(ids)}).scalars()}
                new = found - reached.get(child, set())
                if new:
                    reached.setdefault(child, set()).update(new)
                    following.setdefault(child, set()).update(new)
        if not following:
            break
        frontier = following
    return reached


def dependents(conn: Connection, reached: dict[str, set]) -> dict:
    deps = json.dumps({kind: sorted(ids) for kind, ids in reached.items()})
    analyses, runs = conn.execute(text('SELECT * FROM bazi_dependent_count(CAST(:d AS jsonb))'),
                                  {'d': deps}).one()
    return {'analyses': analyses, 'runs': runs}


def mark_stale(conn: Connection, reached: dict[str, set], reason: str) -> int:
    return conn.execute(text('SELECT bazi_mark_dependents_stale(CAST(:d AS jsonb), :r)'),
                        {'d': json.dumps({k: sorted(v) for k, v in reached.items()}),
                         'r': reason}).scalar_one()


def impact(conn: Connection, kind: str, entity_id) -> dict:
    if kind not in ROOTS:
        raise AppError(422, 'VALIDATION_ERROR', f'impact is not tracked for {kind}')
    if not conn.execute(text(f'SELECT 1 FROM {ROOTS[kind]} WHERE id = :i'),
                        {'i': entity_id}).first():
        raise AppError(404, 'NOT_FOUND', f'{kind} not found')
    reached = downstream(conn, kind, entity_id)
    below = {k: v - ({str(entity_id)} if k == kind else set()) for k, v in reached.items()}
    return {'entity_kind': kind, 'entity_id': str(entity_id),
            'counts': {k: len(v) for k, v in below.items() if v},
            'ids': {k: sorted(v)[:SAMPLE] for k, v in below.items() if v},
            'dependents': dependents(conn, reached)}
