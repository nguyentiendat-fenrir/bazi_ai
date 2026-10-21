"""``embed`` stage: lexical entries for every chunk, vectors when a collection is ready.

Lexical (``fts-simple-1``): ``to_tsvector('simple', …)`` over the NFC text and
over the accent-folded text (đ→d), plus trigram on the folded text — no claim
of Vietnamese word segmentation or BM25 (docs/07).

Book text leaves the machine only with consent: a provider whose profile is not
declared ``locality: local`` is external, and needs the version's
``external_processing_allowed`` (docs/12: unknown rights stay local-private).

Vectors: chunks are embedded in batches (one job unit per batch) as their
*contextual* text — the chunk_meta header, the parent's summary, then the child
text (``embed_text``) — so a child that says "như trên" still lands near
questions about its section. The collection's ``content_hash`` is the hash of
that contextual text: a chunk whose vector already has it is skipped, another
chunk with the same contextual text lends its vector, and a chunk whose context
changed (new summary) is embedded again. Provider failures that may pass
(timeouts, 429, 5xx) retry the unit; wrong dimensions fail it.
"""
from __future__ import annotations

import hashlib
import json

from psycopg import sql
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..documents.text import fold
from ..ingestion.worker import JobContext, RetryableError, Unit, UnitFailed
from .embedding import EmbeddingError, build_embedder, checked
from .models import collection_for, load_profile

LEXICAL_VERSION = 'fts-simple-1'
BATCH = 64


def embed_text(header: str | None, summary: str | None, body: str) -> str:
    parts = [header or '']
    if summary:
        parts.append(f'Tóm tắt: {summary}')
    return '\n'.join(p for p in parts if p) + '\n\n' + body if any(parts) else body


def _contextual(conn: Connection, generation_id, ids: list[str] | None = None) -> list[dict]:
    rows = conn.execute(text(
        "SELECT c.id, c.text, c.content_hash, m.meta->>'header' AS header, p.summary"
        ' FROM generation_chunks gc JOIN chunks c ON c.id = gc.chunk_id'
        ' LEFT JOIN chunk_meta m ON m.generation_id = gc.generation_id AND m.chunk_id = c.id'
        ' LEFT JOIN chunk_parents p ON p.id = gc.parent_id'
        ' WHERE gc.generation_id = :g AND (CAST(:ids AS uuid[]) IS NULL OR c.id = ANY(CAST(:ids AS uuid[])))'
        ' ORDER BY gc.ordinal'), {'g': generation_id, 'ids': ids}).mappings().all()
    out = []
    for row in rows:
        contextual = embed_text(row['header'], row['summary'], row['text'])
        out.append({'id': str(row['id']), 'text': row['text'], 'embed_text': contextual,
                    'embed_hash': hashlib.sha256(contextual.encode('utf-8')).hexdigest()})
    return out


def _vector_literal(vector: list[float]) -> str:
    return '[' + ','.join(f'{v:.7g}' for v in vector) + ']'


