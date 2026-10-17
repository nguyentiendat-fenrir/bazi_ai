"""Evidence bundles and citation resolution: existence, span, support (T037)."""
import unittest
import uuid

from backend.app.retrieval.citations import details, support
from tests.integration.env import PipelineTestCase
from tests.integration.test_search import MANH, TU_BINH


class SupportTests(unittest.TestCase):
    def test_lexical_support_share(self):
        source = 'Tố công là cách nhật chủ làm việc, thực thần sinh tài mà giàu.'
        self.assertEqual(support('thực thần sinh tài thì giàu', source), 1.0)
        self.assertLess(support('ngày mai trời mưa to lắm', source), 0.2)
        self.assertEqual(support('là gì', source), 0.0)          # nothing but function words

    def test_details_are_numbers_urls_and_codes(self):
        self.assertEqual(details('Năm 1984, khóa sk-live-123, xem http://evil.example/a.'),
                         {'1984', 'sk-live-123', 'http://evil.example/a'})
        self.assertEqual(details('Thực thần sinh tài thì giàu.'), set())


class CitationTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        test = cls('test_resolution')
        cls.manh = test.publish_book(MANH, 'manh_phai')
        cls.tu_binh = test.publish_book(TU_BINH, 'tu_binh')

    def bundle(self, client=None):
        response = (client or self.c).post('/api/v1/search', json={
            'query': 'thực thần sinh tài', 'pack': True, 'rerank': False})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['data']['bundle']

    def resolve(self, bundle_id, *claims, client=None):
        return (client or self.c).post('/api/v1/citations/resolve', json={
            'bundle_id': bundle_id, 'claims': list(claims)})

    def test_resolution(self):
        bundle = self.bundle()
        first = bundle['groups'][0]
        claims = [
            {'text': 'Thực thần sinh tài thì giàu', 'evidence_ids': ['E1'],
             'quote': 'thực thần sinh tài'},
            {'text': 'Thực thần sinh tài', 'evidence_ids': ['E1'], 'quote': 'không có trong sách'},
            {'text': 'Thực thần sinh tài', 'evidence_ids': ['E99']},
            {'text': 'Ngày mai trời mưa to lắm', 'evidence_ids': ['E1']},
            # Every word is in the source, the invented key and year are not.
            {'text': 'Thực thần sinh tài thì giàu, khóa sk-live-123 năm 2031',
             'evidence_ids': ['E1']},
        ]
        result = self.resolve(bundle['bundle_id'], *claims)
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()['data']
        self.assertEqual([c['status'] for c in data['claims']],
                         ['supported', 'invalid', 'invalid', 'insufficient_evidence', 'invalid'])
        self.assertEqual([p['code'] for p in data['claims'][4]['problems']], ['UNSUPPORTED_DETAIL'])
        self.assertEqual([p['code'] for c in data['claims'][1:3] for p in c['problems']],
                         ['QUOTE_MISMATCH', 'UNKNOWN_EVIDENCE'])
        citation = data['claims'][0]['citations'][0]
        self.assertEqual((citation['pages'], citation['book_version_id']),
                         (first['pages'], first['book_version_id']))
        self.assertEqual(data['claims'][1]['citations'], [])      # invalid never shows a source
        stored = self.sql('SELECT substr(r.normalized_text, e.start_offset + 1, e.end_offset -'
                          ' e.start_offset) FROM evidence_spans e JOIN page_revisions r'
                          ' ON r.id = e.page_revision_id WHERE e.id = %s',
                          citation['evidence_span_ids'][0])[0][0]
        self.assertIn('thực thần sinh tài', stored)
        again = self.resolve(bundle['bundle_id'], claims[0]).json()['data']
        self.assertEqual(again['claims'][0]['citations'][0]['evidence_span_ids'],
                         citation['evidence_span_ids'])            # spans are reused, not copied

        other, _ = self.client('reviewer')
        self.assertEqual(self.resolve(bundle['bundle_id'], claims[0], client=other).status_code,
                         404)                                      # bundles are owner-private

        withdrawn = first['book_version_id']
        self.c.post(f'/api/v1/book-versions/{withdrawn}/withdraw', json={'reason': 'thu hồi'})
        after = self.resolve(bundle['bundle_id'], claims[0]).json()['data']
        self.assertEqual((after['epoch_changed'], after['claims'][0]['status'],
                          after['claims'][0]['problems'][0]['code']),
                         (True, 'invalid', 'SOURCE_WITHDRAWN'))

        self.sql("UPDATE evidence_bundles SET created_at = now() - interval '2 days',"
                 " expires_at = now() - interval '1 day' WHERE id = %s", bundle['bundle_id'])
        expired = self.resolve(bundle['bundle_id'], claims[0])
        self.assertEqual((expired.status_code, expired.json()['code']), (410, 'BUNDLE_EXPIRED'))


if __name__ == '__main__':
    unittest.main()
