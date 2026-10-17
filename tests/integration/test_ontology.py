"""Schools, methods, concepts, aliases, reviews and school scopes (T020)."""
import unittest
import uuid

from tests.integration.env import PipelineTestCase


class OntologyTests(PipelineTestCase):
    def school(self, key):
        return next(s for s in self.c.get('/api/v1/schools').json()['data'] if s['key'] == key)

    def review(self, kind, entity_id, decision, base=1, key=None):
        return self.c.post('/api/v1/reviews', headers={'Idempotency-Key': key or uuid.uuid4().hex},
                           json={'entity_kind': kind, 'entity_id': entity_id,
                                 'decision': decision, 'base_revision': base,
                                 'reason': 'đã đối chiếu nguồn'})

    def concept(self, school, key, label, **extra):
        response = self.c.post('/api/v1/concepts', json={'school_id': school, 'canonical_key': key,
                                                          'label': label, **extra})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['data']

    def test_seeded_taxonomy_and_school_rules(self):
        root, manh = self.school('tu_tru'), self.school('manh_phai')
        self.assertEqual(manh['parent_id'], root['id'])
        self.assertEqual(self.c.post('/api/v1/schools', json={'key': 'tu_binh',
                                                              'label': 'x'}).status_code, 409)
        self.assertEqual(self.c.post('/api/v1/schools', json={'key': 'Bad Key',
                                                              'label': 'x'}).status_code, 422)
        reader, _ = self.client('reader')
        self.assertEqual(reader.post('/api/v1/schools', json={'key': 'abc', 'label': 'x'})
                         .status_code, 403)
        created = self.c.post('/api/v1/schools', json={'key': f'phai_{uuid.uuid4().hex[:6]}',
                                                       'label': 'Phái thử', 'parent_id': root['id']})
        self.assertEqual(created.status_code, 201, created.text)
        codes = self.c.get('/api/v1/concepts', params={'school_id': root['id'], 'limit': 200})
        self.assertEqual(len(codes.json()['data']), 27)          # seeded Can/Chi/Ngũ hành

    def test_method_revisions(self):
        manh = self.school('manh_phai')
        key = f'khach_chu_{uuid.uuid4().hex[:6]}'
        first = self.c.post('/api/v1/methods', json={'school_id': manh['id'], 'key': key,
                                                     'description': 'Xét khách chủ theo cấp'})
        self.assertEqual((first.status_code, first.json()['data']['state']), (201, 'draft'))
        again = self.c.post('/api/v1/methods', json={'school_id': manh['id'], 'key': key,
                                                     'description': 'x'})
        self.assertEqual(again.status_code, 409)
        method = first.json()['data']['id']
        url = f'/api/v1/methods/{method}/revisions'
        second = self.c.post(url, json={'base_revision': 1, 'description': 'Bản 2',
                                        'reason': 'bổ sung'})
        self.assertEqual(second.json()['data']['revision'], 2)
        stale = self.c.post(url, json={'base_revision': 1, 'description': 'Bản 3',
                                       'reason': 'bổ sung'})
        self.assertEqual(stale.status_code, 412)
        approved = self.review('method', second.json()['data']['id'], 'approve', base=2)
        self.assertEqual(approved.json()['data']['state'], 'approved')

    def test_concept_lifecycle_aliases_and_search(self):
        manh, tu_binh = self.school('manh_phai'), self.school('tu_binh')
        tag = uuid.uuid4().hex[:6]
        concept = self.concept(manh['id'], f'the_dung_{tag}', 'Thể dụng', han='體用',
                               description='Quan hệ thể và dụng')
        self.assertEqual((concept['state'], sorted(t['alias_kind'] for t in concept['terms'])),
                         ('draft', ['canonical', 'translation_variant']))
        alias = self.c.post('/api/v1/terms', json={'concept_id': concept['id'],
                                                   'form': 'Thể và Dụng',
                                                   'alias_kind': 'same_concept'})
        self.assertEqual(alias.status_code, 201, alias.text)
        self.assertEqual(self.c.post('/api/v1/terms', json={
            'concept_id': concept['id'], 'form': 'Thể và Dụng',
            'alias_kind': 'same_concept'}).status_code, 409)

        wrong = self.review('concept', concept['id'], 'approve', base=2)
        self.assertEqual((wrong.status_code, wrong.json()['code']), (412, 'REVISION_MISMATCH'))
        key = uuid.uuid4().hex
        approved = self.review('concept', concept['id'], 'approve', key=key)
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual((approved.json()['data']['state'],
                          approved.json()['data']['terms_approved']), ('approved', 1))
        self.assertEqual(self.review('concept', concept['id'], 'approve', key=key).json(),
                         approved.json())                       # replayed, not re-applied
        self.assertEqual(self.review('concept', concept['id'], 'reject').json()['code'],
                         'INVALID_TRANSITION')
        self.assertEqual(self.review('term', alias.json()['data']['id'], 'approve')
                         .json()['data']['state'], 'approved')

        # Revision 2 carries aliases; approving it approves only what was approved before.
        url = f"/api/v1/concepts/{concept['id']}/revisions"
        revised = self.c.post(url, json={'base_revision': 1, 'label': 'Thể – Dụng',
                                         'reason': 'thống nhất cách viết'})
        self.assertEqual(revised.status_code, 201, revised.text)
        second = revised.json()['data']
        self.assertEqual((second['revision'], second['state']), (2, 'draft'))
        self.assertEqual(self.c.post(url, json={'base_revision': 1, 'reason': 'lặp lại'})
                         .status_code, 412)
        result = self.review('concept', second['id'], 'approve', base=2).json()['data']
        self.assertEqual(result['terms_approved'], 2)           # new label + carried alias
        states = {t['form']: t['state'] for t in
                  self.c.get(f"/api/v1/concepts/{second['id']}").json()['data']['terms']}
        self.assertEqual(states, {'Thể – Dụng': 'approved', 'Thể và Dụng': 'approved',
                                  '體用': 'draft'})
        detail = self.c.get(f"/api/v1/concepts/{concept['id']}").json()['data']
        self.assertEqual([r['revision'] for r in detail['revisions']], [1, 2])
        self.assertEqual([r['decision'] for r in detail['reviews']], ['approve'])
        self.assertEqual(self.review('concept', concept['id'], 'revoke').json()['data']['state'],
                         'revoked')

        # One written form, two schools: search names each school; a school filter keeps one.
        self.concept(tu_binh['id'], f'dung_than_{tag}', f'Dụng thần {tag}')
        self.concept(manh['id'], f'dung_than_{tag}', f'Dụng thần {tag}')
        hits = self.c.get('/api/v1/terms', params={'q': f'dung than {tag}'}).json()['data']
        self.assertEqual(sorted(h['concept']['school_key'] for h in hits),
                         ['manh_phai', 'tu_binh'])
        scoped = self.c.get('/api/v1/terms', params={'q': f'dung than {tag}',
                                                     'school_id': tu_binh['id']}).json()['data']
        self.assertEqual([h['concept']['school_key'] for h in scoped], ['tu_binh'])
        found = self.c.get('/api/v1/concepts', params={'q': 'the va dung'}).json()['data']
        self.assertIn(f'the_dung_{tag}', [c['canonical_key'] for c in found])
        self.assertEqual(next(c for c in found if c['canonical_key'] == f'the_dung_{tag}')
                         ['revision'], 2)                         # latest revision only

    def test_school_scopes_classify_chunks_per_generation(self):
        manh, tu_binh = self.school('manh_phai'), self.school('tu_binh')
        version, gen = self.ready(pages=3)
        url = f'/api/v1/book-versions/{version}/school-scopes'
        whole = self.c.post(url, json={'school_id': manh['id'], 'reason': 'sách Manh phái'})
        self.assertEqual(whole.status_code, 201, whole.text)
        self.assertEqual(self.c.post(url, json={'school_id': manh['id'], 'first_page': 2,
                                                'reason': 'thiếu trang cuối'}).status_code, 422)
        approved = self.review('school_scope', whole.json()['data']['id'], 'approve')
        result = approved.json()['data']
        self.assertEqual((result['state'], result['rebuild']), ('approved', 'queued'))
        self.assertEqual(self.run_pipeline(result['job_id']), 'succeeded')
        first = self.sql('SELECT generation_id FROM ingestion_jobs WHERE id = %s',
                         result['job_id'])[0][0]
        schools = self.sql("SELECT DISTINCT s.key FROM chunk_classifications cc JOIN schools s"
                           " ON s.id = cc.school_id WHERE cc.generation_id = %s"
                           " AND cc.status = 'reviewed'", first)
        self.assertEqual(schools, [('manh_phai',)])
        self.assertEqual(self.sql('SELECT count(*) FROM chunk_classifications'
                                  ' WHERE generation_id = %s AND school_id IS NOT NULL', gen),
                         [(0,)])                                # the old generation is untouched
        self.assertEqual(self.publish(str(first)).status_code, 201)

        appendix = self.c.post(url, json={'school_id': tu_binh['id'], 'first_page': 3,
                                          'last_page': 3, 'reason': 'phụ lục trích Tử Bình'})
        self.assertEqual(appendix.status_code, 201, appendix.text)
        overlap = self.c.post(url, json={'school_id': manh['id'], 'first_page': 2,
                                         'last_page': 3, 'reason': 'chồng lấn'})
        self.assertEqual(overlap.status_code, 409)
        result = self.review('school_scope', appendix.json()['data']['id'], 'approve').json()
        self.assertEqual(self.run_pipeline(result['data']['job_id']), 'succeeded')
        second = self.sql('SELECT generation_id FROM ingestion_jobs WHERE id = %s',
                          result['data']['job_id'])[0][0]
        by_page = dict(self.sql(
            'SELECT p.physical_page_number, s.key FROM chunk_classifications cc'
            ' JOIN schools s ON s.id = cc.school_id JOIN chunk_spans sp ON sp.chunk_id = cc.chunk_id'
            ' JOIN page_revisions r ON r.id = sp.page_revision_id JOIN pages p ON p.id = r.page_id'
            ' WHERE cc.generation_id = %s', second))
        self.assertEqual(by_page, {1: 'manh_phai', 2: 'manh_phai', 3: 'tu_binh'})
        published = self.sql('SELECT DISTINCT s.key FROM chunk_classifications cc JOIN schools s'
                             ' ON s.id = cc.school_id WHERE cc.generation_id = %s', first)
        self.assertEqual(published, [('manh_phai',)])            # published snapshot frozen
        listed = self.c.get(url).json()['data']
        self.assertEqual([(s['first_page'], s['state']) for s in listed],
                         [(None, 'approved'), (3, 'approved')])


if __name__ == '__main__':
    unittest.main()
