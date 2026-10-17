"""Retrieval evaluation: metric definitions, datasets, sign-off and runs (T036)."""
import math
import unittest
import uuid

from backend.app.retrieval.evaluate import _scores
from tests.fixtures.pdf_factory import PdfBuilder
from tests.integration.env import BLACK, PipelineTestCase
from tests.integration.test_search import MANH, TU_BINH


class MetricTests(unittest.TestCase):
    def test_graded_metrics(self):
        item = {'kind': 'retrieval', 'expected': {'relevant': [
            {'book_version_id': 'v', 'pages': [3], 'grade': 2},
            {'book_version_id': 'v', 'pages': [7], 'grade': 1}]}}
        result = {'status': 'ok', 'hits': [{'book_version_id': 'v', 'pages': [1]},
                                           {'book_version_id': 'v', 'pages': [3, 4]},
                                           {'book_version_id': 'v', 'pages': [3]}]}
        scores = _scores(item, result)
        self.assertEqual((scores['hit@5'], scores['recall@5'], scores['mrr@10']), (1.0, 0.5, 0.5))
        ideal = 2 + 1 / math.log2(3)
        self.assertAlmostEqual(scores['ndcg@10'], (2 / math.log2(3)) / ideal)   # page 3 counted once
        self.assertEqual(_scores({'kind': 'no_answer', 'expected': {'no_answer': True}},
                                 {'status': 'no_match', 'hits': []}), {'no_answer_correct': 1.0})


class EvaluationTests(PipelineTestCase):
    def publish_book(self, pages, school_key):
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
        self.run_pipeline(job)
        gen = self.sql('SELECT generation_id::text FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual(self.publish(gen).status_code, 201)
        return version

    def test_dataset_run_and_sign_off(self):
        manh, tu_binh = self.publish_book(MANH, 'manh_phai'), self.publish_book(TU_BINH, 'tu_binh')
        items = [
            {'key': 'q1', 'kind': 'retrieval', 'input': {'query': 'thực thần sinh tài'},
             'expected': {'relevant': [{'book_version_id': manh, 'pages': [1], 'grade': 2},
                                       {'book_version_id': tu_binh, 'pages': [1]}]}},
            {'key': 'q2', 'kind': 'retrieval', 'input': {'query': 'cách cục thành thì quý'},
             'expected': {'relevant': [{'book_version_id': tu_binh, 'pages': [2], 'grade': 2}]},
             'split': 'test'},
            {'key': 'q3', 'kind': 'no_answer', 'input': {'query': 'xyzzy qwerty'},
             'expected': {'no_answer': True}}]
        created = self.c.post('/api/v1/evaluation-datasets', json={
            'name': 'seed', 'version': '1', 'items': items})
        self.assertEqual(created.status_code, 201, created.text)
        dataset = created.json()['data']
        self.assertEqual((dataset['state'], dataset['items'], dataset['split_manifest']),
                         ('draft', 3, {'dev': 2, 'test': 1, 'holdout': 0}))
        self.assertEqual(self.c.post('/api/v1/evaluation-datasets', json={
            'name': 'seed', 'version': '1', 'items': items}).status_code, 409)

        run = self.c.post('/api/v1/evaluation-runs', json={'dataset_id': dataset['id']})
        self.assertEqual(run.status_code, 201, run.text)
        data = run.json()['data']
        self.assertEqual((data['status'], data['metrics']['items']), ('completed', 3))
        self.assertEqual((data['metrics']['hit@5'], data['metrics']['recall@10'],
                          data['metrics']['no_answer_correct']), (1.0, 1.0, 1.0))
        self.assertEqual([r['status'] for r in data['results']], ['passed'] * 3)
        test_only = self.c.post('/api/v1/evaluation-runs', json={
            'dataset_id': dataset['id'], 'split': 'test'}).json()['data']
        self.assertEqual([r['key'] for r in test_only['results']], ['q2'])
        self.assertEqual(self.c.get(f"/api/v1/evaluation-runs/{data['id']}").json()['data']
                         ['metrics'], data['metrics'])

        approved = self.c.post(f"/api/v1/evaluation-datasets/{dataset['id']}/approve")
        self.assertEqual(approved.json()['data']['state'], 'approved')
        signed = self.c.get(f"/api/v1/evaluation-datasets/{dataset['id']}/items").json()['data']
        self.assertTrue(all(i['reviewer_id'] for i in signed))
        self.assertEqual(self.c.post(f"/api/v1/evaluation-datasets/{dataset['id']}/approve")
                         .status_code, 409)
        reader, _ = self.client('reader')
        self.assertEqual(reader.get('/api/v1/evaluation-datasets').status_code, 403)


if __name__ == '__main__':
    unittest.main()