class EmbedStage:
    name = 'embed'

    def __init__(self, app_env: str = 'dev', transport=None):
        self.app_env = app_env
        self.transport = transport   # injectable HTTP transport for tests

    def _profile(self, ctx: JobContext):
        if 'embedding_profile' not in ctx.state:
            with ctx.engine.connect() as conn:
                profile_id = conn.execute(text(
                    'SELECT embedding_profile_id FROM pipeline_profiles WHERE id = :p'),
                    {'p': ctx.pipeline_profile_id}).scalar_one()
                ctx.state['embedding_profile'] = load_profile(conn, profile_id)
                ctx.state['collection'] = collection_for(conn, profile_id)
                ctx.state['external_allowed'] = conn.execute(text(
                    'SELECT external_processing_allowed FROM book_versions WHERE id = :v'),
                    {'v': ctx.book_version_id}).scalar_one()
        return ctx.state['embedding_profile'], ctx.state['collection']

    def units(self, ctx: JobContext) -> list[Unit]:
        with ctx.engine.connect() as conn:
            chunks = _contextual(conn, ctx.generation_id)
        if not chunks:
            return []
        profile, collection = self._profile(ctx)
        units = []
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start:start + BATCH]
            material = '|'.join(f"{c['id']}:{c['embed_hash']}" for c in batch)
            digest = hashlib.sha256(
                f'{material}|{LEXICAL_VERSION}|{profile.profile_hash}|{collection}'.encode()).hexdigest()
            units.append(Unit(f'batch:{start // BATCH}', digest))
        ctx.state['batches'] = {f'batch:{i // BATCH}': [c['id'] for c in chunks[i:i + BATCH]]
                                for i in range(0, len(chunks), BATCH)}
        return units

    def compute(self, ctx: JobContext, unit: Unit) -> dict:
        ids = ctx.state['batches'][unit.key]
        profile, collection = self._profile(ctx)
        with ctx.engine.connect() as conn:
            chunks = _contextual(conn, ctx.generation_id, ids)
            todo, reused = [], {}
            if collection:
                table = sql.Identifier(collection).as_string(conn.connection.dbapi_connection)
                have = dict(conn.execute(text(f'SELECT chunk_id::text, content_hash FROM {table}'
                                              ' WHERE chunk_id = ANY(CAST(:ids AS uuid[]))'),
                                         {'ids': ids}).all())
                missing = [c for c in chunks if (have.get(c['id']) or '').strip() != c['embed_hash']]
                same = dict(conn.execute(text(
                    f'SELECT DISTINCT ON (content_hash) content_hash, vector::text FROM {table}'
                    ' WHERE content_hash = ANY(:hashes)'),
                    {'hashes': [c['embed_hash'] for c in missing]}).all())
                same = {k.strip(): v for k, v in same.items()}
                for chunk in missing:
                    if chunk['embed_hash'] in same:
                        reused[chunk['id']] = same[chunk['embed_hash']]
                    else:
                        todo.append(chunk)
        vectors = {}
        if todo and not (profile.is_fixture or profile.config.get('locality') == 'local'
                         or ctx.state['external_allowed']):
            raise UnitFailed('EXTERNAL_PROCESSING_DENIED', 'this version may not be sent to an'
                             ' external embedding provider; use a local profile or allow it')
        if todo:
            prefix = profile.config.get('passage_prefix', '')
            try:
                embedder = ctx.state.get('embedder') or build_embedder(profile, self.app_env,
                                                                      self.transport)
                ctx.state['embedder'] = embedder
                result = checked(embedder.embed([prefix + c['embed_text'] for c in todo]), profile)
            except EmbeddingError as exc:
                if exc.retryable:
                    raise RetryableError(exc.code, str(exc)) from None
                raise UnitFailed(exc.code, str(exc)) from None
            vectors = {c['id']: _vector_literal(v) for c, v in zip(todo, result)}
        return {'chunks': [{'id': c['id'], 'text': c['text'], 'hash': c['embed_hash']}
                           for c in chunks],
                'vectors': {**reused, **vectors}, 'collection': collection,
                'computed': len(vectors), 'reused': len(reused)}

    def persist(self, conn: Connection, ctx: JobContext, unit: Unit, result: dict) -> dict:
        for chunk in result['chunks']:
            conn.execute(text(
                'INSERT INTO search_entries (chunk_id, lexical_profile_version, text_nfc,'
                " text_folded, ts_nfc, ts_folded) VALUES (:c, :v, :t, :f, to_tsvector('simple', :t),"
                " to_tsvector('simple', :f)) ON CONFLICT (chunk_id, lexical_profile_version)"
                ' DO NOTHING'),
                {'c': chunk['id'], 'v': LEXICAL_VERSION, 't': chunk['text'], 'f': fold(chunk['text'])})
        if result['collection'] and result['vectors']:
            table = sql.Identifier(result['collection']).as_string(conn.connection.dbapi_connection)
            hashes = {c['id']: c['hash'] for c in result['chunks']}
            for chunk_id, vector in result['vectors'].items():
                conn.execute(text(
                    f'INSERT INTO {table} (chunk_id, content_hash, vector, embedding_hash)'
                    ' VALUES (:c, :h, CAST(:v AS vector), :eh) ON CONFLICT (chunk_id) DO UPDATE'
                    ' SET content_hash = EXCLUDED.content_hash, vector = EXCLUDED.vector,'
                    ' embedding_hash = EXCLUDED.embedding_hash'
                    f' WHERE {table}.content_hash <> EXCLUDED.content_hash'),
                    {'c': chunk_id, 'h': hashes[chunk_id], 'v': vector,
                     'eh': hashlib.sha256(vector.encode()).hexdigest()})
        output = {'lexical': len(result['chunks']), 'computed': result['computed'],
                  'reused': result['reused'], 'collection': result['collection']}
        # Work counters only for work done now; a reused unit (attach) adds none.
        conn.execute(text(
            'UPDATE ingestion_jobs SET counters = counters || jsonb_build_object('
            " 'chunks_indexed', coalesce((counters->>'chunks_indexed')::int, 0) + :n,"
            " 'embeddings_computed', coalesce((counters->>'embeddings_computed')::int, 0) + :c)"
            ' WHERE id = :j'), {'j': ctx.job_id, 'n': output['lexical'], 'c': output['computed']})
        self.attach(conn, ctx, unit, output)
        return output

    def attach(self, conn: Connection, ctx: JobContext, unit: Unit, output: dict) -> None:
        conn.execute(text('UPDATE generations SET coverage = coverage || CAST(:c AS jsonb)'
                          ' WHERE id = :g'),
                     {'g': ctx.generation_id, 'c': json.dumps({
                         'lexical_profile_version': LEXICAL_VERSION,
                         'embedding_collection': output['collection']})})
