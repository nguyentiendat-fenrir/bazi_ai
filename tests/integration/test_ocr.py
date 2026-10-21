"""OCR (SenOCR-Vi / PaddleOCR-VL): block mapping, stage behaviour with a fake engine, real model.

Real-model tests run where the model cache holds SenOCR-Vi and a GPU is present
(the worker image with the model_cache volume); elsewhere they are skipped,
which does not count as tested.
"""
from pathlib import Path
import os
import tempfile
import unittest
import uuid

import psycopg

from backend.app.ingestion.ocr import (OcrBlock, OcrTimeout, assign_speakers, new_ocr_blocks,
                                       ocr_page, render, table_rows, to_blocks)
from backend.app.ingestion.ocr_stage import OcrStage
from backend.app.ingestion.pdf_native import open_document
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.worker import run_job
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.pdf_factory import PdfBuilder, font_path, oversized_page
from tests.integration.db import (ADMIN_URL, ROOT, create_runtime_login, database_url,
                                  drop_database, drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

MODEL_DIR = Path(os.environ.get('OCR_MODEL_DIR', '/models/senocr-vi/current'))
HAS_MODEL = (MODEL_DIR / 'model.safetensors').exists()
SCANNED = ROOT / 'inputs' / 'books' / 'Vượng suy' / 'tử bình chân thuyên fb ánh dương .pdf'


class MappingTests(unittest.TestCase):
    def test_ocr_blocks_inside_native_text_are_dropped(self):
        native = [[0.1, 0.1, 0.9, 0.3]]
        ocr = [OcrBlock('duplicate of native', [0.12, 0.12, 0.8, 0.28], None, 0),
               OcrBlock('figure caption', [0.2, 0.5, 0.6, 0.55], None, 1),
               OcrBlock('   ', [0.2, 0.7, 0.6, 0.75], None, 1)]
        self.assertEqual([b.text for b in new_ocr_blocks(ocr, native)], ['figure caption'])

    def test_layout_labels_map_to_block_kinds_roles_and_boxes(self):
        items = [
            {'block_label': 'paragraph_title', 'block_content': 'Chương 8: Luận dụng thần',
             'block_bbox': [100, 50, 900, 100]},
            {'block_label': 'text', 'block_content': 'Bát tự dụng thần chuyên cầu nguyệt lệnh.',
             'block_bbox': [100, 120, 900, 300]},
            {'block_label': 'table', 'block_bbox': [100, 320, 600, 500], 'block_content':
             '<table><tr><td>Kiếp</td><td>T.Tài</td><td>Nhật chủ</td><td>Kiếp</td></tr>'
             '<tr><td>Quý</td><td>Bính</td><td>Nhâm</td><td>Quý</td></tr>'
             '<tr><td>Tị</td><td>Thìn</td><td>Thân</td><td>Mão</td></tr></table>'},
            {'block_label': 'number', 'block_content': '60', 'block_bbox': [480, 980, 520, 1000]},
            {'block_label': 'image', 'block_content': '', 'block_bbox': [0, 0, 10, 10]}]
        blocks = to_blocks(items, 1000, 1000)
        self.assertEqual([(b.kind, b.role) for b in blocks],
                         [('heading', None), ('paragraph', None), ('table', None),
                          ('paragraph', 'folio')])
        self.assertEqual(blocks[0].level, 1)                       # "Chương N" rule
        self.assertEqual(blocks[1].bbox, [0.1, 0.12, 0.9, 0.3])
        self.assertEqual(blocks[2].table_cells[1], ['Quý', 'Bính', 'Nhâm', 'Quý'])
        self.assertEqual(blocks[2].text.split('\n')[1], 'Quý Bính Nhâm Quý')

    def test_table_rows_skip_empty(self):
        self.assertEqual(table_rows('<table><tr><td> a </td><td>b</td></tr><tr><td></td></tr></table>'),
                         [['a', 'b']])

    def test_speaker_markers_carry_to_following_paragraphs(self):
        blocks = [OcrBlock('Nguyên văn: Bát tự dụng thần…', [0, 0, 1, 0.1], None, 0),
                  OcrBlock('chuyên cầu nguyệt lệnh', [0, 0.1, 1, 0.2], None, 0),
                  OcrBlock('Từ chú: nguyệt lệnh là…', [0, 0.2, 1, 0.3], None, 0)]
        assign_speakers(blocks)
        self.assertEqual([b.attributes.get('speaker') for b in blocks],
                         ['original_author', 'original_author', 'commentator'])

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

    def recognize(self, image):
        self.calls += 1
        if self.behaviour == 'timeout':
            raise OcrTimeout('fake timeout')
        if self.behaviour == 'oom':
            from backend.app.ingestion.ocr import OcrOutOfMemory
            raise OcrOutOfMemory('CUDA out of memory')
        if self.behaviour == 'empty':
            return []
        h, w = image.shape[:2]
        return [{'block_label': 'text', 'block_content': 'Thiên can địa chi, âm dương ngũ hành.',
                 'block_bbox': [w * 0.1, h * 0.1, w * 0.6, h * 0.15]}]


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
        self.assertEqual((revision_no, text_, rev_state), (2, 'Thiên can địa chi, âm dương ngũ hành.', 'accepted'))
        self.assertEqual((quality['needs_ocr'], quality['ocr']['mode']), (False, 'page'))
        block = self.sql("SELECT bbox, attributes->>'origin', start_offset, end_offset FROM blocks"
                         ' WHERE page_revision_id = %s', self.linked(gen)[0])[0]
        self.assertEqual((block[1], block[2], block[3]),
                         ('ocr', 0, len('Thiên can địa chi, âm dương ngũ hành.')))
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

    def test_gpu_out_of_memory_retries_the_page_instead_of_settling_it(self):
        state, job, gen = self.run_with(self.scan_pdf(), FakeEngine('oom'))
        self.assertEqual(state, 'retry_wait')          # the GPU is shared: try again later
        self.assertEqual(self.sql('SELECT reason_code FROM review_items WHERE generation_id = %s',
                                  gen), [])
        self.assertEqual(self.linked(gen)[1], 1)       # still the native revision, not settled

    def test_missing_engine_is_a_review_not_a_failure(self):
        job, gen = self.job_for(self.scan_pdf())

        def unavailable():
            from backend.app.ingestion.ocr import OcrUnavailable
            raise OcrUnavailable('no model')
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


@unittest.skipUnless(HAS_MODEL, 'SenOCR-Vi not in the model cache (run in the worker image)')
class SenOcrTests(unittest.TestCase):
    """The real model on real scanned pages (GPU)."""

    @classmethod
    def setUpClass(cls):
        from backend.app.ingestion.ocr import SenOcrEngine
        cls.engine = SenOcrEngine(str(MODEL_DIR))

    def test_scanned_vietnamese_page_is_read_with_its_pillar_tables(self):
        if not SCANNED.exists():
            self.skipTest('scanned Tử Bình Chân Thuyên not in inputs/books')
        doc = open_document(str(SCANNED))
        try:
            blocks, dpi = ocr_page(doc, 59, None, self.engine)      # printed page 60
        finally:
            doc.close()
        text_ = '\n'.join(b.text for b in blocks)
        self.assertIn('Nguyệt lệnh Quan tinh', text_)
        tables = [b for b in blocks if b.kind == 'table']
        self.assertGreaterEqual(len(tables), 2)
        self.assertTrue(any(b.attributes.get('chart_row') for b in tables))

    def test_pixel_bomb_page_goes_to_review_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = open_document(str(oversized_page(Path(tmp) / 'huge.pdf')))
            try:
                with self.assertRaises(OcrTimeout):
                    ocr_page(doc, 0, None, self.engine)
            finally:
                doc.close()


if __name__ == '__main__':
    unittest.main()
