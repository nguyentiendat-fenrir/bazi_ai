"""Rulesets, analyses, staleness and re-evaluation (T031-T034)."""
import unittest
import uuid

from tests.integration.env import PipelineTestCase

BIRTH = {'local_datetime': '1990-08-17T06:45', 'timezone': 'Asia/Ho_Chi_Minh',
         'sex_for_luck': 'male'}            # a wood day master
WOOD = {'op': 'eq', 'left': {'fact': 'pillars.day.stem_element'}, 'right': {'literal': 'wood'}}


class RulesetTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner, _ = cls.client('reader')
        cls.stranger, _ = cls.client('reader')

    def setUp(self):
        version, _ = self.ready()
        page = next(p for p in self.c.get(f'/api/v1/book-versions/{version}/pages').json()['data']
                    if p['physical_page_number'] == 1)
        revision = self.c.get(f"/api/v1/page-revisions/{page['revision_id']}").json()['data']
        block = next(b for b in revision['blocks'] if b['kind'] == 'paragraph')
        self.evidence = self.c.post('/api/v1/evidence', json={
            'page_revision_id': revision['id'], 'start_offset': block['start_offset'],
            'end_offset': block['end_offset']}).json()['data']['id']
        self.school = next(s for s in self.c.get('/api/v1/schools').json()['data']
                           if s['key'] == 'manh_phai')

    def review(self, kind, entity_id, decision='approve', base=1):
        return self.c.post('/api/v1/reviews', headers={'Idempotency-Key': uuid.uuid4().hex},
                           json={'entity_kind': kind, 'entity_id': entity_id,
                                 'decision': decision, 'base_revision': base,
                                 'reason': 'đã đối chiếu nguồn'})

    def method(self) -> tuple[str, str]:
        key = f'm_{uuid.uuid4().hex[:8]}'
        method = self.c.post('/api/v1/methods', json={
            'school_id': self.school['id'], 'key': key, 'description': 'Phép thử'}).json()['data']
        self.assertEqual(self.review('method', method['id']).json()['data']['state'], 'approved')
        return key, method['id']

    def approved_rule(self, method_key, claim, value, when=WOOD, requires=()) -> dict:
        document = {'$schema_version': 'bazi-rule/1', 'rule_key': f'test.r{uuid.uuid4().hex[:8]}',
                    'school_id': 'manh_phai', 'method_id': method_key,
                    'fact_schema_version': 'chart-facts/1', 'when': when,
                    'requires': list(requires), 'evidence_ids': [self.evidence],
                    'emits': [{'claim_key': claim, 'value': value, 'kind': 'structural'}],
                    'explanation_template': 'Điều kiện thử nghiệm.'}
        rule = self.c.post('/api/v1/rules', json={'dsl': document}).json()['data']
        fired = {'pillars': {'day': {'stem_element': 'wood'}}}
        self.c.post(f"/api/v1/rules/{rule['id']}/validate", json={'fixtures': [
            {'name': 'fires', 'facts': fired, 'fired_rules': list(requires), 'expect': 'fired'},
            {'name': 'misses', 'facts': {'pillars': {'day': {'stem_element': 'fire'}}},
             'expect': 'not_matched'},
            {'name': 'unknown', 'facts': {'pillars': {'day': None}}, 'expect': 'pending'}]})
        approved = self.review('rule', rule['id'])
        self.assertEqual(approved.status_code, 200, approved.text)
        return rule

    def chart(self) -> str:
        made = self.owner.post('/api/v1/charts', json={'birth_input': BIRTH})
        self.assertEqual(made.status_code, 201, made.text)
        self.assertEqual(made.json()['data']['facts']['pillars']['day']['stem_element'], 'wood')
        return made.json()['data']['id']

    def build(self, method_id, version, ids=None):
        body = {'school_id': self.school['id'], 'method_id': method_id, 'version': version}
        if ids is not None:
            body['rule_revision_ids'] = ids
        return self.c.post('/api/v1/rulesets', json=body)

    def test_snapshot_activation_analysis_staleness_and_reevaluation(self):
        key, method_id = self.method()
        base = self.approved_rule(key, 'test.day', 'wood')
        child = self.approved_rule(key, 'test.child', 'yes', requires=[base['id']])
        rival = self.approved_rule(key, 'test.day', 'not-wood')

        missing = self.build(method_id, 'v0', [child['id']])
        self.assertEqual((missing.status_code, missing.json()['code']), (409, 'DEPENDENCY_MISSING'))
        built = self.build(method_id, 'v1')
        self.assertEqual(built.status_code, 201, built.text)
        v1 = built.json()['data']
        self.assertEqual((v1['state'], v1['members_count']), ('building', 3))
        order = [m['revision_id'] for m in v1['members']]
        self.assertLess(order.index(base['id']), order.index(child['id']))
        self.assertRegex(v1['manifest_hash'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.build(method_id, 'v1').status_code, 409)      # version taken

        chart = self.chart()
        none = self.owner.post(f'/api/v1/charts/{chart}/analyses', json={
            'school_id': self.school['id'], 'method_id': method_id})
        self.assertEqual((none.status_code, none.json()['code']), (409, 'NO_ACTIVE_RULESET'))
        self.assertEqual(self.owner.post(f"/api/v1/rulesets/{v1['id']}/activate",
                                         json={'expected_current_id': None}).status_code, 403)
        active = self.c.post(f"/api/v1/rulesets/{v1['id']}/activate",
                             json={'expected_current_id': None})
        self.assertEqual((active.status_code, active.json()['data']['state']), (200, 'published'))

        made = self.owner.post(f'/api/v1/charts/{chart}/analyses', json={
            'school_id': self.school['id'], 'method_id': method_id, 'as_of': '2026-06-01'})
        self.assertEqual(made.status_code, 202, made.text)
        analysis = made.json()['data']
        answer = analysis['answer']
        self.assertEqual((analysis['status'], answer['status'], answer['counters']['fired']),
                         ('completed', 'complete', 3))
        self.assertEqual([c['claim_key'] for c in answer['conflicts']], ['test.day'])
        trace = self.owner.get(f"/api/v1/analyses/{analysis['id']}/trace").json()['data']
        self.assertEqual({t['revision_id']: t['status'] for t in trace},
                         {base['id']: 'conflict', child['id']: 'true', rival['id']: 'conflict'})
        self.assertEqual(trace[0]['detail']['reads'], {'pillars.day.stem_element': 'wood'})
        self.assertEqual(self.stranger.get(f"/api/v1/analyses/{analysis['id']}").status_code, 404)

        # A newer ruleset retires v1 and makes its analyses stale; CAS refuses a stale view.
        v2 = self.build(method_id, 'v2', [base['id'], child['id']]).json()['data']
        raced = self.c.post(f"/api/v1/rulesets/{v2['id']}/activate",
                            json={'expected_current_id': None})
        self.assertEqual((raced.status_code, raced.json()['code']), (409, 'ACTIVE_CHANGED'))
        swapped = self.c.post(f"/api/v1/rulesets/{v2['id']}/activate",
                              json={'expected_current_id': v1['id']}).json()['data']
        self.assertEqual(swapped['analyses_stale'], 1)
        old = self.owner.get(f"/api/v1/analyses/{analysis['id']}").json()['data']
        self.assertEqual((old['status'], old['stale_reason']), ('stale', 'ruleset_superseded'))
        again = self.owner.post(f"/api/v1/analyses/{analysis['id']}/reevaluate")
        self.assertEqual(again.status_code, 201, again.text)
        diff = again.json()['data']['diff']
        self.assertEqual((diff['removed'], diff['added'], diff['unchanged']),
                         ([{'claim_key': 'test.day', 'value': 'not-wood'}], [], 2))
        self.assertEqual(again.json()['data']['analysis']['answer']['conflicts'], [])

        # Revoking a member rule: analyses go stale and the ruleset cannot be used any more.
        fresh = again.json()['data']['analysis']['id']
        revoked = self.review('rule', child['id'], 'revoke')
        self.assertEqual(revoked.json()['data']['state'], 'revoked')
        self.assertEqual(self.owner.get(f'/api/v1/analyses/{fresh}').json()['data']['status'],
                         'stale')
        refused = self.owner.post(f'/api/v1/charts/{chart}/analyses', json={
            'school_id': self.school['id'], 'method_id': method_id})
        self.assertEqual((refused.status_code, refused.json()['code']),
                         (409, 'RULESET_HAS_REVOKED_RULE'))
        history = self.owner.get(f"/api/v1/analyses/{analysis['id']}/trace").json()['data']
        self.assertEqual({t['revision_id']: t['rule_state'] for t in history}[child['id']],
                         'revoked')

    def test_dependencies_stay_inside_one_school_and_method(self):
        key, _ = self.method()
        other_key, _ = self.method()
        base = self.approved_rule(key, 'test.base', 'wood')
        document = {'$schema_version': 'bazi-rule/1', 'rule_key': f'test.x{uuid.uuid4().hex[:8]}',
                    'school_id': 'manh_phai', 'method_id': other_key,
                    'fact_schema_version': 'chart-facts/1', 'when': WOOD,
                    'requires': [base['id']], 'evidence_ids': [self.evidence],
                    'emits': [{'claim_key': 'test.x', 'value': 1, 'kind': 'structural'}],
                    'explanation_template': 'Phụ thuộc khác phương pháp.'}
        rule = self.c.post('/api/v1/rules', json={'dsl': document}).json()['data']
        blocked = self.review('rule', rule['id'])
        self.assertEqual(blocked.json()['code'], 'APPROVAL_BLOCKED')
        self.assertIn('another school or method', blocked.json()['detail'])


if __name__ == '__main__':
    unittest.main()
