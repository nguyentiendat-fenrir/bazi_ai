"""OCR (T012): merge rules, stage behaviour with a fake engine, and real Tesseract.

Real-Tesseract tests run where the ``tesseract`` binary exists — the worker
image (infra/backend.Dockerfile ``test`` target); elsewhere they skip.
"""
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

import psycopg

from backend.app.ingestion.ocr import (OcrBlock, OcrTimeout, TesseractEngine, crop, group_blocks,
                                       new_ocr_blocks, ocr_page, render, OcrWord)
from backend.app.ingestion.ocr_stage import OcrStage
from backend.app.ingestion.pdf_native import extract_page, open_document
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.worker import run_job
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path, oversized_page, scanned_copy
from tests.integration.db import (ADMIN_URL, ROOT, create_runtime_login, database_url,
                                  drop_database, drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

HAS_TESSERACT = shutil.which('tesseract') is not None
CAO_CAP = ROOT / 'inputs' / 'books' / ('Manh phái cao cấp - Đoàn kiến Nghiệp - tài liệu giảng dạy'
                                        ' facebook sách ánh dương .pdf')


def text_pdf(tmp: Path, lines) -> Path:
    builder = PdfBuilder()
    builder.page(lines=[(t, 72, y, 20, (0, 0, 0)) for t, y in lines])
    return builder.save(tmp / f'{uuid.uuid4().hex}.pdf')


class MergeRuleTests(unittest.TestCase):
    def test_ocr_blocks_inside_native_text_are_dropped(self):
        native = [[0.1, 0.1, 0.9, 0.3]]
        ocr = [OcrBlock('duplicate of native', [0.12, 0.12, 0.8, 0.28], 90, 0),
               OcrBlock('figure caption', [0.2, 0.5, 0.6, 0.55], 85, 1),
               OcrBlock('   ', [0.2, 0.7, 0.6, 0.75], 85, 1)]
        self.assertEqual([b.text for b in new_ocr_blocks(ocr, native)], ['figure caption'])

    def test_words_grouped_into_paragraph_blocks_in_reading_order(self):
        words = [OcrWord('Chủ', [0.3, 0.1, 0.4, 0.12], 90, (0, 1, 1, 1)),
                 OcrWord('Khách', [0.1, 0.1, 0.25, 0.12], 80, (0, 1, 1, 1)),
                 OcrWord('lưu', [0.1, 0.13, 0.2, 0.15], 70, (0, 1, 1, 2)),
                 OcrWord('Hình', [0.1, 0.6, 0.2, 0.62], 60, (1, 1, 1, 1))]
        blocks = group_blocks(words)
        self.assertEqual([b.text for b in blocks], ['Chủ Khách\nlưu', 'Hình'])
        self.assertEqual(blocks[0].bbox, [0.1, 0.1, 0.4, 0.15])
        self.assertEqual(blocks[0].conf, 80.0)

    def test_crop_is_exact(self):
        w, h = 4, 2
        pixels = bytes(range(w * h * 3))
        ppm = b'P6 4 2 255\n' + pixels
        part, x0, y0, cw, ch = crop(ppm, w, h, [0.5, 0.5, 1.0, 1.0])
        self.assertEqual((x0, y0, cw, ch), (2, 1, 2, 1))
        self.assertEqual(part.split(b'\n', 1)[1], pixels[(1 * w + 2) * 3:(1 * w + 4) * 3])

    def test_pixel_bomb_never_renders_full_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = open_document(str(oversized_page(Path(tmp) / 'huge.pdf')))
            try:
                with self.assertRaises(OcrTimeout):
                    render(doc, 0, 300)  # even MIN_DPI exceeds the pixel budget
            finally:
                doc.close()


class FakeEngine:
    version = 'fake-ocr 1.0'

    def __init__(self, behaviour='text'):
        self.behaviour = behaviour
        self.calls = 0

    def words(self, image, langs):
        self.calls += 1
        if self.behaviour == 'timeout':
            raise OcrTimeout('fake timeout')
        if self.behaviour == 'empty':
            return []
        return [{'text': 'Thiên', 'left': '10', 'top': '10', 'width': '60', 'height': '20',
                 'conf': '91', 'block_num': '1', 'par_num': '1', 'line_num': '1'},
                {'text': 'can', 'left': '80', 'top': '10', 'width': '40', 'height': '20',
                 'conf': '89', 'block_num': '1', 'par_num': '1', 'line_num': '1'}]


class StageTests(unittest.TestCase):
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

    def job_for(self, pdf: Path):
        with self.engine.begin() as conn, open(pdf, 'rb') as source:
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
                            " normalizer_version, embedding_profile_id, config_hash) VALUES ('p',"
                            " 'x', '1', '1', %s, %s) RETURNING id", f.embedding_profile(),
                            sha(uuid.uuid4().hex))
            gen = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                        ' VALUES (%s, %s) RETURNING id', version, profile)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, gen, profile, user)
        return job, gen

    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db)) as conn:
            return conn.execute(query, params).fetchall()

    def linked(self, gen):
        return self.sql('SELECT r.id, r.revision_no, r.state, r.normalized_text, r.quality'
                        ' FROM generation_pages gp JOIN page_revisions r'
                        ' ON r.id = gp.page_revision_id WHERE gp.generation_id = %s', gen)[0]

    def run_with(self, pdf, engine):
        job, gen = self.job_for(pdf)
        stages = [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=lambda: engine)]
        state = run_job(self.engine, self.store, job, stages, 'w1')
        return state, job, gen

    def scan_pdf(self):
        builder = PdfBuilder()
        builder.page(image=(0, 0, 612, 792))
        return builder.save(Path(self.tmp.name) / 'scan.pdf')

    def test_scan_page_gets_merged_revision_with_source_boxes(self):
        engine = FakeEngine()
        state, job, gen = self.run_with(self.scan_pdf(), engine)
        self.assertEqual(state, 'succeeded')
        _, revision_no, rev_state, text_, quality = self.linked(gen)
        self.assertEqual((revision_no, text_, rev_state), (2, 'Thiên can', 'accepted'))
        self.assertEqual((quality['needs_ocr'], quality['ocr']['mode']), (False, 'page'))
        block = self.sql("SELECT bbox, attributes->>'origin', start_offset, end_offset FROM blocks"
                         ' WHERE page_revision_id = %s', self.linked(gen)[0])[0]
        self.assertEqual((block[1], block[2], block[3]), ('ocr', 0, len('Thiên can')))
        self.assertTrue(all(0 <= v <= 1 for v in block[0]))
        counters = self.sql('SELECT counters FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual(counters['pages_ocr_text'], 1)

    def test_timeout_keeps_native_and_opens_review(self):
        state, job, gen = self.run_with(self.scan_pdf(), FakeEngine('timeout'))
        self.assertEqual(state, 'succeeded')  # the job is not failed by one page
        revision_id, revision_no, rev_state, _, _ = self.linked(gen)
        self.assertEqual((revision_no, rev_state), (1, 'review_required'))
        reasons = self.sql('SELECT reason_code FROM review_items WHERE generation_id = %s', gen)
        self.assertEqual(reasons, [('OCR_TIMEOUT',)])

    def test_missing_engine_is_a_review_not_a_failure(self):
        job, gen = self.job_for(self.scan_pdf())

        def unavailable():
            from backend.app.ingestion.ocr import OcrUnavailable
            raise OcrUnavailable('no tesseract')
        stages = [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=unavailable)]
        self.assertEqual(run_job(self.engine, self.store, job, stages, 'w1'), 'succeeded')
        self.assertEqual(self.sql('SELECT reason_code FROM review_items WHERE generation_id = %s',
                                  gen), [('OCR_UNAVAILABLE',)])

    def test_native_text_is_never_overwritten(self):
        if font_path() is None:
            self.skipTest('no TrueType font for the text fixture')
        builder = PdfBuilder()
        builder.page(lines=[('Đoạn chữ native giữ nguyên', 72, 740, 12, (0, 0, 0))],
                     image=(100, 100, 400, 400))
        pdf = builder.save(Path(self.tmp.name) / 'mixed.pdf')
        state, _, gen = self.run_with(pdf, FakeEngine())
        self.assertEqual(state, 'succeeded')
        native = self.sql('SELECT r.normalized_text FROM page_revisions r JOIN generation_pages gp'
                          ' ON gp.page_id = r.page_id WHERE gp.generation_id = %s'
                          ' AND r.revision_no = 1', gen)[0][0]
        merged = self.linked(gen)[3]
        self.assertTrue(merged.startswith(native))   # native offsets unchanged
        self.assertIn('Thiên can', merged[len(native):])

    def test_rerun_does_not_ocr_again(self):
        engine = FakeEngine()
        pdf = self.scan_pdf()
        job, gen = self.job_for(pdf)
        stages = [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=lambda: engine)]
        run_job(self.engine, self.store, job, stages, 'w1')
        calls = engine.calls
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            version, profile, user = conn.execute(
                'SELECT book_version_id, pipeline_profile_id, requested_by FROM ingestion_jobs'
                ' WHERE id = %s', (job,)).fetchone()
            f = Factory(conn)
            gen2 = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                         ' VALUES (%s, %s) RETURNING id', version, profile)
            job2 = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                         ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                         version, gen2, profile, user)
        self.assertEqual(run_job(self.engine, self.store, job2, stages, 'w1'), 'succeeded')
        self.assertEqual(engine.calls, calls)                      # reused, not recomputed
        self.assertEqual(self.linked(gen2)[0], self.linked(gen)[0])  # same merged revision


