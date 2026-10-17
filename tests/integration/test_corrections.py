"""Page corrections, incremental rebuilds and impact on PostgreSQL (T017)."""
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
from backend.app.documents.corrections import _overlaps, changed_range
from backend.app.ingestion.chunker import SEPARATOR, ChunkStage
from backend.app.ingestion.ocr_stage import OcrStage
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.quality import QualityStage
from backend.app.ingestion.structure import StructureStage
from backend.app.ingestion.worker import run_job
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
# Small chunks: one paragraph per chunk, so reuse is visible per paragraph.
CONFIG = '{"chunk": {"target": 25, "max": 60, "overlap": 0}}'
TYPO = 'chế phục thì quv'
BOOK = [
    ('CHƯƠNG 1: THỂ DỤNG', ['Thể là cái mình có, dụng là cái mình dùng để đạt mục đích.',
                          'Mệnh cục lấy thể dụng làm gốc, xem chủ khách mà luận đoán.',
                          'Câu này bàn về tài tinh của nhật chủ, người học cần đọc kỹ.']),
    ('CHƯƠNG 2: CÁCH CỤC', ['Cách cục thành thì quý, cách cục phá thì tiện, đó là lẽ thường.',
                           f'Thất sát gặp thực thần {TYPO}, hóa thành quyền uy.',
                           'Chính quan sợ thương quan, gặp ấn thụ thì được giải cứu.']),
    ('CHƯƠNG 3: ĐẠI VẬN', ['Đại vận mười năm một lần, xem can chi của vận mà định cát hung.',
                          'Lưu niên ứng kỳ phải phối hợp với đại vận mới thấy được sự việc.']),
]


class FakeOcr:
    version = 'fake-ocr 1.0'

    def __init__(self):
        self.calls = 0

    def words(self, image, langs):
        self.calls += 1
        return [{'text': text, 'left': str(left), 'top': '10', 'width': '60', 'height': '20',
                 'conf': '91', 'block_num': '1', 'par_num': '1', 'line_num': '1'}
                for text, left in (('Thiên', 10), ('cn', 80))]


class ChangedRangeTests(unittest.TestCase):
    def test_range_of_replacement_insertion_and_deletion(self):
        self.assertEqual(changed_range('abcdef', 'abXdef'), (2, 3))
        self.assertEqual(changed_range('abc', 'abXc'), (2, 2))
        self.assertEqual(changed_range('abXc', 'abc'), (2, 3))
        self.assertEqual(changed_range('aaa', 'aaaa'), (3, 3))

    def test_evidence_overlap(self):
        self.assertTrue(_overlaps(0, 5, (4, 6)))
        self.assertFalse(_overlaps(0, 4, (4, 6)))
        self.assertTrue(_overlaps(0, 4, (4, 4)))       # insertion right after the quote
        self.assertTrue(_overlaps(7, 9, None))         # whole-block change


