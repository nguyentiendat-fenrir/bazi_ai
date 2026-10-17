"""Shared environment for pipeline-level tests: a migrated database, the runtime
role, a local object store, a provisioned fixture embedding profile, the API app
and logged-in clients, plus helpers to ingest small synthetic books."""
import io
import os
from pathlib import Path
import tempfile
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
from backend.app.ingestion.chunker import ChunkStage
from backend.app.ingestion.ocr import OcrUnavailable
from backend.app.ingestion.ocr_stage import OcrStage
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.publish import PublishStage
from backend.app.ingestion.quality import QualityStage
from backend.app.ingestion.structure import StructureStage
from backend.app.ingestion.worker import run_job
from backend.app.knowledge.candidates import ExtractCandidatesStage
from backend.app.main import create_app
from backend.app.retrieval.indexer import EmbedStage
from backend.app.retrieval.models import provision_collection, register_profile
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path
from tests.integration.db import (ADMIN_URL, create_runtime_login, database_url, drop_database,
                                  drop_role, engine_for, migrated_database, sha)

BLACK = (0, 0, 0)
# Distinct titles: identical ones would repeat at the page edge like a running header.
TITLES = ['THỂ DỤNG', 'CÁCH CỤC', 'ĐẠI VẬN', 'THẬP THẦN', 'NGŨ HÀNH', 'DỤNG THẦN']
PASSWORD = 'correct horse battery staple'


def no_ocr():
    raise OcrUnavailable('no OCR engine in this test')


def default_stages():
    return [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=no_ocr),
            StructureStage(), QualityStage(), ChunkStage(), EmbedStage(), ExtractCandidatesStage(),
            PublishStage()]


class PipelineTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ADMIN_URL:
            raise unittest.SkipTest('BAZI_TEST_DATABASE_URL is not set')
        if font_path() is None:
            raise unittest.SkipTest('no TrueType font for the text fixtures')
        cls.db = migrated_database('head')
        try:
            cls.role, cls.runtime = create_runtime_login(cls.db)
        except BaseException:
            drop_database(cls.db)
            raise
        cls.engine = engine_for(cls.runtime)
        cls.owner_engine = engine_for(database_url(cls.db))
        cls.tmp = Path(tempfile.mkdtemp())
        cls.store = LocalObjectStore(cls.tmp / 'store')
        cls.pipeline = cls.pipeline_profile(f'env-{uuid.uuid4().hex[:6]}')
        with patch.dict(os.environ, {}, clear=True):
            config = load_settings(_env_file=None)
        cls.app = create_app(config, engine=cls.engine, store=cls.store)
        configure_logging('WARNING', [], stream=io.StringIO())
        cls.c, cls.user = cls.client('reviewer')

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
            return str(conn.execute(
                "INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                " normalizer_version, embedding_profile_id, config_hash) VALUES ('p', 'x', '1',"
                " '1', %s, %s) RETURNING id", (profile.id, sha(uuid.uuid4().hex))).fetchone()[0])

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
        return c, str(user['id'])

    # ---- helpers --------------------------------------------------------------------
    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else None

    def pdf(self, pages=2, scan=False) -> bytes:
        builder = PdfBuilder()
        tag = uuid.uuid4().hex[:8]
        for n in range(pages):
            builder.page(lines=[(f'CHƯƠNG {n + 1}: {TITLES[n % len(TITLES)]}', 72, 720, 18, BLACK),
                                (f'Sách {tag} trang {n + 1}: thực thần sinh tài, thương quan.',
                                 72, 680, 11, BLACK)])
        if scan:
            builder.page(image=(0, 0, 612, 792))
        return builder.save(self.tmp / f'{tag}.pdf').read_bytes()

    def queue(self, data=None, pipeline=None, batch=None, rights='private_reference', **pdf):
        """A book version with one queued job; returns (version, generation, job) as str."""
        data = data if data is not None else self.pdf(**pdf)
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
        return str(version), str(gen), str(job)

    def run_pipeline(self, job, stages=None):
        return run_job(self.engine, self.store, job, stages or default_stages(), 'w')

    def ready(self, **kwargs):
        version, gen, job = self.queue(**kwargs)
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        return version, gen

    def publish_book(self, pages, school_key: str) -> str:
        """Ingest ``[(title, paragraph), ...]``, assign and approve its school, publish."""
        builder = PdfBuilder()
        for title, body in pages:
            builder.page(lines=[(title, 72, 720, 18, BLACK), (body, 72, 680, 11, BLACK)])
        version, _ = self.ready(data=builder.save(self.tmp / f'{uuid.uuid4().hex}.pdf').read_bytes())
        school = next(s for s in self.c.get('/api/v1/schools').json()['data']
                      if s['key'] == school_key)
        scope = self.c.post(f'/api/v1/book-versions/{version}/school-scopes',
                            json={'school_id': school['id'], 'reason': 'gán'}).json()['data']
        job = self.c.post('/api/v1/reviews', headers={'Idempotency-Key': uuid.uuid4().hex},
                          json={'entity_kind': 'school_scope', 'entity_id': scope['id'],
                                'decision': 'approve', 'base_revision': 1,
                                'reason': 'đã xem'}).json()['data']['job_id']
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        gen = self.sql('SELECT generation_id::text FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual(self.publish(gen).status_code, 201)
        return version

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
