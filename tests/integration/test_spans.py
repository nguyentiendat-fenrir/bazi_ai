"""Chunk provenance on PostgreSQL (T015): every chunk character maps to page/block text."""
from pathlib import Path
import tempfile
import time
import unittest
import uuid

import psycopg

from backend.app.ingestion.chunker import SEPARATOR
from backend.app.ingestion.pipeline import handlers_for
from backend.app.ingestion.worker import run_job
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path
from tests.integration.db import (ADMIN_URL, ROOT, create_runtime_login, database_url,
                                  drop_database, drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

BOOKS = ROOT / 'inputs' / 'books'
REAL = [BOOKS / 'Tử Bình Chân Thuyên bình chú.pdf',
        BOOKS / 'Manh phái sơ cấp lý pháp Facebook ánh dương .pdf']
BLACK = (0, 0, 0)


class SpanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ADMIN_URL:
            raise unittest.SkipTest('BAZI_TEST_DATABASE_URL is not set')
        cls.db = migrated_database('head')
        cls.role, cls.runtime = create_runtime_login(cls.db)
        cls.engine = engine_for(cls.runtime)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        drop_database(cls.db)
        drop_role(cls.role)

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = LocalObjectStore(self.tmp / 'store')

    def queue(self, pdf: Path):
        with self.engine.begin() as conn, open(pdf, 'rb') as source:
            obj = store_object(conn, self.store, source, 'application/pdf')
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            user = f.user()
            book = f.one("INSERT INTO books (title, normalized_title, language, created_by)"
                         " VALUES ('s', 's', 'vi', %s) RETURNING id", user)
            version = f.one("INSERT INTO book_versions (book_id, object_id, edition_label,"
                            " version_no, rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1,"
                            " 'private_reference', %s) RETURNING id", book, obj['id'], user)
            profile = f.one("INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                            " normalizer_version, embedding_profile_id, config_hash) VALUES ('p',"
                            " 'x', '1', '1', %s, %s) RETURNING id", f.embedding_profile(),
                            sha(uuid.uuid4().hex))
        self.version, self.profile, self.user = version, profile, user
        return self.job()

    def job(self):
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            gen = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                        ' VALUES (%s, %s) RETURNING id', self.version, self.profile)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        self.version, gen, self.profile, self.user)
        return job, gen

    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db)) as conn:
            return conn.execute(query, params).fetchall()

    def assert_provenance(self, gen):
        """Span text equals source text; chunk text is exactly its spans joined."""
        bad = self.sql(
            'SELECT count(*) FROM generation_chunks gc JOIN chunks c ON c.id = gc.chunk_id'
            ' JOIN chunk_spans s ON s.chunk_id = c.id JOIN page_revisions r'
            ' ON r.id = s.page_revision_id WHERE gc.generation_id = %s'
            ' AND substr(c.text, s.chunk_start + 1, s.chunk_end - s.chunk_start)'
            ' <> substr(r.normalized_text, s.start_offset + 1, s.end_offset - s.start_offset)', gen)
        self.assertEqual(bad[0][0], 0)
        rows = self.sql('SELECT c.text, array_agg(substr(c.text, s.chunk_start + 1,'
                        ' s.chunk_end - s.chunk_start) ORDER BY s.ordinal) FROM generation_chunks gc'
                        ' JOIN chunks c ON c.id = gc.chunk_id JOIN chunk_spans s ON s.chunk_id = c.id'
                        ' WHERE gc.generation_id = %s GROUP BY c.id, c.text', gen)
        self.assertTrue(rows)
        for text_, pieces in rows:
            self.assertEqual(text_, SEPARATOR.join(pieces))

    def test_cross_page_paragraph_and_speakers(self):
        if font_path() is None:
            self.skipTest('no TrueType font for the text fixture')
        builder = PdfBuilder()
        builder.page(lines=[('CHƯƠNG 1: THỂ DỤNG', 72, 720, 18, BLACK),
                            ('Nguyên văn: Thể là cái mình có, dụng là cái mình dùng', 72, 690, 11,
                             BLACK),
                            ('để đạt mục đích của mệnh cục.', 72, 676, 11, BLACK)])
        builder.page(lines=[('Từ chú: Dụng ở đây khác dụng thần của Tử Bình.', 72, 720, 11, BLACK),
                            ('Đoạn này nằm ở trang hai và tiếp tục lời chú.', 72, 706, 11, BLACK)])
        builder.page(lines=[('Đoạn văn thường ở trang ba thuộc cùng chương.', 72, 720, 11, BLACK)])
        builder.page(lines=[('Đoạn văn thường ở trang bốn, tiếp nối trang ba.', 72, 720, 11, BLACK)])
        job, gen = self.queue(builder.save(self.tmp / 'x.pdf'))
        self.assertEqual(run_job(self.engine, self.store, job, handlers_for(None), 'w'), 'succeeded')
        self.assert_provenance(gen)
        chunks = self.sql(
            'SELECT c.speaker_layer, count(DISTINCT s.page_revision_id), c.text FROM generation_chunks'
            ' gc JOIN chunks c ON c.id = gc.chunk_id JOIN chunk_spans s ON s.chunk_id = c.id'
            ' WHERE gc.generation_id = %s GROUP BY c.id, gc.ordinal ORDER BY gc.ordinal', gen)
        speakers = [s for s, _, _ in chunks]
        self.assertEqual(speakers[:2], ['original_author', 'commentator'])
        self.assertIn(2, [pages for _, pages, _ in chunks])        # pages 3+4 in one chunk
        mixed = self.sql('SELECT count(*) FROM generation_chunks gc JOIN chunk_spans s'
                         ' ON s.chunk_id = gc.chunk_id JOIN blocks b ON b.id = s.block_id'
                         ' JOIN chunks c ON c.id = gc.chunk_id WHERE gc.generation_id = %s'
                         ' AND b.speaker_layer <> c.speaker_layer', gen)
        self.assertEqual(mixed[0][0], 0)
        sections = self.sql('SELECT DISTINCT s.title FROM generation_chunks gc JOIN sections s'
                            ' ON s.id = gc.section_id WHERE gc.generation_id = %s', gen)
        self.assertEqual([t.replace('\xa0', ' ') for (t,) in sections], ['CHƯƠNG 1: THỂ DỤNG'])

    @unittest.skipUnless(all(p.is_file() for p in REAL), 'original books not present')
    def test_real_books_provenance_and_stable_identity(self):
        for pdf in REAL:
            with self.subTest(book=pdf.name):
                job, gen = self.queue(pdf)
                started = time.time()
                self.assertEqual(run_job(self.engine, self.store, job, handlers_for(None), 'w'),
                                 'succeeded')
                elapsed = time.time() - started
                self.assert_provenance(gen)
                stats = self.sql(
                    'SELECT count(*), max(c.token_count), count(*) FILTER (WHERE c.kind = %s),'
                    ' count(*) FILTER (WHERE c.kind = %s) FROM generation_chunks gc'
                    ' JOIN chunks c ON c.id = gc.chunk_id WHERE gc.generation_id = %s',
                    'table', 'case', gen)[0]
                self.assertGreater(stats[0], 100)
                topics = self.sql("SELECT count(*) FROM chunk_classifications WHERE generation_id = %s"
                                  " AND status = 'proposed'", gen)[0][0]
                print(f'\n{pdf.name[:30]}: {elapsed:.1f}s, chunks={stats[0]} max_tokens={stats[1]}'
                      f' table={stats[2]} case={stats[3]} proposed_topics={topics}')
                total_before = self.sql('SELECT count(*) FROM chunks')[0][0]
                job2, gen2 = self.job()
                self.assertEqual(run_job(self.engine, self.store, job2, handlers_for(None), 'w'),
                                 'succeeded')
                self.assertEqual(self.sql('SELECT count(*) FROM chunks')[0][0], total_before)
                self.assertEqual(self.sql('SELECT count(*) FROM generation_chunks'
                                          ' WHERE generation_id = %s', gen2)[0][0], stats[0])


if __name__ == '__main__':
    unittest.main()
