"""Jobs API (list, detail, events, retry, cancel) and the review queue (T019)."""
import unittest
import uuid

from backend.app.ingestion.chunker import ChunkStage
from backend.app.ingestion.ocr_stage import OcrStage
from backend.app.ingestion.pdf_stages import ExtractPdfStage, ValidatePdfStage
from backend.app.ingestion.publish import PublishStage
from backend.app.ingestion.quality import QualityStage
from backend.app.ingestion.structure import StructureStage
from backend.app.ingestion.worker import Unit, UnitFailed
from backend.app.retrieval.indexer import EmbedStage
from tests.integration.env import PipelineTestCase, no_ocr


class FlakyStage:
    """Fails until fixed; stands in for a unit that needs a retry."""
    name = 'inspect'

    def __init__(self):
        self.broken = True

    def units(self, ctx):
        return [Unit('doc', 'a' * 64)]

    def compute(self, ctx, unit):
        if self.broken:
            raise UnitFailed('FLAKY', 'broken on purpose')
        return {}

    def persist(self, conn, ctx, unit, result):
        return {}


class JobsApiTests(PipelineTestCase):
    def stages(self, flaky):
        return [ValidatePdfStage(), ExtractPdfStage(), flaky, OcrStage(engine_factory=no_ocr),
                StructureStage(), QualityStage(), ChunkStage(), EmbedStage(), PublishStage()]

    def post(self, path, body=None):
        return self.c.post(path, json=body or {}, headers={'Idempotency-Key': uuid.uuid4().hex})

    def test_failed_job_detail_events_and_retry(self):
        flaky = FlakyStage()
        version, _, job = self.queue()
        self.assertEqual(self.run_pipeline(job, self.stages(flaky)), 'failed')
        detail = self.c.get(f'/api/v1/jobs/{job}').json()['data']
        self.assertEqual((detail['state'], detail['stage'], detail['error']['code'],
                          detail['error']['retryable']), ('failed', 'inspect', 'FLAKY', False))
        self.assertEqual((detail['book_title'], detail['edition_label']), ('b', 'v1'))
        stages = {s['stage']: s for s in detail['stages']}
        self.assertTrue(stages['extract']['done'])
        self.assertEqual((stages['inspect']['units'], stages['inspect']['done']), (1, False))

        retry = self.post(f'/api/v1/jobs/{job}/retry')
        self.assertEqual(retry.status_code, 202, retry.text)
        child = retry.json()['data']
        self.assertEqual((child['parent_job_id'], child['state'], child['generation_id']),
                         (job, 'queued', detail['generation_id']))
        busy = self.post(f'/api/v1/jobs/{job}/retry')
        self.assertEqual((busy.status_code, busy.json()['code']), (409, 'JOB_ACTIVE'))
        flaky.broken = False
        self.assertEqual(self.run_pipeline(child['id'], self.stages(flaky)), 'succeeded')
        done = {s['stage']: s for s in
                self.c.get(f"/api/v1/jobs/{child['id']}").json()['data']['stages']}
        self.assertEqual((done['validate']['reused'], done['validate']['computed']), (1, 0))
        self.assertEqual(done['extract']['computed'], 0)          # pages were not re-extracted
        self.assertEqual(done['inspect']['computed'], 1)
        self.assertEqual(self.c.get(f'/api/v1/jobs/{job}').json()['data']['retried_by'],
                         [child['id']])
        again = self.post(f"/api/v1/jobs/{child['id']}/retry")
        self.assertEqual(again.json()['code'], 'JOB_NOT_RETRYABLE')

        codes = [e['code'] for e in
                 self.c.get(f'/api/v1/jobs/{job}/events', params={'limit': 500}).json()['data']]
        self.assertEqual((codes[0], codes[-2:]), ('JOB_STARTED', ['JOB_FAILED', 'RETRIED']))
        first = self.c.get(f'/api/v1/jobs/{job}/events', params={'limit': 2}).json()
        self.assertEqual([e['seq'] for e in first['data']], [1, 2])
        rest = self.c.get(f'/api/v1/jobs/{job}/events',
                          params={'after_seq': first['page']['next_cursor']}).json()['data']
        self.assertEqual(rest[0]['seq'], 3)
        listed = self.c.get('/api/v1/jobs', params={'book_version_id': version}).json()['data']
        self.assertEqual({j['id'] for j in listed}, {job, child['id']})
        failed = self.c.get('/api/v1/jobs', params={'book_version_id': version,
                                                    'state': 'failed'}).json()['data']
        self.assertEqual([j['id'] for j in failed], [job])

    def test_cancel(self):
        _, _, queued = self.queue()
        response = self.c.post(f'/api/v1/jobs/{queued}/cancel')
        self.assertEqual((response.status_code, response.json()['data']['state']),
                         (200, 'cancelled'))
        _, _, running = self.queue()
        self.sql("UPDATE ingestion_jobs SET state = 'running' WHERE id = %s", running)
        response = self.c.post(f'/api/v1/jobs/{running}/cancel')
        self.assertEqual((response.status_code, response.json()['data']['state']),
                         (202, 'cancel_requested'))
        self.assertEqual(self.run_pipeline(running), 'cancelled')
        terminal = self.c.post(f'/api/v1/jobs/{running}/cancel')
        self.assertEqual((terminal.status_code, terminal.json()['data']['state']),
                         (200, 'cancelled'))
        reader, _ = self.client('reader')
        self.assertEqual(reader.get('/api/v1/jobs').status_code, 403)
        self.assertEqual(self.c.get(f'/api/v1/jobs/{uuid.uuid4()}').status_code, 404)

    def test_review_queue_exclude_and_dismiss(self):
        version, gen = self.ready(scan=True)            # page 3 is a scan, OCR unavailable
        items = self.c.get('/api/v1/review-items',
                           params={'book_version_id': version}).json()['data']
        ocr = next(i for i in items if i['reason_code'] == 'OCR_UNAVAILABLE')
        self.assertEqual((ocr['physical_page_number'], ocr['state'], ocr['generation_id'],
                          ocr['book_title']), (3, 'open', gen, 'b'))
        scoped = {scope: {i['id'] for i in self.c.get('/api/v1/review-items', params={
            'book_version_id': version, 'scope': scope}).json()['data']}
            for scope in ('page', 'knowledge')}
        self.assertIn(ocr['id'], scoped['page'])
        self.assertNotIn(ocr['id'], scoped['knowledge'])
        self.assertEqual(self.c.get(f"/api/v1/review-items/{ocr['id']}").json()['data'], ocr)
        self.assertEqual(self.c.get(f'/api/v1/review-items/{uuid.uuid4()}').status_code, 404)
        page = next(p for p in self.c.get(f'/api/v1/book-versions/{version}/pages').json()['data']
                    if p['physical_page_number'] == 3)
        url = f"/api/v1/review-items/{ocr['id']}/resolve"
        stale = self.post(url, {'action': 'exclude', 'reason': 'trang ảnh bìa',
                                'base_revision_id': str(uuid.uuid4())})
        self.assertEqual(stale.status_code, 412)
        missing = self.post(url, {'action': 'exclude', 'reason': 'trang ảnh bìa'})
        self.assertEqual(missing.status_code, 422)
        done = self.post(url, {'action': 'exclude', 'reason': 'trang ảnh bìa',
                               'base_revision_id': page['revision_id']})
        self.assertEqual(done.status_code, 200, done.text)
        result = done.json()['data']
        self.assertEqual(result['item']['state'], 'resolved')
        self.assertEqual(self.run_pipeline(result['job_id']), 'succeeded')
        view = self.c.get(f"/api/v1/generations/{result['generation_id']}").json()['data']
        self.assertEqual((view['coverage']['excluded'], view['coverage']['excluded_ranges']),
                         (1, ['3']))
        reopened = self.c.get('/api/v1/review-items', params={
            'generation_id': result['generation_id'], 'reason': 'OCR_UNAVAILABLE'}).json()['data']
        self.assertEqual(reopened, [])                   # an excluded page is not OCR'd again
        closed = self.post(url, {'action': 'dismiss', 'reason': 'đã xử lý'})
        self.assertEqual(closed.json()['code'], 'REVIEW_CLOSED')

        manual = str(self.sql("INSERT INTO review_items (generation_id, reason_code, severity)"
                              " VALUES (%s, 'MANUAL_CHECK', 'low') RETURNING id", gen)[0][0])
        wrong = self.post(f'/api/v1/review-items/{manual}/resolve',
                          {'action': 'accept', 'reason': 'xem lại',
                           'base_revision_id': page['revision_id']})
        self.assertEqual(wrong.status_code, 422)
        dismissed = self.post(f'/api/v1/review-items/{manual}/resolve',
                              {'action': 'dismiss', 'reason': 'không cần sửa'})
        self.assertEqual((dismissed.status_code, dismissed.json()['data']['item']['state'],
                          dismissed.json()['data']['job_id']), (200, 'dismissed', None))


if __name__ == '__main__':
    unittest.main()
