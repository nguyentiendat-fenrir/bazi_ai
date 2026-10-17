"""Catalog, batches and uploads on PostgreSQL as the runtime role (T009)."""
from concurrent.futures import ThreadPoolExecutor
import io
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid
import warnings
import zipfile

import psycopg

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

from backend.app.auth.service import create_user
from backend.app.core.config import load_settings
from backend.app.core.logging import configure_logging
from backend.app.main import create_app
from backend.app.storage.local import LocalObjectStore
from tests.integration.db import (create_runtime_login, database_url, drop_database, drop_role,
                                  engine_for, migrated_database, sha)

DB_NAME = ROLE = RUNTIME = None
PASSWORD = 'correct horse battery staple'


def setUpModule():
    global DB_NAME, ROLE, RUNTIME
    DB_NAME = migrated_database('head')
    try:
        ROLE, RUNTIME = create_runtime_login(DB_NAME)
    except BaseException:
        drop_database(DB_NAME)
        raise


def tearDownModule():
    if DB_NAME:
        drop_database(DB_NAME)
    if ROLE:
        drop_role(ROLE)


def owner(query, *params):
    with psycopg.connect(database_url(DB_NAME), autocommit=True) as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall() if cursor.description else None


def pdf_bytes(tag: str = '') -> bytes:
    return b'%PDF-1.4\n% synthetic test fixture ' + (tag or uuid.uuid4().hex).encode() + b'\n%%EOF\n'


