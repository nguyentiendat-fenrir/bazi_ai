"""Pipeline profiles: the parser/OCR/chunker versions and embedding profile a version is
processed with (docs/04 ``pipeline_profiles``, immutable rows).

Versions are taken from the code that will run, so a profile never claims a parser it
does not use; the config hash makes creating the same profile twice a no-op.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Connection

from . import chunker, docx, ocr_stage, pdf_native, quality, structure

OCR_LANGUAGES = re.compile(r'^[a-z_]{3,8}(\+[a-z_]{3,8}){0,5}$')


class ProfileError(ValueError):
    pass


def code_versions(renderer: str | None = None) -> dict:
    return {'parser_version': (f'{pdf_native.PARSER_VERSION}+{docx.PARSER_VERSION}'
                               f'+{ocr_stage.OCR_VERSION}'),
            'chunker_version': chunker.CHUNKER_VERSION,
            'normalizer_version': f'{structure.STRUCTURE_VERSION}+{quality.QUALITY_VERSION}',
            'renderer_version': renderer}


def create_pipeline_profile(conn: Connection, name: str, embedding_profile_id: uuid.UUID,
                            ocr_languages: str | None = None,
                            renderer: str | None = None) -> tuple[uuid.UUID, bool]:
    """(profile id, created); the embedding profile must have a ready collection."""
    name = name.strip()
    if not 1 <= len(name) <= 200:
        raise ProfileError('name must be 1-200 characters')
    embedding = conn.execute(text(
        "SELECT m.kind, c.state FROM model_profiles m LEFT JOIN embedding_collections c"
        " ON c.profile_id = m.id WHERE m.id = :id"), {'id': embedding_profile_id}).first()
    if embedding is None or embedding[0] != 'embedding':
        raise ProfileError('embedding profile not found')
    if embedding[1] != 'ready':
        raise ProfileError('the embedding profile has no ready collection; provision it first')
    config: dict = {}
    if ocr_languages:
        if not OCR_LANGUAGES.match(ocr_languages):
            raise ProfileError('OCR languages look like vie+eng (Tesseract codes joined by +)')
        config['ocr'] = {'languages': ocr_languages}
    row = {'name': name, **code_versions(renderer), 'embedding_profile_id': str(embedding_profile_id),
           'config': config}
    digest = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':'),
                                       ensure_ascii=False).encode()).hexdigest()
    created = conn.execute(text(
        'INSERT INTO pipeline_profiles (name, parser_version, chunker_version, normalizer_version,'
        ' renderer_version, embedding_profile_id, config, config_hash) VALUES (:name, :parser,'
        ' :chunker, :normalizer, :renderer, :embedding, CAST(:config AS jsonb), :hash)'
        ' ON CONFLICT (config_hash) DO NOTHING RETURNING id'),
        {'name': name, 'parser': row['parser_version'], 'chunker': row['chunker_version'],
         'normalizer': row['normalizer_version'], 'renderer': renderer,
         'embedding': embedding_profile_id, 'config': json.dumps(config), 'hash': digest}).scalar()
    if created is not None:
        return created, True
    return conn.execute(text('SELECT id FROM pipeline_profiles WHERE config_hash = :h'),
                        {'h': digest}).scalar_one(), False


def list_pipeline_profiles(conn: Connection) -> list[dict]:
    rows = conn.execute(text(
        'SELECT p.id, p.name, p.parser_version, p.chunker_version, p.normalizer_version,'
        ' p.renderer_version, p.config, p.created_at, m.id AS embedding_id, m.provider,'
        " m.model_name, m.model_revision, m.dimension, m.config->>'locality' AS locality,"
        ' m.enabled, c.state AS collection_state FROM pipeline_profiles p'
        ' JOIN model_profiles m ON m.id = p.embedding_profile_id'
        ' LEFT JOIN embedding_collections c ON c.profile_id = m.id'
        ' ORDER BY p.created_at DESC, p.id')).mappings().all()
    return [{
        'id': str(r['id']), 'name': r['name'], 'parser_version': r['parser_version'],
        'chunker_version': r['chunker_version'], 'normalizer_version': r['normalizer_version'],
        'renderer_version': r['renderer_version'], 'config': r['config'] or {},
        'created_at': r['created_at'],
        'embedding': {
            'id': str(r['embedding_id']), 'provider': r['provider'], 'model_name': r['model_name'],
            'model_revision': r['model_revision'], 'dimension': r['dimension'],
            'locality': ('fixture' if r['provider'].startswith('fixture')
                         else 'local' if r['locality'] == 'local' else 'external'),
            'ready': r['collection_state'] == 'ready'},
    } for r in rows]
