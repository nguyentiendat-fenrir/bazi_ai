"""SEC01 (docs/13): every owner-scoped route, read from the contract, refuses another user.

Owner A makes one of everything private (birth profile, chart, analysis, conversation, run,
private case). Stranger B then calls every operation whose permission includes ``O`` and
whose path names one of those ids, with a body the contract accepts: the answer must be
404 — not 403, which would confirm the id exists — and nothing of A's may change. A route
added later without an entry here fails the test until it is covered.
"""
import uuid

from backend.app.api.openapi import example
from backend.app.cli import openapi_document
from tests.integration.env import PipelineTestCase
from tests.integration.test_reasoning import BIRTH
from tests.integration import test_rulesets

# Bodies the contract example cannot express (semantic checks run before the owner check).
BODIES = {
    ('patch', '/api/v1/birth-profiles/{profile_id}'): {'label': 'x', 'birth_input': BIRTH},
    ('post', '/api/v1/charts/{chart_id}/analyses'): None,          # filled with school/method
    ('post', '/api/v1/conversations/{conversation_id}/messages'): {'content': 'câu hỏi'},
    ('post', '/api/v1/cases/{case_id}/revisions'): {'base_revision': 1, 'reason': 'thử',
                                                    'narrative': 'khác'},
}


class IdorTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.owner, _ = cls.client('reader')
        cls.stranger, _ = cls.client('reader')

    # The ruleset tests' helpers make an approved rule and an active ruleset.
    setUp = test_rulesets.RulesetTests.setUp
    review = test_rulesets.RulesetTests.review
    method = test_rulesets.RulesetTests.method
    approved_rule = test_rulesets.RulesetTests.approved_rule
    build = test_rulesets.RulesetTests.build

    def resources(self) -> dict:
        key, method_id = self.method()
        self.approved_rule(key, 'test.day', 'wood')
        ruleset = self.build(method_id, 'v1').json()['data']
        self.c.post(f"/api/v1/rulesets/{ruleset['id']}/activate", json={'expected_current_id': None})
        self.analysis_body = {'school_id': self.school['id'], 'method_id': method_id}
        profile = self.owner.post('/api/v1/birth-profiles', json={
            'label': 'riêng', 'birth_input': BIRTH}).json()['data']
        chart = self.owner.post('/api/v1/charts', json={'profile_id': profile['id']}).json()['data']
        analysis = self.owner.post(f"/api/v1/charts/{chart['id']}/analyses",
                                   json=self.analysis_body).json()['data']
        conversation = self.owner.post('/api/v1/conversations', json={
            'context': {'mode': 'research'}}).json()['data']
        run = self.owner.post(f"/api/v1/conversations/{conversation['id']}/messages",
                              json={'content': 'riêng tư'},
                              headers={'Idempotency-Key': uuid.uuid4().hex}).json()['data']['run']
        case = self.owner.post('/api/v1/cases', json={
            'origin': 'user_case', 'school_id': self.school['id'], 'narrative': 'riêng',
            'chart_payload': {'schema': 'book-case/1', 'pillars': {
                'year': {'stem': 'jia', 'branch': 'zi'}, 'month': {'stem': 'bing', 'branch': 'yin'},
                'day': {'stem': 'wu', 'branch': 'chen'}, 'hour': None}}}).json()['data']
        return {'profile_id': profile['id'], 'chart_id': chart['id'], 'analysis_id': analysis['id'],
                'conversation_id': conversation['id'], 'run_id': run['id'], 'case_id': case['id']}

    def test_strangers_get_404_on_every_owner_route(self):
        ids = self.resources()
        document = openapi_document()
        components = document['components']['schemas']
        checked, uncovered = [], []
        for path, operations in document['paths'].items():
            for method, operation in operations.items():
                if 'O' not in operation.get('x-permission', '').split('/'):
                    continue
                params = [p['name'] for p in operation.get('parameters', []) if p['in'] == 'path']
                if not params:
                    continue                    # collections: scoped to the caller by design
                if any(p not in ids for p in params):
                    uncovered.append(f'{method.upper()} {path}')
                    continue
                url = path.format(**ids)
                body = BODIES.get((method, path), ...)
                if body is None:
                    body = self.analysis_body
                elif body is ...:
                    schema = (operation.get('requestBody', {}).get('content', {})
                              .get('application/json', {}).get('schema'))
                    body = example(schema, components) if schema else None
                headers = {p['name']: (uuid.uuid4().hex if p['name'] == 'Idempotency-Key'
                                       else '"1"')
                           for p in operation.get('parameters', []) if p['in'] == 'header'}
                response = self.stranger.request(method.upper(), url, json=body, headers=headers)
                with self.subTest(op=f'{method.upper()} {path}'):
                    self.assertEqual(response.status_code, 404, response.text[:300])
                checked.append(f'{method.upper()} {path}')
        self.assertEqual(uncovered, [])
        self.assertGreaterEqual(len(checked), 20)
        # Nothing of the owner's changed or disappeared.
        for url in ('/api/v1/birth-profiles/{profile_id}', '/api/v1/charts/{chart_id}',
                    '/api/v1/analyses/{analysis_id}', '/api/v1/conversations/{conversation_id}',
                    '/api/v1/runs/{run_id}'):
            with self.subTest(owner=url):
                self.assertEqual(self.owner.get(url.format(**ids)).status_code, 200)
        self.assertEqual(self.owner.get(f"/api/v1/cases/{ids['case_id']}").status_code, 200)
        profile = self.owner.get(f"/api/v1/birth-profiles/{ids['profile_id']}").json()['data']
        self.assertEqual((profile['label'], profile['revision']), ('riêng', 1))