def docx_bytes(extra: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="w"><w:body/></w:document>')
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return buffer.getvalue()


def pipeline_profile() -> str:
    model = owner("INSERT INTO model_profiles (kind, provider, model_name, model_revision, dimension,"
                  " profile_hash) VALUES ('embedding', 'local', 'e5', 'r1', 768, %s) RETURNING id",
                  sha(uuid.uuid4().hex))[0][0]
    return str(owner("INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                     " normalizer_version, embedding_profile_id, config_hash) VALUES ('default',"
                     " 'p1', 'c1', 'n1', %s, %s) RETURNING id", model, sha(uuid.uuid4().hex))[0][0])


class UploadTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.app = self.make_app()

    def make_app(self, **settings):
        with patch.dict(os.environ, {}, clear=True):
            config = load_settings(_env_file=None, **settings)
        app = create_app(config, engine=engine_for(RUNTIME),
                         store=LocalObjectStore(self.tmp.name, config.max_upload_bytes))
        configure_logging('WARNING', [], stream=io.StringIO())
        return app

    def client(self, role='reviewer', app=None):
        email = f'{uuid.uuid4().hex[:8]}@example.test'
        with engine_for(database_url(DB_NAME)).begin() as conn:
            create_user(conn, email, PASSWORD, role)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            c = TestClient(app or self.app, client=('127.0.0.1', 40000))
        token = c.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
        c.headers['X-CSRF-Token'] = token.json()['data']['csrf_token']
        c.user_email = email
        return c

    def batch(self, c, profile=None):
        body = {'name': 'pilot'} | ({'pipeline_profile_id': profile} if profile else {})
        response = c.post('/api/v1/ingestion-batches', json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['data']['id']

    def upload(self, c, batch, data, name='Manh phái sơ cấp.pdf', key=None, **fields):
        form = {'batch_id': batch, 'rights_status': 'private_reference', **fields}
        return c.post('/api/v1/uploads', data=form, files={'file': (name, data, 'application/pdf')},
                      headers={'Idempotency-Key': key or uuid.uuid4().hex})


class UploadTests(UploadTestCase):
    def test_accepted_upload_creates_private_book_and_version(self):
        c = self.client()
        batch = self.batch(c)
        data = pdf_bytes()
        response = self.upload(c, batch, data)
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()['data']
        self.assertEqual((result['outcome'], result['sha256'], result['size_bytes']),
                         ('accepted', sha_bytes(data), len(data)))
        self.assertIsNone(result['job_id'])  # batch without pipeline profile
        book = c.get(f"/api/v1/books/{result['book_id']}").json()['data']
        self.assertEqual(book['title'], 'Manh phái sơ cấp')
        version = c.get(f"/api/v1/book-versions/{result['version_id']}").json()['data']
        self.assertEqual((version['version_no'], version['rights_status'], version['mime']),
                         (1, 'private_reference', 'application/pdf'))
        reader = self.client('reader')
        self.assertEqual(reader.get(f"/api/v1/books/{result['book_id']}").status_code, 404)
        stored = owner('SELECT object_key FROM objects WHERE sha256 = %s', sha_bytes(data))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, stored[0][0])))

    def test_duplicate_bytes_reuse_object_and_version(self):
        c = self.client()
        batch = self.batch(c)
        data = pdf_bytes()
        first = self.upload(c, batch, data).json()['data']
        second = self.upload(c, batch, data, name='copy.pdf')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()['data']['duplicate_of'], first['version_id'])
        self.assertEqual(owner('SELECT count(*) FROM objects WHERE sha256 = %s',
                               sha_bytes(data))[0][0], 1)
        counters = c.get(f'/api/v1/ingestion-batches/{batch}').json()['data']['counters']
        self.assertEqual(counters, {'accepted': 1, 'duplicate': 1, 'rejected': 0})

    def test_concurrent_identical_uploads_create_one_object(self):
        clients = [self.client(), self.client()]
        batch = self.batch(clients[0])
        data = pdf_bytes()
        barrier = threading.Barrier(2)

        def send(c):
            barrier.wait()
            return self.upload(c, batch, data)
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(send, clients))
        self.assertEqual(sorted(r.status_code for r in results), [200, 201])
        digest = sha_bytes(data)
        self.assertEqual(owner('SELECT count(*) FROM objects WHERE sha256 = %s', digest)[0][0], 1)
        self.assertEqual(owner('SELECT count(*) FROM book_versions v JOIN objects o'
                               ' ON o.id = v.object_id WHERE o.sha256 = %s', digest)[0][0], 1)

    def test_bad_file_rejected_without_failing_batch(self):
        c = self.client()
        batch = self.batch(c)
        cases = [(b'plain text, not a book', 'notes.txt', 'UNSUPPORTED_TYPE'),
                 (docx_bytes(), 'disguised.pdf', 'UNSUPPORTED_TYPE'),
                 (docx_bytes({'word/vbaProject.bin': 'x'}), 'macro.docx', 'DOCX_ACTIVE_CONTENT'),
                 (docx_bytes({'word/_rels/document.xml.rels':
                              '<Relationships><Relationship Id="r1" Type="x/relationships/image"'
                              ' Target="http://evil.example/a.png" TargetMode="External"/>'
                              '</Relationships>'}), 'remote.docx', 'DOCX_EXTERNAL_RELATIONSHIP'),
                 (b'PK\x03\x04broken zip', 'broken.docx', 'DOCX_INVALID')]
        for data, name, code in cases:
            with self.subTest(name=name):
                response = self.upload(c, batch, data, name=name)
                self.assertEqual((response.status_code, response.json()['code']), (415, code))
        good = self.upload(c, batch, docx_bytes({'word/_rels/document.xml.rels':
                           '<Relationships><Relationship Id="h" Type="x/relationships/hyperlink"'
                           ' Target="https://example.org" TargetMode="External"/></Relationships>'}),
                           name='Tên Sách.docx')
        self.assertEqual(good.status_code, 201, good.text)
        view = c.get(f'/api/v1/ingestion-batches/{batch}').json()['data']
        self.assertEqual(view['counters'], {'accepted': 1, 'duplicate': 0, 'rejected': 5})
        self.assertEqual({i['display_name'] for i in view['items'] if i['outcome'] == 'rejected'},
                         {'notes.txt', 'disguised.pdf', 'macro.docx', 'remote.docx', 'broken.docx'})

    def test_size_limit_rejects_and_leaves_nothing(self):
        app = self.make_app(max_upload_bytes=64)
        c = self.client(app=app)
        batch = self.batch(c)
        response = self.upload(c, batch, pdf_bytes() + b'x' * 200)
        self.assertEqual((response.status_code, response.json()['code']), (413, 'FILE_TOO_LARGE'))
        objects_dir = os.path.join(self.tmp.name, 'objects')
        self.assertFalse(os.path.isdir(objects_dir) and os.listdir(objects_dir))
        self.assertEqual(os.listdir(os.path.join(self.tmp.name, 'staging')), [])

    def test_idempotent_retry_replays_and_detects_changes(self):
        c = self.client()
        batch = self.batch(c)
        data = pdf_bytes()
        first = self.upload(c, batch, data, key='file-1')
        again = self.upload(c, batch, data, key='file-1')
        self.assertEqual((again.status_code, again.json()), (201, first.json()))
        self.assertEqual(len(c.get(f'/api/v1/ingestion-batches/{batch}').json()['data']['items']), 1)
        changed = self.upload(c, batch, pdf_bytes(), key='file-1')
        self.assertEqual((changed.status_code, changed.json()['code']),
                         (409, 'IDEMPOTENCY_MISMATCH'))

    def test_batch_with_profile_queues_job_and_outbox(self):
        c = self.client()
        batch = self.batch(c, pipeline_profile())
        result = self.upload(c, batch, pdf_bytes()).json()['data']
        job = owner('SELECT j.state, g.state, j.book_version_id FROM ingestion_jobs j'
                    ' JOIN generations g ON g.id = j.generation_id WHERE j.id = %s',
                    result['job_id'])[0]
        self.assertEqual((job[0], job[1], str(job[2])), ('queued', 'building', result['version_id']))
        events = owner("SELECT payload->>'job_id' FROM outbox_events"
                       " WHERE topic = 'ingestion.job.queued'")
        self.assertIn((result['job_id'],), events)
        self.assertEqual(c.get(f'/api/v1/ingestion-batches/{batch}').json()['data']['state'],
                         'running')

    def test_new_version_of_existing_book(self):
        c = self.client()
        batch = self.batch(c)
        first = self.upload(c, batch, pdf_bytes()).json()['data']
        second = self.upload(c, batch, pdf_bytes(), book_id=first['book_id'],
                             edition_label='bản sửa 2').json()['data']
        versions = c.get(f"/api/v1/books/{first['book_id']}/versions").json()['data']
        self.assertEqual([(v['version_no'], v['edition_label']) for v in versions],
                         [(1, 'v1'), (2, 'bản sửa 2')])
        self.assertEqual(second['book_id'], first['book_id'])

    def test_readers_cannot_upload_or_create_batches(self):
        reader = self.client('reader')
        self.assertEqual(reader.post('/api/v1/ingestion-batches', json={'name': 'x'}).status_code,
                         403)
        reviewer = self.client()
        batch = self.batch(reviewer)
        self.assertEqual(self.upload(reader, batch, pdf_bytes()).status_code, 403)


