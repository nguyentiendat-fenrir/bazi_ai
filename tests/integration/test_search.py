"""Hybrid retrieval over the active corpus: scope, filters, expansion, fusion (T035)."""
import unittest
import uuid

from backend.app.retrieval.search import fuse
from tests.fixtures.pdf_factory import PdfBuilder
from tests.integration.env import BLACK, PipelineTestCase

MANH = [('CHƯƠNG 1: TỐ CÔNG', 'Tố công là cách nhật chủ làm việc, thực thần sinh tài mà giàu.'),
        ('CHƯƠNG 2: KHÁCH CHỦ', 'Khách chủ được xét theo nhiều cấp độ khác nhau trong mệnh.')]
TU_BINH = [('CHƯƠNG 1: DỤNG THẦN', 'Dụng thần là yếu tố then chốt, thực thần sinh tài thì phú.'),
           ('CHƯƠNG 2: CÁCH CỤC', 'Cách cục thành thì quý, cách cục phá thì tiện, lẽ thường.')]


class FusionTests(unittest.TestCase):
    def test_reciprocal_rank_fusion(self):
        fused = fuse({'lexical': [('a', 9.0), ('b', 1.0)], 'vector': [('b', 0.1), ('c', 0.2)]})
        self.assertEqual([h['chunk_id'] for h in fused], ['b', 'a', 'c'])
        self.assertAlmostEqual(fused[0]['score'], 1 / 62 + 1 / 61)
        self.assertEqual(fused[0]['ranks'], {'lexical': 2, 'vector': 1})


class SearchTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.empty = cls.c.post('/api/v1/search', json={'query': 'dụng thần'})
        cls.reader, _ = cls.client('reader')

    def book(self, pages) -> bytes:
        builder = PdfBuilder()
        for title, body in pages:
            builder.page(lines=[(title, 72, 720, 18, BLACK), (body, 72, 680, 11, BLACK)])
        return builder.save(self.tmp / f'{uuid.uuid4().hex}.pdf').read_bytes()

    def school(self, key):
        return next(s for s in self.c.get('/api/v1/schools').json()['data'] if s['key'] == key)

    def review(self, kind, entity_id, decision='approve', base=1):
        return self.c.post('/api/v1/reviews', headers={'Idempotency-Key': uuid.uuid4().hex},
                           json={'entity_kind': kind, 'entity_id': entity_id,
                                 'decision': decision, 'base_revision': base,
                                 'reason': 'đã đối chiếu'})

    def published(self, pages, school_key):
        version, _ = self.ready(data=self.book(pages))
        scope = self.c.post(f'/api/v1/book-versions/{version}/school-scopes', json={
            'school_id': self.school(school_key)['id'], 'reason': 'gán trường phái'}).json()['data']
        job = self.review('school_scope', scope['id']).json()['data']['job_id']
        self.assertEqual(self.run_pipeline(job), 'succeeded')
        gen = self.sql('SELECT generation_id::text FROM ingestion_jobs WHERE id = %s', job)[0][0]
        self.assertEqual(self.publish(gen).status_code, 201)
        book = self.sql('SELECT book_id::text FROM book_versions WHERE id = %s', version)[0][0]
        return version, book

    def search(self, client=None, **body):
        response = (client or self.c).post('/api/v1/search', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']

    def test_retrieval_scope_filters_and_expansion(self):
        self.assertEqual(self.empty.json()['data']['status'], 'empty_corpus')
        manh_version, manh_book = self.published(MANH, 'manh_phai')
        tb_version, tb_book = self.published(TU_BINH, 'tu_binh')

        both = self.search(query='thực thần sinh tài')
        self.assertEqual(both['status'], 'ok')
        self.assertEqual({h['book_version_id'] for h in both['hits'][:2]}, {manh_version, tb_version})
        top = both['hits'][0]
        self.assertTrue(top['spans'] and top['pages'] == [1])
        self.assertTrue({'lexical', 'vector'} <= set(top['ranks']), top['ranks'])
        self.assertEqual(both['degraded'], ['reranker_not_configured'])
        folded = self.search(query='thuc than sinh tai')               # no accents typed
        self.assertEqual([h['chunk_id'] for h in folded['hits'][:2]],
                         [h['chunk_id'] for h in both['hits'][:2]])

        manh = self.school('manh_phai')
        scoped = self.search(query='thực thần sinh tài', school_ids=[manh['id']])
        self.assertEqual({(h['book_version_id'], h['school_key']) for h in scoped['hits']},
                         {(manh_version, 'manh_phai')})
        self.assertEqual({h['book_version_id'] for h in self.search(
            query='thực thần', book_ids=[tb_book])['hits']}, {tb_version})
        self.assertEqual(self.search(query='thực thần', book_ids=[str(uuid.uuid4())])['status'],
                         'empty_filters')
        paged = self.search(query='khách chủ cách cục', page_from=2, page_to=2)
        self.assertTrue(paged['hits'] and all(h['pages'] == [2] for h in paged['hits']))
        self.assertEqual(self.search(query='xyzzy qwerty')['status'], 'no_match')

        # An approved alias expands to the other forms of its concept.
        tag = uuid.uuid4().hex[:6]
        concept = self.c.post('/api/v1/concepts', json={
            'school_id': manh['id'], 'canonical_key': f'to_cong_{tag}',
            'label': 'Tố công'}).json()['data']
        alias = self.c.post('/api/v1/terms', json={'concept_id': concept['id'], 'form': 'Tác công',
                                                   'alias_kind': 'same_concept'}).json()['data']
        self.review('concept', concept['id'])
        self.review('term', alias['id'])
        self.assertEqual(self.c.post('/api/v1/ontology-releases', json={},
                                     headers={'Idempotency-Key': uuid.uuid4().hex}).status_code, 201)
        expanded = self.search(query='tác công là gì', school_ids=[manh['id']])
        self.assertEqual(expanded['query']['expansions'],
                         [{'concept': f'to_cong_{tag}', 'school_key': 'manh_phai',
                           'matched': 'Tác công', 'variants': ['Tố công']}])
        self.assertIn('Tố công', expanded['hits'][0]['text'])
        # "Thần" is not the branch "Thân", "đâu" is not "Dậu": no expansion from those.
        self.assertEqual(self.search(query='Dụng Thần ở đâu')['query']['expansions'], [])

        # Readers only reach books shared with them; withdrawn versions leave at once.
        self.sql("INSERT INTO book_access (book_id, role_scope, permission)"
                 " VALUES (%s, 'reader', 'read')", manh_book)
        seen = self.search(client=self.reader, query='thực thần sinh tài')
        self.assertEqual({h['book_version_id'] for h in seen['hits']}, {manh_version})
        self.c.post(f'/api/v1/book-versions/{manh_version}/withdraw',
                    json={'reason': 'thu hồi quyền'})
        after = self.search(query='thực thần sinh tài')
        self.assertEqual({h['book_version_id'] for h in after['hits']}, {tb_version})
        self.assertEqual(self.search(client=self.reader, query='thực thần')['status'],
                         'empty_corpus')


if __name__ == '__main__':
    unittest.main()
