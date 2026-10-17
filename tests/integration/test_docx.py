"""DOCX extraction and canonical rendering (T013).

Rendering needs LibreOffice (worker image ``test`` target); on hosts without it
the rendering checks skip and the pipeline exercises the anchor-only path.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import psycopg

from backend.app.ingestion import docx as docx_module
from backend.app.ingestion.docx import DocxRejected, extract, parse, soffice
from backend.app.ingestion.docx_stage import DocxExtractStage
from backend.app.ingestion.worker import run_job
from backend.app.storage.local import LocalObjectStore
from backend.app.storage.service import store_object
from tests.fixtures.docx_factory import paragraph, sample_body, write_docx
from tests.integration.db import (ADMIN_URL, ROOT, create_runtime_login, database_url,
                                  drop_database, drop_role, engine_for, migrated_database, sha)
from tests.integration.factories import Factory

HAS_SOFFICE = soffice() is not None
REAL_DOCX = ROOT / 'inputs' / 'books' / 'Tên Sách Chưa Đặt.docx'
DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.tmp, ignore_errors=True))

    def test_blocks_anchors_kinds_and_tables(self):
        blocks = parse(write_docx(self.tmp / 'a.docx', sample_body()))
        self.assertEqual([(b.anchor, b.kind) for b in blocks], [
            ('body/p[1]', 'heading'), ('body/p[2]', 'paragraph'), ('body/p[3]', 'heading'),
            ('body/p[4]', 'paragraph'), ('body/tbl[1]', 'table'), ('body/p[5]', 'paragraph'),
            ('body/p[6]', 'heading'), ('body/p[7]', 'paragraph')])
        table = blocks[4]
        self.assertEqual(table.table_cells, [['Thiên Can', 'Giáp', 'Ất'], ['Lộc', 'Dần', 'Mão']])
        self.assertEqual(table.text, 'Thiên Can | Giáp | Ất\nLộc | Dần | Mão')
        self.assertEqual(blocks[5].text, 'Đoạn nằm trong content control vẫn được đọc.')

    def test_anchors_are_stable_when_text_changes(self):
        before = parse(write_docx(self.tmp / 'a.docx', sample_body()))
        after = parse(write_docx(self.tmp / 'b.docx', sample_body(' (sửa)')))
        self.assertEqual([b.anchor for b in before], [b.anchor for b in after])
        self.assertNotEqual(before[2].text, after[2].text)

    def test_entities_and_non_word_archives_rejected(self):
        bad_xml = self.tmp / 'entity.docx'
        write_docx(bad_xml, paragraph('x'))
        import zipfile
        with zipfile.ZipFile(bad_xml, 'a') as archive:
            pass
        with zipfile.ZipFile(self.tmp / 'evil.docx', 'w') as archive:
            archive.writestr('word/document.xml', '<!DOCTYPE x [<!ENTITY a "b">]><x>&a;</x>')
        with zipfile.ZipFile(self.tmp / 'notword.docx', 'w') as archive:
            archive.writestr('content.xml', '<x/>')
        for name, code in (('evil.docx', 'DOCX_INVALID'), ('notword.docx', 'DOCX_INVALID')):
            with self.subTest(name=name):
                with self.assertRaises(DocxRejected) as caught:
                    parse(self.tmp / name)
                self.assertEqual(caught.exception.code, code)

    def test_render_failure_falls_back_to_anchors(self):
        path = write_docx(self.tmp / 'a.docx', sample_body())
        with patch.object(docx_module, 'soffice', return_value=None):
            doc = extract(path, self.tmp)
        self.assertEqual((doc.rendered_pdf, doc.render_error), (None, 'RENDER_UNAVAILABLE'))
        self.assertTrue(all(b.page is None and b.bbox is None for b in doc.blocks))

    @unittest.skipUnless(REAL_DOCX.is_file(), 'original DOCX not present')
    def test_real_docx_structure(self):
        blocks = parse(REAL_DOCX)
        kinds = [b.kind for b in blocks]
        self.assertEqual(kinds.count('table'), 80)   # matches the T057 inventory
        self.assertGreater(kinds.count('heading'), 50)
        self.assertEqual(len({b.anchor for b in blocks}), len(blocks))


@unittest.skipUnless(HAS_SOFFICE, 'LibreOffice not installed (run in the worker image)')
class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.tmp, ignore_errors=True))

    def test_render_locates_paragraphs_and_tables(self):
        long_body = sample_body() + ''.join(
            paragraph(f'Đoạn bổ sung số {i} để tài liệu sang trang thứ hai.') for i in range(80))
        doc = extract(write_docx(self.tmp / 'a.docx', long_body), self.tmp)
        self.assertIsNotNone(doc.rendered_pdf)
        self.assertGreaterEqual(doc.rendered_pages, 2)
        self.assertGreaterEqual(doc.located / len(doc.blocks), 0.9)
        pages = [b.page for b in doc.blocks if b.page]
        self.assertEqual(pages, sorted(pages))              # document order preserved
        table = next(b for b in doc.blocks if b.kind == 'table')
        self.assertEqual(table.page, 1)
        self.assertTrue(table.bbox and all(0 <= v <= 1 for v in table.bbox))
        self.assertTrue(doc.renderer and 'LibreOffice' in doc.renderer)

    @unittest.skipUnless(REAL_DOCX.is_file(), 'original DOCX not present')
    def test_real_docx_renders_and_locates(self):
        doc = extract(REAL_DOCX, self.tmp)
        self.assertIsNotNone(doc.rendered_pdf, doc.render_error)
        self.assertGreaterEqual(doc.located / len(doc.blocks), 0.9)


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
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(self.tmp, ignore_errors=True))
        self.store = LocalObjectStore(self.tmp / 'store')
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            self.user = f.user()
            self.book = f.one("INSERT INTO books (title, normalized_title, language, created_by)"
                              " VALUES ('d', 'd', 'vi', %s) RETURNING id", self.user)
            self.profile = f.one("INSERT INTO pipeline_profiles (name, parser_version,"
                                 " chunker_version, normalizer_version, embedding_profile_id,"
                                 " config_hash) VALUES ('p', 'x', '1', '1', %s, %s) RETURNING id",
                                 f.embedding_profile(), sha(uuid.uuid4().hex))

    def process(self, path: Path, version_no: int):
        with self.engine.begin() as conn, open(path, 'rb') as source:
            obj = store_object(conn, self.store, source, DOCX_MIME)
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            f = Factory(conn)
            version = f.one("INSERT INTO book_versions (book_id, object_id, edition_label,"
                            " version_no, rights_status, uploaded_by) VALUES (%s, %s, %s, %s,"
                            " 'private_reference', %s) RETURNING id", self.book, obj['id'],
                            f'v{version_no}', version_no, self.user)
            gen = f.one('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                        ' VALUES (%s, %s) RETURNING id', version, self.profile)
            job = f.one('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                        ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                        version, gen, self.profile, self.user)
        state = run_job(self.engine, self.store, job, [DocxExtractStage()], 'w1')
        return state, version, gen

    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db)) as conn:
            return conn.execute(query, params).fetchall()

    def test_docx_job_and_new_upload_gives_new_generation(self):
        state, version, gen = self.process(write_docx(self.tmp / 'v1.docx', sample_body()), 1)
        self.assertEqual(state, 'succeeded')
        kinds = {r[0] for r in self.sql('SELECT p.page_kind FROM generation_pages gp JOIN pages p'
                                        ' ON p.id = gp.page_id WHERE gp.generation_id = %s', gen)}
        self.assertEqual(kinds, {'docx_rendered_page' if HAS_SOFFICE else 'docx_anchor'})
        anchors = [r[0] for r in self.sql(
            "SELECT b.attributes->>'anchor' FROM generation_pages gp JOIN blocks b"
            ' ON b.page_revision_id = gp.page_revision_id JOIN pages p ON p.id = gp.page_id'
            ' WHERE gp.generation_id = %s ORDER BY p.physical_page_number, b.ordinal', gen)]
        self.assertEqual(anchors[:5], ['body/p[1]', 'body/p[2]', 'body/p[3]', 'body/p[4]',
                                       'body/tbl[1]'])
        table = self.sql("SELECT b.table_cells, b.text, r.normalized_text, b.start_offset,"
                         ' b.end_offset FROM blocks b JOIN page_revisions r'
                         " ON r.id = b.page_revision_id WHERE b.kind = 'table'"
                         ' AND r.id IN (SELECT page_revision_id FROM generation_pages'
                         ' WHERE generation_id = %s)', gen)[0]
        self.assertEqual(table[0][1], ['Lộc', 'Dần', 'Mão'])
        self.assertEqual(table[2][table[3]:table[4]], table[1])   # source opens at the table
        if not HAS_SOFFICE:
            self.assertEqual(self.sql('SELECT reason_code FROM review_items WHERE generation_id = %s',
                                      gen), [('DOCX_RENDER_FAILED',)])
            boxes = self.sql('SELECT DISTINCT b.bbox FROM blocks b JOIN generation_pages gp'
                             ' ON gp.page_revision_id = b.page_revision_id'
                             ' WHERE gp.generation_id = %s', gen)
            self.assertEqual(boxes, [(None,)])                     # no invented geometry
        old_texts = self.sql('SELECT r.id, r.normalized_text FROM generation_pages gp JOIN'
                             ' page_revisions r ON r.id = gp.page_revision_id'
                             ' WHERE gp.generation_id = %s ORDER BY r.id', gen)
        state2, version2, gen2 = self.process(write_docx(self.tmp / 'v2.docx',
                                                         sample_body(' (sửa)')), 2)
        self.assertEqual(state2, 'succeeded')
        self.assertNotEqual(version2, version)
        new_text = ' '.join(r[0] for r in self.sql(
            'SELECT r.normalized_text FROM generation_pages gp JOIN page_revisions r'
            ' ON r.id = gp.page_revision_id WHERE gp.generation_id = %s', gen2))
        self.assertIn('Khách – Chủ (sửa)', new_text)
        self.assertEqual(old_texts, self.sql('SELECT r.id, r.normalized_text FROM generation_pages'
                                             ' gp JOIN page_revisions r ON r.id = gp.page_revision_id'
                                             ' WHERE gp.generation_id = %s ORDER BY r.id', gen))


if __name__ == '__main__':
    unittest.main()
