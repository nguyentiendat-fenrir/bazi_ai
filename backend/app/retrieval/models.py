"""Model registry: embedding profiles and their physical vector collections (docs/04).

Profiles are immutable rows identified by a hash of everything that changes the
vectors. A collection is one ``embeddings_<slug>`` table per profile, created by
the owner role (CLI) with a server-generated name — never a client-supplied
identifier — and a fixed ``vector(D)`` type, so a vector of the wrong
dimension cannot be stored. The ANN (HNSW) index is created on request once the
collection is large enough to need it.
"""
from __future__ import annotations

import hashlib
import json
import re

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .embedding import SECRET_REFS, EmbeddingProfile

_SLUG = re.compile(r'[^a-z0-9]+')
FORBIDDEN_CONFIG_KEYS = re.compile(r'(?i)(api[_-]?key|secret|password|token|authorization)')


class RegistryError(ValueError):
    pass


def profile_hash(provider: str, model_name: str, model_revision: str, dimension: int,
                 config: dict, secret_ref: str | None) -> str:
    canonical = json.dumps({'provider': provider, 'model': model_name, 'revision': model_revision,
                            'dimension': dimension, 'config': config, 'secret_ref': secret_ref},
                           sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()


def register_profile(conn: Connection, provider: str, model_name: str, model_revision: str,
                     dimension: int, config: dict | None = None,
                     secret_ref: str | None = None) -> EmbeddingProfile:
    config = config or {}
    if any(FORBIDDEN_CONFIG_KEYS.search(key) for key in config):
        raise RegistryError('secrets belong in an environment variable named by secret_ref')
    if secret_ref and secret_ref not in SECRET_REFS:
        raise RegistryError(f'secret_ref must be one of {sorted(SECRET_REFS)}')
    if not 8 <= dimension <= 4096:
        raise RegistryError('dimension must be between 8 and 4096')
    digest = profile_hash(provider, model_name, model_revision, dimension, config, secret_ref)
    conn.execute(text(
        'INSERT INTO model_profiles (kind, provider, model_name, model_revision, dimension, config,'
        " secret_ref, profile_hash) VALUES ('embedding', :p, :m, :r, :d, CAST(:c AS jsonb), :s, :h)"
        ' ON CONFLICT (profile_hash) DO NOTHING'),
        {'p': provider, 'm': model_name, 'r': model_revision, 'd': dimension,
         'c': json.dumps(config), 's': secret_ref, 'h': digest})
    return load_profile(conn, digest=digest)


def load_profile(conn: Connection, profile_id=None, digest: str | None = None) -> EmbeddingProfile:
    row = conn.execute(text(
        "SELECT id, provider, model_name, model_revision, dimension, config, secret_ref, profile_hash"
        " FROM model_profiles WHERE kind = 'embedding' AND (id = CAST(:id AS uuid)"
        ' OR profile_hash = :h)'), {'id': str(profile_id) if profile_id else None,
                                    'h': digest}).mappings().first()
    if row is None:
        raise RegistryError('embedding profile not found')
    return EmbeddingProfile(str(row['id']), row['provider'], row['model_name'],
                            row['model_revision'], row['dimension'], row['config'] or {},
                            row['secret_ref'], row['profile_hash'].strip())


def table_name(profile: EmbeddingProfile) -> str:
    slug = _SLUG.sub('_', profile.model_name.lower()).strip('_')[:20] or 'model'
    name = f'embeddings_{slug}_{profile.dimension}_{profile.profile_hash[:8]}'
    if not re.fullmatch(r'embeddings_[a-z0-9_]{1,40}', name):
        raise RegistryError('generated collection name is out of bounds')
    return name


def provision_collection(dbapi_conn, profile: EmbeddingProfile, distance: str = 'cosine') -> str:
    """Owner-role DDL: create the physical table and register it; idempotent.

    ``dbapi_conn`` is a psycopg connection (autocommit or caller-managed).
    """
    if distance not in ('cosine', 'l2', 'inner_product'):
        raise RegistryError('unsupported distance')
    name = table_name(profile)
    dbapi_conn.execute(sql.SQL(
        'CREATE TABLE IF NOT EXISTS {table} ('
        ' chunk_id uuid PRIMARY KEY REFERENCES chunks ON DELETE CASCADE,'
        ' content_hash sha256_hex NOT NULL,'
        ' vector vector({dim}) NOT NULL,'
        ' embedding_hash sha256_hex NOT NULL,'
        ' created_at timestamptz NOT NULL DEFAULT now())').format(
            table=sql.Identifier(name), dim=sql.Literal(profile.dimension)))
    dbapi_conn.execute(sql.SQL('CREATE INDEX IF NOT EXISTS {idx} ON {table} (content_hash)').format(
        idx=sql.Identifier(f'{name}_content_hash_idx'), table=sql.Identifier(name)))
    dbapi_conn.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO bazi_runtime')
                       .format(table=sql.Identifier(name)))
    dbapi_conn.execute(
        'INSERT INTO embedding_collections (profile_id, dimension, distance, physical_table, state)'
        " VALUES (%s, %s, %s, %s, 'ready') ON CONFLICT (profile_id) DO NOTHING",
        (profile.id, profile.dimension, distance, name))
    return name


def create_ann_index(dbapi_conn, profile: EmbeddingProfile) -> None:
    ops = {'cosine': 'vector_cosine_ops', 'l2': 'vector_l2_ops',
           'inner_product': 'vector_ip_ops'}
    distance = dbapi_conn.execute('SELECT distance FROM embedding_collections WHERE profile_id = %s',
                                  (profile.id,)).fetchone()[0]
    name = table_name(profile)
    dbapi_conn.execute(sql.SQL('CREATE INDEX IF NOT EXISTS {idx} ON {table} USING hnsw (vector {ops})')
                       .format(idx=sql.Identifier(f'{name}_hnsw_idx'), table=sql.Identifier(name),
                               ops=sql.SQL(ops[distance])))


def collection_for(conn: Connection, profile_id) -> str | None:
    """Physical table of the profile's ready collection, validated against the registry."""
    row = conn.execute(text(
        "SELECT physical_table, dimension FROM embedding_collections WHERE profile_id = :p"
        " AND state = 'ready'"), {'p': profile_id}).first()
    if row is None:
        return None
    if not re.fullmatch(r'embeddings_[a-z0-9_]{1,40}', row[0]):
        raise RegistryError('registry holds an invalid collection name')
    return row[0]
