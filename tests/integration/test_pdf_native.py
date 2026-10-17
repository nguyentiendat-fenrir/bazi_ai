"""Native PDF extraction (T011): synthetic fixtures, the real audit books, and the pipeline.

Real-book checks need the original PDFs in inputs/books (kept outside Git) and
skip without them; the pipeline part needs BAZI_TEST_DATABASE_URL.
"""
import io
from pathlib import Path
import tempfile
import unittest
import uuid

import psycopg

from backend.app.ingestion.pdf_native import PdfRejected, extract_page, open_document
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.worker import run_job
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path
from tests.integration.db import (ADMIN_URL, ROOT, create_runtime_login, database_url,
                                  drop_database, drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

BOOKS = ROOT / 'inputs' / 'books'
AUDITED = {  # docs/02: the three audited PDFs, 613 pages together
    'Manh phái sơ cấp lý pháp Facebook ánh dương .pdf': 292,
    'Manh phái cao cấp - Đoàn kiến Nghiệp - tài liệu giảng dạy facebook sách ánh dương .pdf': 181,
    'Tử Bình Chân Thuyên bình chú.pdf': 140,
}


def build(tmp, **pages):
    builder = PdfBuilder()
    for spec in pages.get('pages', []):
        builder.page(**spec)
    return str(builder.save(Path(tmp) / f'{uuid.uuid4().hex}.pdf'))


class SyntheticPdfTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def text_line(self, text, y, color=(0, 0, 0), size=12):
        return (text, 72, y, size, color)

    def test_vietnamese_text_blocks_and_colour_layers(self):
        if font_path() is None:
            self.skipTest('no TrueType font with Vietnamese coverage on this machine')
        path = build(self.tmp.name, pages=[{'lines': [
            self.text_line('Khách Chủ luận theo can ngày', 700),
            self.text_line('dòng tiếp theo của cùng đoạn', 686),
            self.text_line('Lời bình chú in màu xanh', 600, color=(0, 0, 205))]}])
        page = extract_page(open_document(path), 0)
        texts = [b.text.replace('\xa0', ' ') for b in page.blocks]
        self.assertEqual(texts, ['Khách Chủ luận theo can ngày\ndòng tiếp theo của cùng đoạn',
                                 'Lời bình chú in màu xanh'])
        self.assertEqual([b.attributes['color'] for b in page.blocks], ['#000000', '#0000cd'])
        for block in page.blocks:
            self.assertEqual(page.normalized_text[block.start:block.end], block.text)
            x0, y0, x1, y1 = block.bbox
            self.assertTrue(0 <= x0 <= x1 <= 1 and 0 <= y0 <= y1 <= 1)
        self.assertLess(page.blocks[0].bbox[1], page.blocks[1].bbox[1])  # top-left origin

    def test_blank_and_scan_pages_are_classified_not_failed(self):
        path = build(self.tmp.name, pages=[{}, {'image': (0, 0, 612, 792)}])
        doc = open_document(path)
        blank, scan = extract_page(doc, 0), extract_page(doc, 1)
        self.assertEqual((blank.page_class, blank.quality_state, blank.blocks), ('blank', 'accepted', []))
        self.assertEqual((scan.page_class, scan.needs_ocr, scan.quality_state),
                         ('scan', True, 'review_required'))
        self.assertEqual(len(scan.image_boxes), 1)

    def test_rotation_normalises_boxes(self):
        if font_path() is None:
            self.skipTest('no TrueType font with Vietnamese coverage on this machine')
        path = build(self.tmp.name, pages=[{'rotation': r, 'lines': [self.text_line('Góc', 700)]}
                                           for r in (0, 90, 180, 270)])
        doc = open_document(path)
        corners = []
        for i in range(4):
            x0, y0, x1, y1 = extract_page(doc, i).blocks[0].bbox
            corners.append(('left' if x1 < 0.5 else 'right', 'top' if y1 < 0.5 else 'bottom'))
        self.assertEqual(corners, [('left', 'top'), ('right', 'top'), ('right', 'bottom'),
                                   ('left', 'bottom')])

    def test_encrypted_and_corrupt_pdfs_are_rejected_with_codes(self):
        from pypdf import PdfReader, PdfWriter
        plain = build(self.tmp.name, pages=[{}])
        writer = PdfWriter(clone_from=PdfReader(plain))
        writer.encrypt('secret-password')
        locked = Path(self.tmp.name) / 'locked.pdf'
        writer.write(locked)
        corrupt = Path(self.tmp.name) / 'corrupt.pdf'
        corrupt.write_bytes(b'%PDF-1.7\nthis is not a PDF body')
        for path, code in ((locked, 'PASSWORD_REQUIRED'), (corrupt, 'PDF_CORRUPT')):
            with self.subTest(code=code):
                with self.assertRaises(PdfRejected) as caught:
                    open_document(str(path))
                self.assertEqual(caught.exception.code, code)


@unittest.skipUnless(all((BOOKS / n).is_file() for n in AUDITED), 'original books not present')
class AuditedBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = {name: open_document(str(BOOKS / name)) for name in AUDITED}

    @classmethod
    def tearDownClass(cls):
        for doc in cls.docs.values():
            doc.close()

    def test_page_counts_total_613(self):
        counts = {name: len(doc) for name, doc in self.docs.items()}
        self.assertEqual(counts, AUDITED)
        self.assertEqual(sum(counts.values()), 613)

    def test_unicode_preserved_and_no_replacement_characters(self):
        so_cap = self.docs['Manh phái sơ cấp lý pháp Facebook ánh dương .pdf']
        page6 = extract_page(so_cap, 5).normalized_text
        self.assertIn('tinh thần', page6)    # pypdf split this as "tinh th ần"
        self.assertIn('có thể', page6)
        tu_binh = self.docs['Tử Bình Chân Thuyên bình chú.pdf']
        text = ' '.join(extract_page(tu_binh, i).normalized_text for i in range(0, 6))
        self.assertIn('Thẩm Hiếu Chiêm', text)
        for name, doc in self.docs.items():
            with self.subTest(book=name):
                self.assertEqual(sum(extract_page(doc, i).replacement_chars
                                     for i in range(len(doc))), 0)

    def test_audit_observations(self):
        cao_cap = self.docs['Manh phái cao cấp - Đoàn kiến Nghiệp - tài liệu giảng dạy facebook'
                            ' sách ánh dương .pdf']
        self.assertEqual(extract_page(cao_cap, 4).page_class, 'sparse')   # p5 near-empty, not an error
        self.assertEqual(extract_page(cao_cap, 29).page_class, 'mixed')   # p30 star chart image
        tu_binh = self.docs['Tử Bình Chân Thuyên bình chú.pdf']
        self.assertTrue(extract_page(tu_binh, 76).image_boxes)            # p77 figure kept as region
        page28 = extract_page(tu_binh, 27)
        self.assertEqual(page28.printed_label, '28')
        self.assertGreaterEqual(len({b.attributes['color'] for b in page28.blocks}), 2)


class PipelineTests(unittest.TestCase):
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
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = LocalObjectStore(Path(self.tmp.name) / 'store')

    def queue_job(self, pdf_path):
        with self.engine.begin() as conn, open(pdf_path, 'rb') as source:
            obj = store_object(conn, self.store, source, 'application/pdf')
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            user = f.user()
            book = f.one("INSERT INTO books (title, normalized_title, language, created_by)"
                         " VALUES ('t', 't', 'vi', %s) RETURNING id", user)
            version = f.one("INSERT INTO book_versions (book_id, object_id, edition_label,"
                            " version_no, rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1,"
                            " 'private_reference', %s) RETURNING id", book, obj['id'], user)
            profile = f.one("INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                            " normalizer_version, embedding_profile_id, config_hash)"
                            " VALUES ('p', 'pdfium', '1', '1', %s, %s) RETURNING id",
                            f.embedding_profile(), sha(uuid.uuid4().hex))
        self.version, self.profile, self.user = version, profile, user
        return version, [self.new_job()]

    def new_job(self):
        """Only one active job per version/profile exists at a time (M007 index)."""
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

    def test_job_extracts_pages_blocks_and_reuses_revisions(self):
        pages = [{}, {'image': (0, 0, 612, 792)}]
        if font_path():
            pages.insert(0, {'lines': [('Khách Chủ', 72, 700, 12, (0, 0, 0))]})
        path = build(self.tmp.name, pages=pages)
        version, jobs = self.queue_job(path)
        stages = [ValidatePdfStage(), ExtractPdfStage()]
        first_job, first_gen = jobs[0]
        self.assertEqual(run_job(self.engine, self.store, first_job, stages, 'w1'), 'succeeded')
        n = len(pages)
        counters = self.sql('SELECT counters FROM ingestion_jobs WHERE id = %s', first_job)[0][0]
        self.assertEqual((counters['pages_total'], counters['pages_processed'],
                          counters['pages_needing_ocr']), (n, n, 1))
        classes = [r[0] for r in self.sql(
            "SELECT r.quality->>'page_class' FROM generation_pages gp JOIN page_revisions r"
            ' ON r.id = gp.page_revision_id JOIN pages p ON p.id = gp.page_id'
            ' WHERE gp.generation_id = %s ORDER BY p.physical_page_number', first_gen)]
        self.assertEqual(classes[-2:], ['blank', 'scan'])
        if font_path():
            block = self.sql('SELECT b.text, b.start_offset, b.end_offset, r.normalized_text'
                             ' FROM blocks b JOIN page_revisions r ON r.id = b.page_revision_id'
                             ' JOIN pages p ON p.id = r.page_id WHERE p.book_version_id = %s'
                             ' AND p.physical_page_number = 1', version)[0]
            self.assertEqual(block[3][block[1]:block[2]], block[0])
        # A second generation with the same parser reuses every revision: no duplicates.
        second_job, second_gen = self.new_job()
        self.assertEqual(run_job(self.engine, self.store, second_job, stages, 'w1'), 'succeeded')
        revisions = self.sql('SELECT count(*) FROM page_revisions r JOIN pages p ON p.id = r.page_id'
                             ' WHERE p.book_version_id = %s', version)[0][0]
        selected = self.sql('SELECT count(DISTINCT page_revision_id) FROM generation_pages'
                            ' WHERE generation_id = ANY(%s)', [first_gen, second_gen])[0][0]
        self.assertEqual((revisions, selected), (n, n))

    def test_encrypted_source_fails_job_with_code(self):
        from pypdf import PdfReader, PdfWriter
        writer = PdfWriter(clone_from=PdfReader(build(self.tmp.name, pages=[{}])))
        writer.encrypt('secret-password')
        locked = Path(self.tmp.name) / 'locked.pdf'
        writer.write(locked)
        _, jobs = self.queue_job(locked)
        job = jobs[0][0]
        self.assertEqual(run_job(self.engine, self.store, job,
                                 [ValidatePdfStage(), ExtractPdfStage()], 'w1'), 'failed')
        error = self.sql('SELECT error FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual((error['code'], error['retryable']), ('PASSWORD_REQUIRED', False))


if __name__ == '__main__':
    unittest.main()