@unittest.skipUnless(HAS_TESSERACT, 'tesseract binary not installed (run in the worker image)')
class TesseractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = TesseractEngine()

    def test_scanned_vietnamese_page_is_read(self):
        if font_path() is None:
            self.skipTest('no TrueType font for the text fixture')
        tmp = Path(self.tmp.name)
        source = text_pdf(tmp, [('Khách Chủ luận theo can ngày', 700),
                                ('Thể Dụng và Tố Công', 650)])
        scan = scanned_copy(source, tmp / 'scan.pdf')
        doc = open_document(str(scan))
        try:
            self.assertEqual(extract_page(doc, 0).page_class, 'scan')
            words, dpi = ocr_page(doc, 0, None, self.engine)
        finally:
            doc.close()
        text_ = ' '.join(w.text for w in words)
        for expected in ('Khách', 'Chủ', 'ngày', 'Dụng'):
            self.assertIn(expected, text_)
        self.assertTrue(all(0 <= v <= 1 for w in words for v in w.box))
        self.assertEqual(dpi, 300)

    def test_pixel_bomb_page_goes_to_review_not_crash(self):
        doc = open_document(str(oversized_page(Path(self.tmp.name) / 'bomb.pdf')))
        try:
            with self.assertRaises(OcrTimeout):
                ocr_page(doc, 0, None, self.engine)
        finally:
            doc.close()

    @unittest.skipUnless(CAO_CAP.is_file(), 'original book not mounted')
    def test_figure_region_on_real_page(self):
        doc = open_document(str(CAO_CAP))
        try:
            page = extract_page(doc, 29)                       # p30 star chart
            words, _ = ocr_page(doc, 29, page.image_boxes, self.engine)
        finally:
            doc.close()
        blocks = new_ocr_blocks(group_blocks(words), [b.bbox for b in page.blocks])
        for block in blocks:   # whatever OCR finds lies inside the figure, not over native text
            box = page.image_boxes[0]
            self.assertTrue(box[0] - 0.01 <= block.bbox[0] and block.bbox[2] <= box[2] + 0.01)


if __name__ == '__main__':
    unittest.main()
