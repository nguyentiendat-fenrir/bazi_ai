"""Reranker adapters, their fallbacks and the packed evidence bundle (T036)."""
import json
import unittest
import uuid

import httpx

from tests.fixtures.pdf_factory import PdfBuilder
from tests.integration.db import sha
from tests.integration.env import BLACK, PipelineTestCase
from tests.integration.test_search import MANH, TU_BINH


class RerankTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        test = cls('test_adapters_fallbacks_and_bundle')
        cls.versions = [test.publish_book(MANH, 'manh_phai'), test.publish_book(TU_BINH, 'tu_binh')]

    def setUp(self):
        self.app.state.rerank_transport = None
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'reranker'")

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
        self.publish(gen)
        return version

    def reranker(self, provider, **config):
        self.sql("INSERT INTO model_profiles (kind, provider, model_name, model_revision, config,"
                 " profile_hash) VALUES ('reranker', %s, 'rr', '1', %s, %s)",
                 provider, json.dumps(config), sha(uuid.uuid4().hex))

    def search(self, **body):
        response = self.c.post('/api/v1/search', json={'query': 'thực thần sinh tài', **body})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def test_adapters_fallbacks_and_bundle(self):
        fused = self.search(rerank=False)
        order = [h['chunk_id'] for h in fused['hits']]
        self.assertEqual(self.search()['degraded'], ['reranker_not_configured'])

        self.reranker('fixture-overlap')
        ranked = self.search()
        self.assertEqual(ranked['degraded'], [])
        scores = [h['rerank_score'] for h in ranked['hits']]
        self.assertEqual(scores, sorted(scores, reverse=True))

        calls = []

        def reverse(request):
            calls.append(json.loads(request.content))
            count = len(calls[-1]['documents'])
            return httpx.Response(200, json={'results': [
                {'index': i, 'relevance_score': float(i)} for i in range(count)]})
        self.setUp()
        self.reranker('openai_compatible', base_url='http://rerank.local/v1', locality='local')
        self.app.state.rerank_transport = httpx.MockTransport(reverse)
        reversed_ = self.search()
        self.assertEqual(calls[0]['query'], 'thực thần sinh tài')
        self.assertEqual([h['chunk_id'] for h in reversed_['hits']], list(reversed(order)))

        self.app.state.rerank_transport = httpx.MockTransport(lambda r: httpx.Response(503))
        failed = self.search()
        self.assertEqual((failed['degraded'], [h['chunk_id'] for h in failed['hits']]),
                         (['reranker_unavailable'], order))

        self.setUp()
        self.reranker('openai_compatible', base_url='https://rerank.example.test/v1')
        calls.clear()
        self.app.state.rerank_transport = httpx.MockTransport(reverse)
        self.assertEqual(self.search()['degraded'], ['reranker_skipped_external'])
        self.assertEqual(calls, [])                      # book text never left the machine

        bundle = self.search(pack=True, rerank=False)['bundle']
        self.assertEqual([g['evidence_id'] for g in bundle['groups']],
                         [f'E{i}' for i in range(1, len(bundle['groups']) + 1)])
        self.assertTrue(bundle['groups'] and bundle['tokens'] <= 6000)
        first = bundle['groups'][0]
        self.assertEqual(first['excerpt'], next(h['text'] for h in fused['hits']
                                                if h['chunk_id'] == first['chunk_ids'][0]))
        self.assertTrue(all(len([g for g in bundle['groups'] if g['book_version_id'] == v]) <= 3
                            for v in self.versions))


if __name__ == '__main__':
    unittest.main()
