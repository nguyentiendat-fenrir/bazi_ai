"""Ontology releases pinned by the corpus, and the downstream impact graph (T024)."""
import unittest
import uuid

from tests.integration.env import PipelineTestCase

FIXTURES = [
    {'name': 'wood', 'facts': {'pillars': {'day': {'stem_element': 'wood'}}}, 'expect': 'fired'},
    {'name': 'fire', 'facts': {'pillars': {'day': {'stem_element': 'fire'}}},
     'expect': 'not_matched'},
    {'name': 'none', 'facts': {'pillars': {'day': None}}, 'expect': 'pending'},
]


class OntologyReleaseTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reader, _ = cls.client('reader')

    def post(self, path, body):
        return self.c.post(path, json=body, headers={'Idempotency-Key': uuid.uuid4().hex})

    def review(self, kind, entity_id, decision='approve', base=1):
        return self.post('/api/v1/reviews', {'entity_kind': kind, 'entity_id': entity_id,
                                             'decision': decision, 'base_revision': base,
                                             'reason': 'đã đối chiếu'})

    def school(self, key):
        return next(s for s in self.c.get('/api/v1/schools').json()['data'] if s['key'] == key)

    def test_publish_pins_a_new_corpus_release_without_reprocessing(self):
        _, gen = self.ready()
        self.assertEqual(self.publish(gen).status_code, 201)
        before = self.active()
        releases = self.reader.get('/api/v1/ontology-releases').json()['data']
        seed = next(r for r in releases if r['version'] == 'seed-1')
        self.assertEqual((seed['state'], seed['concepts'], seed['terms'],
                          seed['pinned_by_active_corpus']), ('published', 27, 54, True))

        manh = self.school('manh_phai')
        tag = uuid.uuid4().hex[:6]
        concept = self.c.post('/api/v1/concepts', json={
            'school_id': manh['id'], 'canonical_key': f'to_cong_{tag}', 'label': 'Tố công',
            'han': '做功'}).json()['data']
        alias = self.c.post('/api/v1/terms', json={'concept_id': concept['id'], 'form': 'Tác công',
                                                   'alias_kind': 'same_concept'}).json()['data']
        self.c.post('/api/v1/concepts', json={'school_id': manh['id'],
                                              'canonical_key': f'nhap_{tag}', 'label': 'Bản nháp'})
        self.review('concept', concept['id'])
        self.review('term', alias['id'])
        diff = self.c.get('/api/v1/ontology-releases/preview').json()['data']
        self.assertEqual((diff['changed'], diff['concepts']['added']),
                         (True, [f'manh_phai.to_cong_{tag}@1']))
        self.assertEqual(sorted(t.split(': ')[1] for t in diff['terms']['added']),
                         ['Tác công (vi, same_concept)', 'Tố công (vi, canonical)'])

        published = self.post('/api/v1/ontology-releases', {})
        self.assertEqual(published.status_code, 201, published.text)
        data = published.json()['data']
        self.assertEqual((data['release']['state'], data['release']['concepts'],
                          data['release']['terms']), ('published', 28, 56))
        self.assertTrue(data['release']['pinned_by_active_corpus'])
        self.assertEqual(self.active(), data['corpus_release_id'])
        self.assertEqual(self.members(data['corpus_release_id']), self.members(before))
        pinned = self.sql('SELECT ontology_release_id::text FROM corpus_releases WHERE id = %s',
                          data['corpus_release_id'])[0][0]
        self.assertEqual(pinned, data['release']['id'])
        states = {r['version']: r['state'] for r in
                  self.c.get('/api/v1/ontology-releases').json()['data']}
        self.assertEqual(states['seed-1'], 'retired')
        again = self.post('/api/v1/ontology-releases', {})
        self.assertEqual((again.status_code, again.json()['code']), (409, 'NO_CHANGE'))

    def test_impact_graph_and_revocation_marks_answers_stale(self):
        version, _ = self.ready()
        page = next(p for p in self.c.get(f'/api/v1/book-versions/{version}/pages')
                    .json()['data'] if p['physical_page_number'] == 1)
        revision = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}").json()['data']
        block = next(b for b in revision['blocks'] if b['kind'] == 'paragraph')
        evidence = self.c.post('/api/v1/evidence', json={
            'page_revision_id': revision['id'], 'start_offset': block['start_offset'],
            'end_offset': block['end_offset']}).json()['data']['id']
        manh = self.school('manh_phai')
        assertion = self.c.post('/api/v1/assertions', json={
            'school_id': manh['id'], 'statement': 'Nhật can Mộc thì thể là Mộc.',
            'origin': 'source_explicit', 'evidence_ids': [evidence]}).json()['data']
        self.review('assertion', assertion['id'])
        method_key = f'm_{uuid.uuid4().hex[:8]}'
        method = self.c.post('/api/v1/methods', json={'school_id': manh['id'], 'key': method_key,
                                                      'description': 'Phép thử'}).json()['data']
        self.review('method', method['id'])
        document = {'$schema_version': 'bazi-rule/1', 'rule_key': f'test.{uuid.uuid4().hex[:8]}',
                    'school_id': 'manh_phai', 'method_id': method_key,
                    'fact_schema_version': 'chart-facts/1',
                    'when': {'op': 'eq', 'left': {'fact': 'pillars.day.stem_element'},
                             'right': {'literal': 'wood'}},
                    'requires': [], 'evidence_ids': [evidence],
                    'emits': [{'claim_key': 'test.wood', 'value': True, 'kind': 'structural'}],
                    'explanation_template': 'Mộc.'}
        rule = self.c.post('/api/v1/rules', json={'dsl': document,
                                                  'assertion_id': assertion['id']}).json()['data']
        self.c.post(f"/api/v1/rules/{rule['id']}/validate", json={'fixtures': FIXTURES})
        self.assertEqual(self.review('rule', rule['id']).json()['data']['state'], 'approved')
        child_doc = {**document, 'rule_key': f'test.{uuid.uuid4().hex[:8]}',
                     'requires': [rule['id']]}
        child = self.c.post('/api/v1/rules', json={'dsl': child_doc}).json()['data']

        graph = self.c.get('/api/v1/knowledge/impact', params={
            'entity_kind': 'page_revision', 'entity_id': revision['id']}).json()['data']
        self.assertEqual((graph['counts']['evidence'], graph['counts']['assertion'],
                          graph['counts']['rule']), (1, 1, 2))
        self.assertEqual(sorted(graph['ids']['rule']), sorted([rule['id'], child['id']]))
        from_rule = self.c.get('/api/v1/knowledge/impact', params={
            'entity_kind': 'rule', 'entity_id': rule['id']}).json()['data']
        self.assertEqual(from_rule['ids'], {'rule': [child['id']]})

        # An answer that relied on the rule belongs to its owner; reviewers only see a count.
        owner, owner_id = self.client('reader')
        policy = self.sql("INSERT INTO calculation_policies (key, revision, config, manifest_hash)"
                          " VALUES (%s, 1, '{}'::jsonb, bazi_sha256_text('{}'::jsonb::text))"
                          ' RETURNING id', uuid.uuid4().hex)[0][0]
        chart = self.sql("INSERT INTO bazi_charts (owner_id, policy_id, input_snapshot_encrypted,"
                         " facts, facts_hash, engine_manifest, validation_status) VALUES (%s, %s,"
                         " '\\x00', '{}', bazi_sha256_text('{}'::jsonb::text), '{}', 'valid')"
                         ' RETURNING id', owner_id, policy)[0][0]
        analysis = self.sql("INSERT INTO chart_analyses (owner_id, chart_id, answer, status)"
                            " VALUES (%s, %s, '{}', 'completed') RETURNING id", owner_id, chart)[0][0]
        self.sql("INSERT INTO analysis_dependencies (analysis_id, dependency_kind, dependency_id)"
                 " VALUES (%s, 'rule', %s)", analysis, rule['id'])
        counted = self.c.get('/api/v1/knowledge/impact', params={
            'entity_kind': 'evidence', 'entity_id': evidence}).json()['data']
        self.assertEqual(counted['dependents'], {'analyses': 1, 'runs': 0})
        revoked = self.review('rule', rule['id'], 'revoke').json()['data']
        self.assertEqual((revoked['state'], revoked['analyses_stale']), ('revoked', 1))
        self.assertEqual(self.sql('SELECT status, stale_reason LIKE %s FROM chart_analyses'
                                  ' WHERE id = %s', 'rule revoked:%', analysis),
                         [('stale', True)])

        self.assertEqual(self.c.get('/api/v1/knowledge/impact', params={
            'entity_kind': 'users', 'entity_id': str(uuid.uuid4())}).status_code, 422)
        self.assertEqual(self.c.get('/api/v1/knowledge/impact', params={
            'entity_kind': 'rule', 'entity_id': str(uuid.uuid4())}).status_code, 404)
        self.assertEqual(owner.get('/api/v1/knowledge/impact', params={
            'entity_kind': 'rule', 'entity_id': rule['id']}).status_code, 403)


if __name__ == '__main__':
    unittest.main()