class CatalogTests(UploadTestCase):
    def test_book_crud_with_if_match_and_authors(self):
        c = self.client()
        created = c.post('/api/v1/books', json={
            'title': 'Tử Bình Chân Thuyên bình chú', 'authors': [
                {'name': 'Thẩm Hiếu Chiêm', 'role': 'author'},
                {'name': 'Từ Nhạc Ngô', 'role': 'commentator'}]})
        self.assertEqual((created.status_code, created.headers['etag']), (201, '"1"'))
        book = created.json()['data']
        self.assertEqual([(a['name'], a['role']) for a in book['authors']],
                         [('Thẩm Hiếu Chiêm', 'author'), ('Từ Nhạc Ngô', 'commentator')])
        path = f"/api/v1/books/{book['id']}"
        self.assertEqual(c.patch(path, json={'description': 'x'}).status_code, 428)
        ok = c.patch(path, json={'description': 'Nguyên văn + bình chú'}, headers={'If-Match': '"1"'})
        self.assertEqual((ok.status_code, ok.json()['data']['revision']), (200, 2))
        stale = c.patch(path, json={'title': 'x'}, headers={'If-Match': '"1"'})
        self.assertEqual(stale.status_code, 412)
        found = c.get('/api/v1/books', params={'q': 'tu binh chan'}).json()['data']
        self.assertIn(book['id'], [b['id'] for b in found])

    def test_reader_sees_book_after_grant(self):
        reviewer, admin, reader = self.client(), self.client('admin'), self.client('reader')
        book = reviewer.post('/api/v1/books', json={'title': 'Trích Thiên Tủy'}).json()['data']
        path = f"/api/v1/books/{book['id']}"
        self.assertEqual(reader.get(path).status_code, 404)
        self.assertEqual(reviewer.patch(f'{path}/access', json={'grants': []},
                                        headers={'If-Match': '"1"'}).status_code, 403)
        grants = admin.get(f'{path}/access').json()['data']
        grants.append({'role_scope': 'reader', 'permission': 'read'})
        response = admin.patch(f'{path}/access', json={'grants': grants}, headers={'If-Match': '"1"'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(reader.get(path).status_code, 200)
        audit = owner("SELECT count(*) FROM audit_logs WHERE action = 'book.access.replace'"
                      ' AND target_id = %s', book['id'])
        self.assertEqual(audit[0][0], 1)
        bad = admin.patch(f'{path}/access', json={'grants': [{'permission': 'read'}]},
                          headers={'If-Match': '"2"'})
        self.assertEqual(bad.status_code, 422)

    def test_cursor_pagination(self):
        c = self.client()
        for i in range(3):
            c.post('/api/v1/books', json={'title': f'Phân trang {uuid.uuid4().hex[:6]} {i}'})
        seen, cursor = [], None
        while True:
            params = {'limit': 2, 'q': 'phan trang'} | ({'cursor': cursor} if cursor else {})
            page = c.get('/api/v1/books', params=params).json()
            seen += [b['id'] for b in page['data']]
            cursor = page['page']['next_cursor']
            if not page['page']['has_more']:
                break
        self.assertEqual(len(seen), len(set(seen)))
        self.assertGreaterEqual(len(seen), 3)


def sha_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


if __name__ == '__main__':
    unittest.main()