class CorrectionTests(unittest.TestCase):
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
        with cls.owner_engine.begin() as conn:
            profile = register_profile(conn, 'fixture-hashing', 'fix', 'r1', 32)
        with psycopg.connect(database_url(cls.db), autocommit=True) as conn:
            provision_collection(conn, profile)
            cls.pipeline = conn.execute(
                "INSERT INTO pipeline_profiles (name, parser_version, chunker_version,"
                " normalizer_version, embedding_profile_id, config, config_hash) VALUES ('p', 'x',"
                " '1', '1', %s, %s, %s) RETURNING id",
                (profile.id, CONFIG, sha(uuid.uuid4().hex))).fetchone()[0]
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

    def setUp(self):
        self.ocr = FakeOcr()

    # ---- helpers --------------------------------------------------------------------
    def sql(self, query, *params):
        with psycopg.connect(database_url(self.db), autocommit=True) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall() if cursor.description else None

    def run_job(self, job):
        stages = [ValidatePdfStage(), ExtractPdfStage(), OcrStage(engine_factory=lambda: self.ocr),
                  StructureStage(), QualityStage(), ChunkStage(), EmbedStage()]
        return run_job(self.engine, self.store, job, stages, 'w')

    def ingest(self, pages=BOOK, scan_page=False):
        builder = PdfBuilder()
        for title, paragraphs in pages:
            builder.page(lines=[(title, 72, 720, 18, BLACK)] +
                         [(p, 72, 680 - 40 * i, 11, BLACK) for i, p in enumerate(paragraphs)])
        if scan_page:
            builder.page(image=(0, 0, 612, 792))
        pdf = builder.save(self.tmp / f'{uuid.uuid4().hex}.pdf')
        with self.engine.begin() as conn, open(pdf, 'rb') as source:
            obj = store_object(conn, self.store, source, 'application/pdf')
        book = self.sql("INSERT INTO books (title, normalized_title, language, created_by)"
                        " VALUES ('s', 's', 'vi', %s) RETURNING id", self.user)[0][0]
        version = self.sql("INSERT INTO book_versions (book_id, object_id, edition_label,"
                           " version_no, rights_status, uploaded_by) VALUES (%s, %s, 'v1', 1,"
                           " 'private_reference', %s) RETURNING id", book, obj['id'], self.user)[0][0]
        gen = self.sql('INSERT INTO generations (book_version_id, pipeline_profile_id)'
                       ' VALUES (%s, %s) RETURNING id', version, self.pipeline)[0][0]
        job = self.sql('INSERT INTO ingestion_jobs (book_version_id, generation_id,'
                       ' pipeline_profile_id, requested_by) VALUES (%s, %s, %s, %s) RETURNING id',
                       version, gen, self.pipeline, self.user)[0][0]
        self.assertEqual(self.run_job(job), 'succeeded')
        return version, gen

    def page(self, version, number):
        response = self.c.get(f'/api/v1/book-versions/{version}/pages')
        self.assertEqual(response.status_code, 200, response.text)
        page = next(p for p in response.json()['data'] if p['physical_page_number'] == number)
        revision = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}")
        self.assertEqual(revision.status_code, 200, revision.text)
        self.assertEqual(revision.headers['ETag'], f'"{page["revision_id"]}"')
        return page, revision.json()['data']['blocks']

    def correct(self, page, base, changes, etag=None, key=None, client=None):
        headers = {'Idempotency-Key': key or uuid.uuid4().hex}
        if etag is not False:
            headers['If-Match'] = f'"{etag or base}"'
        return (client or self.c).post(
            f'/api/v1/pages/{page}/corrections', headers=headers,
            json={'base_revision_id': base, 'changes': changes, 'reason': 'sửa lỗi OCR'})

    def chunks(self, gen):
        """(chunk id, text, section title, pages) in reading order."""
        return [(str(cid), text, title, pages) for cid, text, title, pages in self.sql(
            'SELECT c.id, c.text, s.title, array_agg(DISTINCT p.physical_page_number)'
            ' FROM generation_chunks gc JOIN chunks c ON c.id = gc.chunk_id'
            ' JOIN sections s ON s.id = gc.section_id JOIN chunk_spans sp ON sp.chunk_id = c.id'
            ' JOIN page_revisions r ON r.id = sp.page_revision_id JOIN pages p ON p.id = r.page_id'
            ' WHERE gc.generation_id = %s GROUP BY c.id, c.text, s.title, gc.ordinal'
            ' ORDER BY gc.ordinal', gen)]

    def counters(self, job):
        return self.sql('SELECT counters FROM ingestion_jobs WHERE id = %s', job)[0][0]

    def impact(self, gen, **params):
        response = self.c.get(f'/api/v1/generations/{gen}/impact', params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def assert_provenance(self, gen):
        bad = self.sql(
            'SELECT count(*) FROM generation_chunks gc JOIN chunks c ON c.id = gc.chunk_id'
            ' JOIN chunk_spans s ON s.chunk_id = c.id JOIN page_revisions r'
            ' ON r.id = s.page_revision_id WHERE gc.generation_id = %s'
            ' AND substr(c.text, s.chunk_start + 1, s.chunk_end - s.chunk_start)'
            ' <> substr(r.normalized_text, s.start_offset + 1, s.end_offset - s.start_offset)', gen)
        self.assertEqual(bad[0][0], 0)
        for text_, pieces in self.sql(
                'SELECT c.text, array_agg(substr(c.text, s.chunk_start + 1, s.chunk_end'
                ' - s.chunk_start) ORDER BY s.ordinal) FROM generation_chunks gc JOIN chunks c'
                ' ON c.id = gc.chunk_id JOIN chunk_spans s ON s.chunk_id = c.id'
                ' WHERE gc.generation_id = %s GROUP BY c.id, c.text', gen):
            self.assertEqual(text_, SEPARATOR.join(pieces))

    def evidence(self, version, block, start, end):
        """Evidence on ``block`` at revision offsets [start, end)."""
        return str(self.sql(
            'INSERT INTO evidence_spans (book_version_id, page_revision_id, block_id, start_offset,'
            ' end_offset, quote_hash, speaker_layer, origin) SELECT %s, b.page_revision_id, b.id,'
            ' %s, %s, bazi_sha256_text(substr(r.normalized_text, %s + 1, %s - %s)),'
            " b.speaker_layer, 'source_explicit' FROM blocks b JOIN page_revisions r"
            ' ON r.id = b.page_revision_id WHERE b.id = %s RETURNING id',
            version, start, end, start, end, start, block['id'])[0][0])

    def rule(self, evidence):
        rule = self.sql(
            'WITH m AS (INSERT INTO methods (school_id, key, revision, description)'
            " SELECT id, %s, 1, 'test' FROM schools WHERE key = 'tu_binh' RETURNING id, school_id)"
            ' INSERT INTO knowledge_rules (rule_key, revision, school_id, method_id, dsl, dsl_hash,'
            " fact_schema_version, author_id) SELECT %s, 1, m.school_id, m.id, '{}',"
            " bazi_sha256_text('{}'::jsonb::text), 'facts-1', %s FROM m RETURNING id",
            uuid.uuid4().hex, uuid.uuid4().hex, self.user)[0][0]
        self.sql('INSERT INTO rule_sources (rule_id, evidence_id) VALUES (%s, %s)', rule, evidence)
        return str(rule)

    def assertion(self, evidence):
        assertion = self.sql(
            'INSERT INTO assertions (assertion_key, revision, school_id, statement, origin,'
            " author_id) SELECT %s, 1, id, 'Thất sát có chế thì quý', 'source_explicit', %s"
            " FROM schools WHERE key = 'tu_binh' RETURNING id", uuid.uuid4().hex, self.user)[0][0]
        self.sql("INSERT INTO assertion_sources (assertion_id, evidence_id, relation)"
                 " VALUES (%s, %s, 'states')", assertion, evidence)
        return str(assertion)

    # ---- acceptance -----------------------------------------------------------------
    def test_paragraph_fix_replaces_only_its_page_and_embeds_only_new_text(self):
        version, gen1 = self.ingest()
        before = self.chunks(gen1)
        self.assertEqual(len(before), 8)                       # one chunk per paragraph
        page, blocks = self.page(version, 2)
        block = next(b for b in blocks if TYPO in b['text'])
        fixed = f'quý {uuid.uuid4().hex[:6]}'     # text no other test has embedded yet
        response = self.correct(page['page_id'], page['revision_id'],
                                [{'ordinal': block['ordinal'],
                                  'text': block['text'].replace('quv', fixed)}])
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()['data']
        self.assertEqual((data['revision']['revision_no'], data['changed_blocks'],
                          data['coalesced']), (2, [block['ordinal']], False))
        self.assertEqual(response.headers['ETag'], f'"{data["revision"]["id"]}"')
        self.assertEqual(self.run_job(data['job_id']), 'succeeded')
        gen2 = data['generation_id']
        after = self.chunks(gen2)
        self.assertEqual([t for _, t, _, _ in after],
                         [t.replace('quv', fixed) for _, t, _, _ in before])
        # Pages 1 and 3 keep their chunk rows; page 2 is re-chunked onto its new revision.
        self.assertEqual({c for c, _, _, pages in after if pages != [2]},
                         {c for c, _, _, pages in before if pages != [2]})
        self.assertFalse({c for c, _, _, pages in after if pages == [2]} & {c for c, *_ in before})
        self.assertEqual(self.counters(data['job_id'])['embeddings_computed'], 1)
        counts = self.impact(gen2)['counts']
        self.assertEqual({k: counts[k] for k in ('page', 'chunk_added', 'chunk_removed',
                                                 'chunk_reused', 'section_added',
                                                 'section_removed')},
                         {'page': 1, 'chunk_added': 3, 'chunk_removed': 3, 'chunk_reused': 5,
                          'section_added': 0, 'section_removed': 0})
        self.assert_provenance(gen2)
        old = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}").json()['data']
        self.assertIn(TYPO, old['text'])
        self.assertFalse(old['is_latest'])
        self.assertEqual(old['latest_revision_id'], data['revision']['id'])

    def test_heading_change_reshapes_only_its_section(self):
        version, gen1 = self.ingest()
        before = self.chunks(gen1)
        page, blocks = self.page(version, 1)
        chapter = next(b for b in blocks if b['kind'] == 'heading')
        promoted = next(b for b in blocks if b['text'].startswith('Mệnh cục'))
        level = (chapter['attributes'].get('level') or 2) + 1
        response = self.correct(page['page_id'], page['revision_id'],
                                [{'ordinal': promoted['ordinal'], 'kind': 'heading',
                                  'level': level}])
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()['data']
        self.assertEqual(self.run_job(data['job_id']), 'succeeded')
        after = self.chunks(data['generation_id'])
        # The promoted paragraph is now a title: its text left the chunks, and the
        # paragraph after it belongs to the new subsection.
        self.assertEqual([t for _, t, _, _ in after],
                         [t for _, t, _, _ in before if not t.startswith('Mệnh cục')])
        self.assertEqual(next(s for _, t, s, _ in after if t.startswith('Câu này')),
                         promoted['text'])
        self.assertEqual({c for c, _, _, pages in after if pages != [1]},
                         {c for c, _, _, pages in before if pages != [1]})
        self.assertEqual(self.counters(data['job_id'])['embeddings_computed'], 0)
        counts = self.impact(data['generation_id'])['counts']
        self.assertEqual((counts['section_added'], counts['section_removed'],
                          counts['chunk_removed'], counts['chunk_added']), (1, 0, 3, 2))

    def test_old_citations_stay_put_and_dependents_are_flagged(self):
        version, _ = self.ingest()
        page, blocks = self.page(version, 2)
        block = next(b for b in blocks if TYPO in b['text'])
        start = block['start_offset']
        hit_at = start + block['text'].index(TYPO)
        hit = self.evidence(version, block, hit_at, hit_at + len(TYPO))
        miss_at = start + block['text'].index('Thất sát')
        miss = self.evidence(version, block, miss_at, miss_at + len('Thất sát'))
        rule_hit, rule_miss, assertion = self.rule(hit), self.rule(miss), self.assertion(hit)
        response = self.correct(page['page_id'], page['revision_id'],
                                [{'ordinal': block['ordinal'],
                                  'text': block['text'].replace('quv', 'quý')}])
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()['data']
        self.assertEqual(data['source_changed'], {'evidence': [hit], 'rule': [rule_hit],
                                                  'assertion': [assertion], 'case_revision': []})
        flagged = self.sql("SELECT entity_kind, entity_id::text FROM review_items WHERE"
                           " reason_code = 'SOURCE_CHANGED' AND generation_id = %s",
                           data['generation_id'])
        self.assertEqual(sorted(flagged), sorted([('rule', rule_hit), ('assertion', assertion)]))
        # Citations do not drift: the evidence still quotes the old revision verbatim,
        # and the reviewed rules are not rewritten.
        quote = self.sql('SELECT e.page_revision_id::text, substr(r.normalized_text,'
                         ' e.start_offset + 1, e.end_offset - e.start_offset) FROM evidence_spans e'
                         ' JOIN page_revisions r ON r.id = e.page_revision_id WHERE e.id = %s', hit)
        self.assertEqual(quote, [(page['revision_id'], TYPO)])
        self.assertEqual(self.sql('SELECT state FROM knowledge_rules WHERE id = ANY(%s::uuid[])',
                                  [rule_hit, rule_miss]), [('draft',), ('draft',)])
        self.assertEqual(self.run_job(data['job_id']), 'succeeded')
        impact = self.impact(data['generation_id'], kind='rule')
        self.assertEqual((impact['counts']['rule'], impact['counts']['assertion'],
                          impact['counts']['evidence'], impact['ids']), (1, 1, 1, [rule_hit]))

    def test_preconditions_idempotency_and_coalescing(self):
        version, _ = self.ingest()
        (p1, blocks1), (p2, blocks2) = self.page(version, 1), self.page(version, 2)
        para = next(b for b in blocks1 if b['kind'] == 'paragraph')
        change = [{'ordinal': para['ordinal'], 'text': para['text'] + ' Thêm chữ.'}]
        self.assertEqual(self.correct(p1['page_id'], p1['revision_id'], change,
                                      etag=False).status_code, 428)
        missing_key = self.c.post(f"/api/v1/pages/{p1['page_id']}/corrections",
                                  headers={'If-Match': f'"{p1["revision_id"]}"'},
                                  json={'base_revision_id': p1['revision_id'], 'changes': change,
                                        'reason': 'sửa lỗi OCR'})
        self.assertEqual(missing_key.status_code, 422)
        reader, _ = self.client('reader')
        self.assertEqual(self.correct(p1['page_id'], p1['revision_id'], change,
                                      client=reader).status_code, 403)
        same = self.correct(p1['page_id'], p1['revision_id'],
                            [{'ordinal': para['ordinal'], 'text': para['text']}])
        self.assertEqual((same.status_code, same.json()['code']), (422, 'NO_CHANGE'))
        unknown = self.correct(p1['page_id'], p1['revision_id'], [{'ordinal': 99, 'text': 'x'}])
        self.assertEqual(unknown.status_code, 422)

        key = uuid.uuid4().hex
        first = self.correct(p1['page_id'], p1['revision_id'], change, key=key)
        self.assertEqual(first.status_code, 201, first.text)
        replay = self.correct(p1['page_id'], p1['revision_id'], change, key=key)
        self.assertEqual((replay.status_code, replay.json()['data']),
                         (201, first.json()['data']))
        revisions = 'SELECT count(*) FROM page_revisions WHERE page_id = %s'
        self.assertEqual(self.sql(revisions, p1['page_id'])[0][0], 2)
        stale = self.correct(p1['page_id'], p1['revision_id'],
                             [{'ordinal': para['ordinal'], 'kind': 'caption'}])
        self.assertEqual((stale.status_code, stale.headers['ETag']),
                         (412, f'"{first.json()["data"]["revision"]["id"]}"'))

        # A second page corrected while the rebuild is still queued joins it.
        other = next(b for b in blocks2 if TYPO in b['text'])
        second = self.correct(p2['page_id'], p2['revision_id'],
                              [{'ordinal': other['ordinal'], 'speaker_layer': 'original_author'}])
        self.assertEqual(second.status_code, 201, second.text)
        job = first.json()['data']['job_id']
        self.assertEqual((second.json()['data']['coalesced'], second.json()['data']['job_id']),
                         (True, job))
        linked = self.sql('SELECT r.revision_no FROM generation_pages gp JOIN page_revisions r'
                          ' ON r.id = gp.page_revision_id WHERE gp.generation_id = %s'
                          ' ORDER BY r.revision_no DESC', first.json()['data']['generation_id'])
        self.assertEqual([n for (n,) in linked], [2, 2, 1])

        # Once a worker runs it, a further correction is refused rather than lost.
        self.sql("UPDATE ingestion_jobs SET state = 'running' WHERE id = %s", job)
        latest = first.json()['data']['revision']['id']
        busy = self.correct(p1['page_id'], latest, [{'ordinal': para['ordinal'],
                                                      'kind': 'caption'}])
        self.assertEqual((busy.status_code, busy.json()['code']), (409, 'JOB_ACTIVE'))
        self.assertEqual(self.sql(revisions, p1['page_id'])[0][0], 2)
        self.assertEqual(self.run_job(job), 'succeeded')
        self.assertEqual(self.impact(first.json()['data']['generation_id'])['counts']['page'], 2)

    def test_corrected_ocr_text_is_not_ocred_again(self):
        version, gen1 = self.ingest(pages=BOOK[:1], scan_page=True)
        calls = self.ocr.calls
        self.assertGreater(calls, 0)
        page, blocks = self.page(version, 2)
        self.assertEqual(page['revision_no'], 2)                    # OCR merged revision
        ocr_block = next(b for b in blocks if b['attributes'].get('origin') == 'ocr')
        self.assertEqual(ocr_block['text'], 'Thiên cn')
        response = self.correct(page['page_id'], page['revision_id'],
                                [{'ordinal': ocr_block['ordinal'], 'text': 'Thiên can'}])
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()['data']
        self.assertEqual(self.run_job(data['job_id']), 'succeeded')
        self.assertEqual(self.ocr.calls, calls)                     # no OCR over the fix
        linked = self.sql('SELECT r.revision_no FROM generation_pages gp JOIN page_revisions r'
                          ' ON r.id = gp.page_revision_id JOIN pages p ON p.id = gp.page_id'
                          ' WHERE gp.generation_id = %s AND p.physical_page_number = 2',
                          data['generation_id'])
        self.assertEqual(linked, [(3,)])
        texts = SEPARATOR.join(t for _, t, _, _ in self.chunks(data['generation_id']))
        self.assertIn('Thiên can', texts)
        self.assertNotIn('Thiên cn', texts)


if __name__ == '__main__':
    unittest.main()
