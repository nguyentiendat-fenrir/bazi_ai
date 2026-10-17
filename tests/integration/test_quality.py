"""Structure and quality stages end to end on PostgreSQL (T014)."""
from pathlib import Path
import tempfile
import time
import unittest
import uuid

import psycopg

from backend.app.ingestion.pipeline import handlers_for
from backend.app.ingestion.structure import BlockRef, build_sections
from backend.app.ingestion.worker import run_job
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path
from tests.integration.db import (ADMIN_URL, ROOT, create_runtime_login, database_url,
                                  drop_database, drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

TU_BINH = ROOT / 'inputs' / 'books' / 'Tử Bình Chân Thuyên bình chú.pdf'
BLACK, BLUE = (0, 0, 0), (0, 0, 205)


class BuildSectionsTests(unittest.TestCase):
    def ref(self, i, kind='paragraph', level=None, role=None, page=1):
        return BlockRef(f'b{i}', page, 'pdf_page', i, kind, role, level, f'text {i}')

    def test_tree_paths_and_assignment(self):
        blocks = [self.ref(0), self.ref(1, role='folio'), self.ref(2, 'heading', 1),
                  self.ref(3), self.ref(4, 'heading', 2), self.ref(5), self.ref(6, 'heading', 2),
                  self.ref(7, 'heading', 1), self.ref(8)]
        sections, assignment = build_sections(blocks)
        self.assertEqual([(s.path, s.parent_path) for s in sections],
                         [('0000', None), ('0001', None), ('0001.0001', '0001'),
                          ('0001.0002', '0001'), ('0002', None)])
        self.assertEqual(assignment['b0'], '0000')
        self.assertNotIn('b1', assignment)                  # folio belongs to no section
        self.assertEqual((assignment['b5'], assignment['b8']), ('0001.0001', '0002'))


class PipelineQualityTests(unittest.TestCase):
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

    def run_pipeline(self, pdf: Path):
        with self.engine.begin() as conn, open(pdf, 'rb') as source:
            obj = store_object(conn, self.store, source, 'application/pdf')
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            user = f.user()
            book = f.one("INSERT INTO books (title, normalized_title, language, created_by)"
                         " VALUES ('q', 'q', 'vi', %s) RETURNING id", user)
            version = f.one("INSERT INTO book_versions (book_id, object_id, edition_label,"
                            " version_no, rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1,"
                            " 'private_reference', %s) RETURNING id", book, obj['id'], user)
            profile = f.one("INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                            " normalizer_version, embedding_profile_id, config_hash) VALUES ('p',"
                            " 'x', '1', '1', %s, %s) RETURNING id", f.embedding_profile(),
                            sha(uuid.uuid4().hex))
            gen = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                        ' VALUES (%s, %s) RETURNING id', version, profile)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, gen, profile, user)
        started = time.time()
        state = run_job(self.engine, self.store, job, handlers_for(None), 'w1')
        return state, gen, time.time() - started

    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db)) as conn:
            return conn.execute(query, params).fetchall()

    def synthetic(self) -> Path:
        builder = PdfBuilder()
        labels = [5, 6, 7, 99, 9]   # printed folio = physical + 4, page 4 is wrong
        bodies = [
            [('CHƯƠNG 1: KHÁCH CHỦ', 72, 720, 18, BLACK),
             ('Khách và Chủ được xét theo nhiều cấp độ khác nhau trong lá số.', 72, 690, 11, BLACK),
             ('1. Khái niệm khách chủ', 72, 650, 11, BLACK),
             ('Chủ là bản thân, khách là người khác hoặc sự việc bên ngoài.', 72, 620, 11, BLACK)],
            [('Nguyên văn: Bát tự dụng thần chuyên cầu nguyệt lệnh.', 72, 720, 11, BLUE),
             ('lấy nhật can phối với nguyệt lệnh mà xét.', 72, 706, 11, BLUE),
             ('Từ chú: Dụng thần ở đây khác với dụng của Manh phái.', 72, 650, 11, BLACK)],
            [('Mậu Kỷ Bính Canh', 72, 720, 11, BLACK), ('Ngọ Mùi Dần', 72, 706, 11, BLACK),
             ('Đoạn văn sau bảng trụ thiếu một chi.', 72, 650, 11, BLACK)],
            [('2. Khái niệm thể dụng', 72, 720, 11, BLACK),
             ('Thể là cái mình có, dụng là cái mình dùng.', 72, 690, 11, BLACK)],
            [('Đoạn kết của chương với nội dung thường.', 72, 720, 11, BLACK)],
        ]
        for label, lines in zip(labels, bodies):
            builder.page(lines=lines + [(str(label), 300, 30, 10, BLACK)])
        return builder.save(self.tmp / 'synthetic.pdf')

    def test_sections_labels_quality_and_speakers(self):
        if font_path() is None:
            self.skipTest('no TrueType font for the text fixture')
        state, gen, _ = self.run_pipeline(self.synthetic())
        self.assertEqual(state, 'succeeded')
        sections = self.sql('SELECT path, title FROM sections WHERE generation_id = %s'
                            ' ORDER BY path', gen)
        self.assertEqual([p for p, _ in sections], ['0001', '0001.0001', '0001.0002'])
        self.assertEqual(sections[0][1].replace('\xa0', ' '), 'CHƯƠNG 1: KHÁCH CHỦ')
        labels = self.sql('SELECT p.physical_page_number, r.printed_page_label,'
                          ' r.printed_label_verified FROM generation_pages gp JOIN pages p'
                          ' ON p.id = gp.page_id JOIN page_revisions r ON r.id = gp.page_revision_id'
                          ' WHERE gp.generation_id = %s ORDER BY 1', gen)
        self.assertEqual([v for _, _, v in labels], [True, True, True, False, True])
        reasons = {(r[0], r[1]) for r in self.sql(
            'SELECT ri.reason_code, p.physical_page_number FROM review_items ri'
            ' LEFT JOIN page_revisions r ON r.id = ri.page_revision_id'
            ' LEFT JOIN pages p ON p.id = r.page_id WHERE ri.generation_id = %s', gen)}
        self.assertIn(('PRINTED_LABEL_MISMATCH', 4), reasons)
        self.assertIn(('PILLAR_ROW_MISMATCH', 3), reasons)
        self.assertIn(('SPEAKER_LAYERS_INCOMPLETE', None), reasons)
        speakers = self.sql("SELECT b.speaker_layer, b.attributes->>'marker', b.text FROM blocks b"
                            ' JOIN generation_pages gp ON gp.page_revision_id = b.page_revision_id'
                            ' JOIN pages p ON p.id = gp.page_id WHERE gp.generation_id = %s'
                            ' AND p.physical_page_number = 2 ORDER BY b.ordinal', gen)
        self.assertEqual([(s, m) for s, m, _ in speakers[:2]],
                         [('original_author', 'nguyên văn'), ('commentator', 'từ chú')])
        roles = self.sql("SELECT DISTINCT b.attributes->>'role' FROM blocks b JOIN generation_pages gp"
                         ' ON gp.page_revision_id = b.page_revision_id WHERE gp.generation_id = %s'
                         " AND b.text ~ '^[0-9]+$'", gen)
        self.assertEqual(roles, [('folio',)])

    @unittest.skipUnless(TU_BINH.is_file(), 'original book not present')
    def test_real_book_structure(self):
        state, gen, elapsed = self.run_pipeline(TU_BINH)
        self.assertEqual(state, 'succeeded')
        titles = [t for (t,) in self.sql('SELECT title FROM sections WHERE generation_id = %s', gen)]
        self.assertIn('Chương 8: Luận dụng thần', titles)          # docs/02 audit: p26
        coverage = self.sql('SELECT coverage FROM generations WHERE id = %s', gen)[0][0]
        self.assertGreaterEqual(coverage['printed_labels_verified'], 130)
        self.assertEqual(coverage['printed_label_offset'], 0)       # printed = physical
        self.assertIn('SPEAKER_LAYERS_INCOMPLETE', coverage['quality'])
        speakers = dict(self.sql('SELECT b.speaker_layer, count(*) FROM blocks b JOIN'
                                 ' generation_pages gp ON gp.page_revision_id = b.page_revision_id'
                                 ' WHERE gp.generation_id = %s GROUP BY 1', gen))
        self.assertGreater(speakers.get('original_author', 0), 100)
        self.assertGreater(speakers.get('commentator', 0), 100)
        print(f'\nTử Bình full pipeline: {elapsed:.1f}s, {len(titles)} sections, {speakers}')


if __name__ == '__main__':
    unittest.main()
