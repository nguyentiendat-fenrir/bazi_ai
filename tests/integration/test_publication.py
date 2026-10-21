"""Sealing, publication gates and the atomic active corpus release on PostgreSQL (T018)."""
from concurrent.futures import ThreadPoolExecutor
import io
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import warnings

import psycopg

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

from backend.app.auth.service import create_user
from backend.app.core.config import load_settings
from backend.app.core.logging import configure_logging
from backend.app.documents.releases import ranges
from backend.app.ingestion.chunker import ChunkStage
from backend.app.ingestion.ocr import OcrUnavailable
from backend.app.ingestion.ocr_stage import OcrStage
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.publish import PublishStage
from backend.app.ingestion.quality import QualityStage
from backend.app.ingestion.structure import StructureStage
from backend.app.ingestion.worker import Unit, run_job
from backend.app.main import create_app
from backend.app.retrieval.indexer import EmbedStage
from backend.app.retrieval.models import provision_collection, register_profile
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path
from tests.integration.db import (ADMIN_URL, create_runtime_login, database_url, drop_database,
                                  drop_role, engine_for, migrated_database, sha)

BLACK = (0, 0, 0)
PASSWORD = 'correct horse battery staple'


def no_ocr():
    raise OcrUnavailable('no OCR engine in this test')


class RangeTests(unittest.TestCase):
    def test_ranges(self):
        self.assertEqual(ranges([7, 1, 2, 3, 9, 10]), ['1-3', '7', '9-10'])
        self.assertEqual(ranges([]), [])


