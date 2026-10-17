"""Evidence, assertions, relations and rules: drafts, revisions and approval gates (T022)."""
import unittest
import uuid

from tests.integration.env import PipelineTestCase

FIXTURES = [
    {'name': 'wood', 'facts': {'pillars': {'day': {'stem_element': 'wood'}}}, 'expect': 'fired'},
    {'name': 'fire', 'facts': {'pillars': {'day': {'stem_element': 'fire'}}},
     'expect': 'not_matched'},
    {'name': 'no-day', 'facts': {'pillars': {'day': None}}, 'expect': 'pending'},
]


class RuleReviewTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader, _ = cls.client('reader')

    def setUp(self):
        self.version, self.gen = self.ready()
        page = next(p for p in self.c.get(f'/api/v1/book-versions/{self.version}/pages')
                    .json()['data'] if p['physical_page_number'] == 1)
        self.revision = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}").json()['data']
        self.paragraph = next(b for b in self.revision['blocks'] if b['kind'] == 'paragraph')
        self.manh = next(s for s in self.c.get('/api/v1/schools').json()['data']
                         if s['key'] == 'manh_phai')

    def evidence(self, block=None):
        block = block or self.paragraph
        response = self.c.post('/api/v1/evidence', json={
            'page_revision_id': self.revision['id'], 'start_offset': block['start_offset'],
            'end_offset': block['end_offset']})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['data']

    def review(self, kind, entity_id, decision='approve', base=1):
        return self.c.post('/api/v1/reviews', headers={'Idempotency-Key': uuid.uuid4().hex},
                           json={'entity_kind': kind, 'entity_id': entity_id,
                                 'decision': decision, 'base_revision': base,
                                 'reason': 'đã đối chiếu nguồn'})

    def assertion(self, statement, evidence_ids):
        response = self.c.post('/api/v1/assertions', json={
            'school_id': self.manh['id'], 'statement': statement, 'origin': 'source_explicit',
            'evidence_ids': evidence_ids})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['data']

    def method(self):
        key = f'm_{uuid.uuid4().hex[:8]}'
        method = self.c.post('/api/v1/methods', json={'school_id': self.manh['id'], 'key': key,
                                                      'description': 'Phép xét thử'}).json()['data']
        self.assertEqual(self.review('method', method['id']).json()['data']['state'], 'approved')
        return key

    def document(self, method_key, evidence_ids, rule_key=None):
        return {'$schema_version': 'bazi-rule/1',
                'rule_key': rule_key or f'test.r{uuid.uuid4().hex[:8]}',
                'school_id': 'manh_phai', 'method_id': method_key,
                'fact_schema_version': 'chart-facts/1',
                'when': {'op': 'eq', 'left': {'fact': 'pillars.day.stem_element'},
                         'right': {'literal': 'wood'}},
                'requires': [], 'evidence_ids': evidence_ids,
                'emits': [{'claim_key': 'test.day_element', 'value': 'wood',
                           'kind': 'structural'}],
                'explanation_template': 'Nhật can thuộc Mộc.'}

    def test_evidence_spans_one_block(self):
        evidence = self.evidence()
        self.assertEqual((evidence['quote'], evidence['speaker_layer'],
                          evidence['physical_page_number']),
                         (self.paragraph['text'], self.paragraph['speaker_layer'], 1))
        heading = next(b for b in self.revision['blocks'] if b['kind'] == 'heading')
        across = self.c.post('/api/v1/evidence', json={
            'page_revision_id': self.revision['id'], 'start_offset': heading['start_offset'],
            'end_offset': self.paragraph['end_offset']})
        self.assertEqual(across.status_code, 422)
        self.assertEqual(self.reader.post('/api/v1/evidence', json={
            'page_revision_id': self.revision['id'], 'start_offset': 0,
            'end_offset': 3}).status_code, 403)

    def test_assertions_revisions_relations_and_gates(self):
        evidence = self.evidence()['id']
        first = self.assertion('Thực thần sinh tài thì giàu.', [evidence])
        self.assertEqual((first['state'], first['sources'][0]['quote']),
                         ('draft', self.paragraph['text']))
        url = f"/api/v1/assertions/{first['id']}/revisions"
        second = self.c.post(url, json={'base_revision': 1, 'reason': 'rõ nghĩa',
                                        'statement': 'Thực thần sinh tài thì giàu có.'})
        self.assertEqual((second.status_code, second.json()['data']['revision']), (201, 2))
        self.assertEqual(len(second.json()['data']['sources']), 1)      # sources carried
        self.assertEqual(self.c.post(url, json={'base_revision': 1, 'reason': 'lặp'})
                         .status_code, 412)
        other = self.assertion('Thương quan kiến quan thì họa.', [evidence])
        relation = self.c.post('/api/v1/assertion-relations', json={
            'from_id': other['id'], 'to_id': second.json()['data']['id'],
            'relation': 'qualifies'}).json()['data']
        blocked = self.review('assertion_relation', relation['id'])
        self.assertEqual((blocked.status_code, blocked.json()['code']), (409, 'APPROVAL_BLOCKED'))

        # A cited page that is not accepted blocks approval.
        self.sql("UPDATE page_revisions SET state = 'review_required' WHERE id = %s",
                 self.revision['id'])
        refused = self.review('assertion', other['id'])
        self.assertIn('not accepted', refused.json()['detail'])
        self.sql("UPDATE page_revisions SET state = 'accepted' WHERE id = %s", self.revision['id'])
        for assertion_id, base in ((other['id'], 1), (second.json()['data']['id'], 2)):
            self.assertEqual(self.review('assertion', assertion_id, base=base)
                             .json()['data']['state'], 'approved')
        self.assertEqual(self.review('assertion_relation', relation['id']).json()['data']['state'],
                         'approved')
        # Readers see approved assertions only; candidates' review items close on decision.
        self.assertEqual(self.reader.get(f"/api/v1/assertions/{first['id']}").status_code, 404)
        self.assertEqual(self.reader.get(f"/api/v1/assertions/{other['id']}").status_code, 200)
        candidate = self.assertion('Kiếp tài đoạt tài thì hao tán.', [evidence])
        self.sql("INSERT INTO review_items (entity_kind, entity_id, reason_code, severity)"
                 " VALUES ('assertion', %s, 'CANDIDATE_ASSERTION', 'info')", candidate['id'])
        self.assertEqual(self.review('assertion', candidate['id'], 'reject')
                         .json()['data']['state'], 'rejected')
        self.assertEqual(self.sql("SELECT state FROM review_items WHERE entity_id = %s",
                                  candidate['id']), [('dismissed',)])

    def test_rule_needs_valid_dsl_sources_and_fixtures(self):
        evidence = self.evidence()['id']
        method = self.method()
        invalid = self.document(method, [evidence])
        invalid['when'] = {'op': 'eq', 'left': {'fact': 'pillars.day.stem'},
                           'right': {'fact': 'pillars.day.branch'}}
        bad = self.c.post('/api/v1/rules', json={'dsl': invalid})
        self.assertEqual((bad.status_code, bad.json()['code']), (422, 'RULE_INVALID'))
        self.assertEqual(bad.json()['field_errors'][0]['path'], 'body.dsl.when')

        document = self.document(method, [evidence])
        created = self.c.post('/api/v1/rules', json={'dsl': document})
        self.assertEqual(created.status_code, 201, created.text)
        rule = created.json()['data']
        self.assertEqual((rule['state'], rule['method_key'], len(rule['sources'])),
                         ('draft', method, 1))
        self.assertEqual(self.c.post('/api/v1/rules', json={'dsl': document}).status_code, 409)
        blocked = self.review('rule', rule['id'])
        self.assertEqual(blocked.json()['code'], 'APPROVAL_BLOCKED')
        self.assertIn('fixtures missing', blocked.json()['detail'])

        url = f"/api/v1/rules/{rule['id']}/validate"
        failing = self.c.post(url, json={'fixtures': FIXTURES[:2] + [
            {**FIXTURES[2], 'expect': 'fired'}]}).json()['data']
        self.assertEqual(({r['name']: r['passed'] for r in failing['results']},
                          failing['approvable_fixtures']),
                         ({'wood': True, 'fire': True, 'no-day': False}, False))
        passing = self.c.post(url, json={'fixtures': FIXTURES}).json()['data']
        self.assertEqual((passing['valid'], passing['approvable_fixtures'], passing['problem']),
                         (True, True, None))
        approved = self.review('rule', rule['id'])
        self.assertEqual(approved.json()['data']['state'], 'approved', approved.text)
        frozen = self.c.post(url, json={'fixtures': FIXTURES})
        self.assertEqual(frozen.status_code, 409)
        detail = self.c.get(f"/api/v1/rules/{rule['id']}").json()['data']
        self.assertEqual(([f['name'] for f in detail['fixtures']],
                          [r['decision'] for r in detail['reviews']]),
                         (['fire', 'no-day', 'wood'], ['approve']))

        revised = self.c.post(f"/api/v1/rules/{rule['id']}/revisions", json={
            'base_revision': 1, 'dsl': document, 'reason': 'thêm điều kiện'})
        self.assertEqual((revised.status_code, revised.json()['data']['revision']), (201, 2))
        renamed = self.c.post(f"/api/v1/rules/{rule['id']}/revisions", json={
            'base_revision': 2, 'dsl': {**document, 'rule_key': 'test.other'}, 'reason': 'x x'})
        self.assertEqual(renamed.status_code, 422)
        listed = self.reader.get('/api/v1/rules').json()['data']
        self.assertTrue(all(r['state'] == 'approved' for r in listed))
        self.assertEqual(self.reader.get(f"/api/v1/rules/{revised.json()['data']['id']}")
                         .status_code, 404)

    def test_rule_with_unapproved_method_or_dependency_is_blocked(self):
        evidence = self.evidence()['id']
        key = f'm_{uuid.uuid4().hex[:8]}'
        self.c.post('/api/v1/methods', json={'school_id': self.manh['id'], 'key': key,
                                             'description': 'Chưa duyệt'})
        rule = self.c.post('/api/v1/rules', json={'dsl': self.document(key, [evidence])}).json()
        self.c.post(f"/api/v1/rules/{rule['data']['id']}/validate", json={'fixtures': FIXTURES})
        blocked = self.review('rule', rule['data']['id'])
        self.assertIn('method is not approved', blocked.json()['detail'])
        method = self.method()
        base = self.c.post('/api/v1/rules', json={'dsl': self.document(method, [evidence])})
        dependent = self.document(method, [evidence])
        dependent['requires'] = [base.json()['data']['id']]
        child = self.c.post('/api/v1/rules', json={'dsl': dependent}).json()['data']
        self.assertEqual(child['requires'], [base.json()['data']['id']])
        self.c.post(f"/api/v1/rules/{child['id']}/validate", json={'fixtures': [
            {**FIXTURES[0], 'fired_rules': [base.json()['data']['id']]},
            FIXTURES[1], FIXTURES[2]]})
        self.assertIn('required rule is not approved',
                      self.review('rule', child['id']).json()['detail'])


if __name__ == '__main__':
    unittest.main()
