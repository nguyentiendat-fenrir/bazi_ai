"""Embedding registry, collections and the embed stage on PostgreSQL (T016)."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import httpx
import psycopg

from backend.app.ingestion.chunker import ChunkStage
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.structure import StructureStage
from backend.app.ingestion.worker import run_job
from backend.app.retrieval import embedding as E
from backend.app.retrieval.indexer import EmbedStage
from backend.app.retrieval.models import (RegistryError, provision_collection, register_profile,
                                          table_name)
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path
from tests.integration.db import (ADMIN_URL, create_runtime_login, database_url, drop_database,
                                  drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

BLACK = (0, 0, 0)


class IndexingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ADMIN_URL:
            raise unittest.SkipTest('BAZI_TEST_DATABASE_URL is not set')
        if font_path() is None:
            raise unittest.SkipTest('no TrueType font for the text fixtures')
        cls.db = migrated_database('head')
        cls.role, cls.runtime = create_runtime_login(cls.db)
        cls.engine = engine_for(cls.runtime)
        cls.owner_engine = engine_for(database_url(cls.db))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.owner_engine.dispose()
        drop_database(cls.db)
        drop_role(cls.role)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = LocalObjectStore(self.tmp / 'store')

    def profile(self, provider='fixture-hashing', dimension=64, provision=True, **config):
        with self.owner_engine.begin() as conn:
            profile = register_profile(conn, provider, f'model-{uuid.uuid4().hex[:6]}', 'r1',
                                       dimension, config, config.pop('secret_ref', None)
                                       if 'secret_ref' in config else None)
        if provision:
            with psycopg.connect(database_url(self.db), autocommit=True) as conn:
                provision_collection(conn, profile)
        return profile

    def pdf(self, lines):
        builder = PdfBuilder()
        builder.page(lines=[(t, 72, 720 - 20 * i, 11, BLACK) for i, t in enumerate(lines)])
        return builder.save(self.tmp / f'{uuid.uuid4().hex}.pdf')

    def job(self, pdf, profile):
        with self.engine.begin() as conn, open(pdf, 'rb') as source:
            obj = store_object(conn, self.store, source, 'application/pdf')
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            user = f.user()
            book = f.one("INSERT INTO books (title, normalized_title, language, created_by)"
                         " VALUES ('i', 'i', 'vi', %s) RETURNING id", user)
            version = f.one("INSERT INTO book_versions (book_id, object_id, edition_label,"
                            " version_no, rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1,"
                            " 'private_reference', %s) RETURNING id", book, obj['id'], user)
            pipeline = f.one("INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                             " normalizer_version, embedding_profile_id, config_hash) VALUES ('p',"
                             " 'x', '1', '1', %s, %s) RETURNING id", profile.id, sha(uuid.uuid4().hex))
            gen = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                        ' VALUES (%s, %s) RETURNING id', version, pipeline)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, gen, pipeline, user)
        self.last = (version, pipeline, user)
        return job, gen

    def next_job(self):
        version, pipeline, user = self.last
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            gen = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                        ' VALUES (%s, %s) RETURNING id', version, pipeline)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, gen, pipeline, user)
        return job, gen

    def stages(self, embed=None):
        return [ValidatePdfStage(), ExtractPdfStage(), StructureStage(), ChunkStage(),
                embed or EmbedStage()]

    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db)) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else None

    # ---- registry -------------------------------------------------------------------
    def test_registry_is_deterministic_and_secret_free(self):
        with self.owner_engine.begin() as conn:
            a = register_profile(conn, 'fixture-hashing', 'm-det', 'r1', 32, {'k': 1})
            b = register_profile(conn, 'fixture-hashing', 'm-det', 'r1', 32, {'k': 1})
            self.assertEqual((a.id, a.profile_hash), (b.id, b.profile_hash))
            with self.assertRaises(RegistryError):
                register_profile(conn, 'openai_compatible', 'm', 'r', 32, {'api_key': 'sk-x'})
            with self.assertRaises(RegistryError):
                register_profile(conn, 'openai_compatible', 'm', 'r', 32, {}, 'HOME')
        self.assertRegex(table_name(a), r'^embeddings_m_det_32_[0-9a-f]{8}$')

    def test_collection_rejects_wrong_dimension(self):
        profile = self.profile(dimension=16)
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            provision_collection(conn, profile)   # idempotent
            chunk = Factory(conn).chunk(text=f'k {uuid.uuid4().hex}')
            with self.assertRaises(psycopg.errors.DataException):
                conn.execute(f'INSERT INTO {table_name(profile)} (chunk_id, content_hash, vector,'
                             " embedding_hash) VALUES (%s, %s, '[1,2,3]', %s)",
                             (chunk, sha('x'), sha('y')))

    def test_fixture_refused_in_production(self):
        profile = self.profile(provision=False)
        with self.assertRaises(E.EmbeddingError) as caught:
            E.build_embedder(profile, 'production')
        self.assertEqual(caught.exception.code, 'FIXTURE_IN_PRODUCTION')

    # ---- embed stage ----------------------------------------------------------------
    def test_pipeline_indexes_lexical_and_vectors_once(self):
        profile = self.profile()
        job, gen = self.job(self.pdf(['CHƯƠNG 1: KHÁCH CHỦ', 'Khách và Chủ được xét theo nhiều cấp độ.',
                                      'Thể và Dụng là hai khái niệm khác.']), profile)
        self.assertEqual(run_job(self.engine, self.store, job, self.stages(), 'w'), 'succeeded')
        table = table_name(profile)
        counts = self.sql(f'SELECT (SELECT count(*) FROM generation_chunks WHERE generation_id = %s),'
                          ' (SELECT count(*) FROM search_entries s JOIN generation_chunks gc'
                          ' ON gc.chunk_id = s.chunk_id WHERE gc.generation_id = %s),'
                          f' (SELECT count(*) FROM {table} e JOIN generation_chunks gc'
                          ' ON gc.chunk_id = e.chunk_id WHERE gc.generation_id = %s)', gen, gen, gen)[0]
        self.assertTrue(counts[0] > 0 and counts[0] == counts[1] == counts[2], counts)
        hit = self.sql("SELECT count(*) FROM search_entries WHERE ts_folded @@ plainto_tsquery("
                       "'simple', 'khach chu')")[0][0]
        self.assertGreater(hit, 0)                       # accent-insensitive lexical match
        nearest = self.sql(f'SELECT e2.chunk_id = e1.chunk_id FROM {table} e1 CROSS JOIN LATERAL ('
                           f' SELECT chunk_id FROM {table} ORDER BY vector <=> e1.vector LIMIT 1) e2'
                           ' LIMIT 3')
        self.assertTrue(all(row[0] for row in nearest))  # cosine neighbour of a vector is itself
        # Replay in a new generation: nothing recomputed, nothing duplicated.
        embed = EmbedStage()
        job2, gen2 = self.next_job()
        self.assertEqual(run_job(self.engine, self.store, job2, self.stages(embed), 'w'), 'succeeded')
        counters = self.sql('SELECT counters FROM ingestion_jobs WHERE id = %s', job2)[0][0]
        self.assertEqual(counters.get('embeddings_computed', 0), 0)
        self.assertEqual(self.sql(f'SELECT count(*) FROM {table}')[0][0], counts[2])

    def test_same_text_reuses_vector_without_provider_call(self):
        profile = self.profile()
        lines = ['Đoạn văn y hệt dùng để kiểm tra tái sử dụng vector theo nội dung.']
        job, _ = self.job(self.pdf(lines), profile)
        run_job(self.engine, self.store, job, self.stages(), 'w')
        calls = []
        real = E.HashingEmbedder.embed

        def counting(self_, texts):
            calls.append(len(texts))
            return real(self_, texts)
        with patch.object(E.HashingEmbedder, 'embed', counting):
            job2, gen2 = self.job(self.pdf(lines + ['']), profile)   # other book, same text
            self.assertEqual(run_job(self.engine, self.store, job2, self.stages(), 'w'), 'succeeded')
        self.assertEqual(calls, [])

    def test_no_collection_means_lexical_only(self):
        profile = self.profile(provision=False)
        job, gen = self.job(self.pdf(['Chỉ có tìm kiếm từ khóa ở đây.']), profile)
        self.assertEqual(run_job(self.engine, self.store, job, self.stages(), 'w'), 'succeeded')
        coverage = self.sql('SELECT coverage FROM generations WHERE id = %s', gen)[0][0]
        self.assertIsNone(coverage['embedding_collection'])
        self.assertGreater(self.sql('SELECT count(*) FROM search_entries s JOIN generation_chunks gc'
                                    ' ON gc.chunk_id = s.chunk_id WHERE gc.generation_id = %s',
                                    gen)[0][0], 0)

    def test_openai_compatible_provider(self):
        seen = []

        def handler(request):
            seen.append((request.headers.get('authorization'), json.loads(request.content)))
            body = json.loads(request.content)
            return httpx.Response(200, json={'data': [
                {'index': i, 'embedding': [0.1] * 8} for i in range(len(body['input']))]})
        with self.owner_engine.begin() as conn:
            profile = register_profile(conn, 'openai_compatible', f'emb-{uuid.uuid4().hex[:6]}',
                                       'r1', 8, {'base_url': 'http://embed.local/v1',
                                                 'passage_prefix': 'passage: ',
                                                 'locality': 'local'}, 'EMBEDDING_API_KEY')
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            provision_collection(conn, profile)
        job, _ = self.job(self.pdf(['Gửi tới máy chủ embedding tương thích OpenAI.']), profile)
        with patch.dict(os.environ, {'EMBEDDING_API_KEY': 'test-token-123'}):
            state = run_job(self.engine, self.store, job,
                            self.stages(EmbedStage(transport=httpx.MockTransport(handler))), 'w')
        self.assertEqual(state, 'succeeded')
        auth, body = seen[0]
        self.assertEqual(auth, 'Bearer test-token-123')
        self.assertEqual(body['model'], profile.model_name)
        self.assertTrue(body['input'][0].startswith('passage: '))

    def test_provider_failures(self):
        with self.owner_engine.begin() as conn:
            profile = register_profile(conn, 'openai_compatible', f'emb-{uuid.uuid4().hex[:6]}',
                                       'r1', 8, {'base_url': 'http://embed.local/v1',
                                                 'locality': 'local'})
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            provision_collection(conn, profile)
        cases = [(lambda r: httpx.Response(429), 'retry_wait', 'PROVIDER_UNAVAILABLE'),
                 (lambda r: httpx.Response(200, json={'data': [
                     {'index': i, 'embedding': [0.1] * 5}
                     for i in range(len(json.loads(r.content)['input']))]}),
                  'failed', 'EMBEDDING_DIMENSION_MISMATCH')]
        for handler, state, code in cases:
            with self.subTest(code=code):
                job, _ = self.job(self.pdf([f'Lỗi nhà cung cấp {code}.']), profile)
                result = run_job(self.engine, self.store, job,
                                 self.stages(EmbedStage(transport=httpx.MockTransport(handler))), 'w')
                self.assertEqual(result, state)
                error = self.sql('SELECT error FROM ingestion_jobs WHERE id = %s', job)[0][0]
                self.assertEqual(error['code'], code)

    def test_external_provider_needs_consent(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={'data': [
                {'index': i, 'embedding': [0.1] * 8}
                for i in range(len(json.loads(request.content)['input']))]})
        with self.owner_engine.begin() as conn:
            profile = register_profile(conn, 'openai_compatible', f'emb-{uuid.uuid4().hex[:6]}',
                                       'r1', 8, {'base_url': 'https://api.example.test/v1'})
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            provision_collection(conn, profile)
        job, _ = self.job(self.pdf(['Văn bản sách không được gửi ra ngoài khi chưa cho phép.']),
                          profile)
        stages = self.stages(EmbedStage(transport=httpx.MockTransport(handler)))
        self.assertEqual(run_job(self.engine, self.store, job, stages, 'w'), 'failed')
        error = self.sql('SELECT error FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual((error['code'], seen), ('EXTERNAL_PROCESSING_DENIED', []))
        self.sql('UPDATE book_versions SET external_processing_allowed = true WHERE id = %s',
                 self.last[0])
        job2, _ = self.next_job()
        self.assertEqual(run_job(self.engine, self.store, job2, stages, 'w'), 'succeeded')
        self.assertEqual(len(seen), 1)


if __name__ == '__main__':
    unittest.main()