class PublicationTests(unittest.TestCase):
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
        cls.tmp = Path(tempfile.mkdtemp())
        cls.store = LocalObjectStore(cls.tmp / 'store')
        cls.pipeline = cls.pipeline_profile('pub-main')
        with patch.dict(os.environ, {}, clear=True):
            config = load_settings(_env_file=None)
        cls.app = create_app(config, engine=cls.engine, store=cls.store)
        configure_logging('WARNING', [], stream=io.StringIO())
        cls.c, cls.user = cls.client('reviewer')
        cls.admin, _ = cls.client('admin')
        cls.empty = cls.c.get('/api/v1/corpus-releases')   # before anything is published

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        cls.owner_engine.dispose()
        drop_database(cls.db)
        drop_role(cls.role)

    @classmethod
    def pipeline_profile(cls, model, provision=True):
        with cls.owner_engine.begin() as conn:
            profile = register_profile(conn, 'fixture-hashing', model, 'r1', 32)
        with psycopg.connect(database_url(cls.db), autocommit=True) as conn:
            if provision:
                provision_collection(conn, profile)
            return conn.execute(
                "INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                " normalizer_version, embedding_profile_id, config_hash) VALUES ('p', 'x', '1',"
                " '1', %s, %s) RETURNING id", (profile.id, sha(uuid.uuid4().hex))).fetchone()[0]

    @classmethod
    def client(cls, role):
        email = f'{uuid.uuid4().hex[:8]}@example.test'
        with cls.owner_engine.begin() as conn:
            user = create_user(conn, email, PASSWORD, role)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            c = TestClient(cls.app, client=('127.0.0.1', 40000))
        login = c.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
        c.headers['X-CSRF-Token'] = login.json()['data']['csrf_token']
        return c, user['id']

    # ---- helpers --------------------------------------------------------------------
    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else None

    def queue(self, pages=2, scan=False, pipeline=None, batch=None, rights='private_reference',
              data=None):
        """A book version with one queued job; returns (version, generation, job)."""
        if data is None:
            builder = PdfBuilder()
            tag = uuid.uuid4().hex[:8]
            for n in range(pages):
                builder.page(lines=[(f'CHƯƠNG {n + 1}: MỤC {tag}', 72, 720, 18, BLACK),
                                    (f'Sách {tag} trang {n + 1}: thực thần sinh tài, thương quan.', 72, 680,
                                     11, BLACK)])
            if scan:
                builder.page(image=(0, 0, 612, 792))
            data = builder.save(self.tmp / f'{tag}.pdf').read_bytes()
        with self.engine.begin() as conn:
            obj = store_object(conn, self.store, io.BytesIO(data), 'application/pdf')
        book = self.sql("INSERT INTO books (title, normalized_title, language, created_by)"
                        " VALUES ('b', 'b', 'vi', %s) RETURNING id", self.user)[0][0]
        version = self.sql("INSERT INTO book_versions (book_id, object_id, edition_label,"
                           " version_no, rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1, %s,"
                           " %s) RETURNING id", book, obj['id'], rights, self.user)[0][0]
        pipeline = pipeline or self.pipeline
        gen = self.sql('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                       ' VALUES (%s, %s) RETURNING id', version, pipeline)[0][0]
        job = self.sql('INSERT INTO ingestion_jobs (batch_id, book_version_id, generation_id,'
                       ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s, %s)'
                       ' RETURNING id', batch, version, gen, pipeline, self.user)[0][0]
        return str(version), str(gen), job

    def run_pipeline(self, job):
        stages = [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=no_ocr),
                  StructureStage(), QualityStage(), ChunkStage(), EmbedStage(), PublishStage()]
        return run_job(self.engine, self.store, job, stages, 'w')

    def ready(self, **kwargs):
        version, gen, job = self.queue(**kwargs)
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        return version, gen

    def publish(self, gen, client=None, **body):
        return (client or self.c).post(f'/api/v1/generations/{gen}/publish', json=body,
                                       headers={'Idempotency-Key': uuid.uuid4().hex})

    def active(self):
        rows = self.sql("SELECT release_id::text FROM active_corpus WHERE slot = 'default'")
        return rows[0][0] if rows else None

    def members(self, release):
        return {(str(v), str(g)) for v, g in self.sql(
            'SELECT book_version_id, generation_id FROM corpus_members WHERE release_id = %s',
            release)}

    # ---- tests ----------------------------------------------------------------------
    def test_empty_corpus_is_a_normal_200(self):
        self.assertEqual(self.empty.status_code, 200, self.empty.text)
        self.assertEqual(self.empty.json()['data'], {'active': None, 'releases': []})

    def test_sealed_generation_publishes_into_a_new_active_release(self):
        version, gen = self.ready()
        view = self.c.get(f'/api/v1/generations/{gen}').json()['data']
        self.assertEqual((view['state'], view['coverage']['excluded_ranges'],
                          view['in_active_release']), ('ready', [], False))
        self.assertRegex(view['manifest_hash'], r'^[0-9a-f]{64}$')
        # Membership is frozen once sealed.
        with self.assertRaises(psycopg.errors.RestrictViolation):
            self.sql('DELETE FROM generation_chunks WHERE generation_id = %s', gen)
        before = self.active()
        book = self.sql('SELECT book_id FROM book_versions WHERE id = %s', version)[0][0]
        coverage = lambda: self.c.get(f'/api/v1/books/{book}').json()['data']['active_coverage']
        self.assertIsNone(coverage())
        response = self.publish(gen)
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()['data']
        release = data['release']['id']
        self.assertEqual(coverage(), {'versions': 1, 'total': view['coverage']['total'],
                                      'accepted': view['coverage']['accepted'],
                                      'review_required': 0, 'excluded': 0})
        self.assertEqual((data['activated'], data['release']['state'], data['release']['parent_id']),
                         (True, 'active', before))
        self.assertEqual(self.active(), release)
        self.assertIn((version, gen), self.members(release))
        if before:
            self.assertEqual(self.members(release) - {(version, gen)}, self.members(before))
            self.assertEqual(self.sql('SELECT state FROM corpus_releases WHERE id = %s', before),
                             [('retired',)])
        self.assertEqual(self.sql('SELECT state FROM generations WHERE id = %s', gen),
                         [('published',)])
        # Publication approves nothing: topic proposals stay proposals.
        self.assertEqual(self.sql("SELECT DISTINCT status FROM chunk_classifications"
                                  " WHERE generation_id = %s", gen), [('proposed',)])
        listing = self.c.get('/api/v1/corpus-releases').json()['data']
        self.assertEqual(listing['active']['release_id'], release)
        detail = self.c.get(f'/api/v1/corpus-releases/{release}').json()['data']
        self.assertIn({'book_version_id': version, 'generation_id': gen}, detail['members'])
        again = self.publish(gen)
        self.assertEqual((again.status_code, again.json()['code']), (409, 'GENERATION_NOT_READY'))

    def test_unfinished_or_failed_generation_never_touches_the_active_release(self):
        self.ready_and_publish()
        before = self.active()
        _, failed_gen, job = self.queue(data=b'%PDF-1.4\nnot really a pdf\n%%EOF\n')
        self.assertEqual(self.run_pipeline(job), 'failed')
        _, queued_gen, _ = self.queue()
        for gen in (failed_gen, queued_gen):
            response = self.publish(gen)
            self.assertEqual((response.status_code, response.json()['code']),
                             (409, 'GENERATION_NOT_READY'))
        self.assertEqual(self.active(), before)

    def ready_and_publish(self):
        version, gen = self.ready()
        self.assertEqual(self.publish(gen).status_code, 201)
        return version, gen

    def test_partial_coverage_needs_the_exact_ranges(self):
        _, gen = self.ready(pages=2, scan=True)          # page 3 is a scan without OCR
        before = self.active()
        refused = self.publish(gen)
        self.assertEqual((refused.status_code, refused.json()['code']),
                         (409, 'PARTIAL_NOT_ACKNOWLEDGED'))
        self.assertIn('3', refused.json()['detail'])
        wrong = self.publish(gen, allow_partial=True, ack_excluded_ranges=['2'])
        self.assertEqual(wrong.status_code, 409)
        self.assertEqual(self.active(), before)
        accepted = self.publish(gen, allow_partial=True, ack_excluded_ranges=['3'])
        self.assertEqual(accepted.status_code, 201, accepted.text)
        self.assertEqual(accepted.json()['data']['coverage']['excluded_ranges'], ['3'])
        publication = self.sql("SELECT coverage->'publication' FROM generations WHERE id = %s",
                               gen)[0][0]
        self.assertTrue(publication['acknowledged_partial'])

    def test_gates_rights_profile_and_index(self):
        self.ready_and_publish()
        _, restricted = self.ready(rights='restricted')
        response = self.publish(restricted)
        self.assertEqual(response.json()['code'], 'RIGHTS_RESTRICTED')
        _, other = self.ready(pipeline=self.pipeline_profile(f'other-{uuid.uuid4().hex[:6]}'))
        self.assertEqual(self.publish(other).json()['code'], 'EMBEDDING_PROFILE_MISMATCH')
        _, lexical_only = self.ready(
            pipeline=self.pipeline_profile(f'noidx-{uuid.uuid4().hex[:6]}', provision=False))
        self.assertEqual(self.publish(lexical_only).json()['code'], 'INDEX_INCOMPLETE')
        reader, _ = self.client('reader')
        self.assertEqual(self.publish(restricted, client=reader).status_code, 403)

    def test_readers_see_whole_snapshots_while_publishing(self):
        self.ready_and_publish()
        stop = threading.Event()
        seen = []

        def read():
            with psycopg.connect(database_url(self.db), autocommit=True) as conn:
                while not stop.is_set():
                    seen.append(conn.execute(
                        "SELECT a.release_id::text, (SELECT count(*) FROM corpus_members m"
                        " JOIN generation_chunks gc ON gc.generation_id = m.generation_id"
                        " WHERE m.release_id = a.release_id) FROM active_corpus a"
                        " WHERE a.slot = 'default'").fetchone())
        ready = [self.ready()[1] for _ in range(3)]
        with ThreadPoolExecutor(2) as pool:
            reader = pool.submit(read)
            for gen in ready:
                self.assertEqual(self.publish(gen).status_code, 201)
            stop.set()
            reader.result()
        totals = dict(self.sql(
            'SELECT r.id::text, (SELECT count(*) FROM corpus_members m JOIN generation_chunks gc'
            ' ON gc.generation_id = m.generation_id WHERE m.release_id = r.id)'
            ' FROM corpus_releases r'))
        self.assertTrue(seen)
        for release, chunks in seen:      # never a release mid-build, never a partial count
            self.assertEqual(chunks, totals[release])
        self.assertGreaterEqual(len({r for r, _ in seen}), 1)

    def test_concurrent_publications_keep_both_books(self):
        self.ready_and_publish()
        (v1, g1), (v2, g2) = self.ready(), self.ready()
        other, _ = self.client('reviewer')
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda args: self.publish(args[0], client=args[1]),
                                    [(g1, self.c), (g2, other)]))
        self.assertEqual([r.status_code for r in results], [201, 201])
        self.assertTrue({(v1, g1), (v2, g2)} <= self.members(self.active()))

    def test_activation_is_compare_and_swap(self):
        self.ready_and_publish()
        current = self.active()
        _, gen = self.ready()
        built = self.publish(gen, activate=False)
        self.assertEqual(built.status_code, 201, built.text)
        release = built.json()['data']['release']['id']
        self.assertEqual((built.json()['data']['release']['state'], self.active()),
                         ('ready', current))
        url = f'/api/v1/corpus-releases/{release}/activate'
        self.assertEqual(self.c.post(url, json={'expected_active_id': current}).status_code, 403)
        stale = self.admin.post(url, json={'expected_active_id': str(uuid.uuid4())})
        self.assertEqual((stale.status_code, stale.json()['code']), (409, 'ACTIVE_CHANGED'))
        done = self.admin.post(url, json={'expected_active_id': current})
        self.assertEqual((done.status_code, done.json()['data']['state']), (200, 'active'))
        self.assertEqual(self.admin.post(url, json={'expected_active_id': current}).status_code,
                         200)                                  # retried request: no-op
        self.assertEqual(self.active(), release)
        retired = self.admin.post(f'/api/v1/corpus-releases/{current}/activate',
                                  json={'expected_active_id': release})
        self.assertEqual(retired.json()['code'], 'RELEASE_NOT_READY')

    def test_auto_publish_from_batch(self):
        batch = self.sql("INSERT INTO ingestion_batches (created_by, name, config) VALUES"
                         """ (%s, 'auto', '{"auto_publish": true}') RETURNING id""",
                         self.user)[0][0]
        version, gen, job = self.queue(batch=batch)
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        counters = self.sql('SELECT counters FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual(counters['auto_publish'], 'published')
        self.assertIn((version, gen), self.members(self.active()))
        before = self.active()
        _, partial, job = self.queue(batch=batch, scan=True)
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        counters = self.sql('SELECT counters FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual(counters['auto_publish'], 'PARTIAL_NOT_ACKNOWLEDGED')
        self.assertEqual((self.active(), self.sql('SELECT state FROM generations WHERE id = %s',
                                                  partial)), (before, [('ready',)]))

    def test_resumed_job_finishes_stages_after_publish_without_touching_the_seal(self):
        """A worker that dies after publish (during rule candidates) resumes the job: the
        reused pre-publish units must not be re-linked into the sealed generation."""
        class AfterPublish:
            name = 'extract_candidates'
            calls = 0

            def units(self, ctx):
                return [Unit('after', '0' * 64)]

            def compute(self, ctx, unit):
                AfterPublish.calls += 1
                if AfterPublish.calls == 1:
                    raise RuntimeError('worker died after publish')
                return {}

            def persist(self, conn, ctx, unit, result):
                return {}
        batch = self.sql("INSERT INTO ingestion_batches (created_by, name, config) VALUES"
                         """ (%s, 'auto', '{"auto_publish": true}') RETURNING id""",
                         self.user)[0][0]
        version, gen, job = self.queue(batch=batch)
        stages = [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=no_ocr),
                  StructureStage(), QualityStage(), ChunkStage(), EmbedStage(), PublishStage(),
                  AfterPublish()]
        with self.assertRaises(RuntimeError):
            run_job(self.engine, self.store, job, stages, 'w')
        self.sql("UPDATE job_stages SET state = 'pending', lease_until = NULL"
                 " WHERE job_id = %s AND state = 'running'", job)     # the watchdog's job
        self.assertEqual(run_job(self.engine, self.store, job, stages, 'w2'), 'succeeded')
        self.assertEqual(self.sql('SELECT state FROM generations WHERE id = %s', gen),
                         [('published',)])
        self.assertIn((version, gen), self.members(self.active()))


if __name__ == '__main__':
    unittest.main()
