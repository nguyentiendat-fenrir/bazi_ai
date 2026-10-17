"""LLM adapters, budget holds, usage and model profile API (T038)."""
import json
import threading
import time
import unittest
import uuid

import httpx
from pydantic import BaseModel

from backend.app.core.db import transaction
from backend.app.core.errors import AppError
from backend.app.llm import budget, providers, service
from tests.integration.env import PipelineTestCase


class Pong(BaseModel):
    ok: bool


def profile(provider='openai_compatible', **config):
    return providers.LLMProfile(str(uuid.uuid4()), provider, 'gemma-test', 'r1',
                                {'base_url': 'http://llm.local/v1', 'retry_base_seconds': 0,
                                 **config}, None)


def reply(content, prompt=7, completion=3):
    return httpx.Response(200, json={'id': 'req-1', 'choices': [{'message': {'content': content}}],
                                     'usage': {'prompt_tokens': prompt,
                                               'completion_tokens': completion}})


class AdapterTests(unittest.TestCase):
    def test_request_shape_usage_and_json_mode(self):
        seen = []

        def handler(request):
            seen.append(json.loads(request.content))
            return reply('{"ok": true}')
        llm = providers.OpenAICompatibleLLM(profile(json_mode='json_schema'),
                                            httpx.MockTransport(handler))
        result = llm.generate([{'role': 'user', 'content': 'ping'}], 16, schema=Pong)
        self.assertEqual((result.data, result.input_tokens, result.output_tokens, result.request_id),
                         (Pong(ok=True), 7, 3, 'req-1'))
        body = seen[0]
        self.assertEqual((body['model'], body['max_tokens'], body['response_format']['type']),
                         ('gemma-test', 16, 'json_schema'))
        self.assertEqual(body['response_format']['json_schema']['schema']['required'], ['ok'])

    def test_retries_then_success_and_permanent_errors(self):
        answers = iter([httpx.Response(503), httpx.Response(429), reply('OK')])
        llm = providers.OpenAICompatibleLLM(profile(), httpx.MockTransport(lambda r: next(answers)))
        self.assertEqual(llm.generate([{'role': 'user', 'content': 'x'}]).text, 'OK')
        calls = []

        def rejected(request):
            calls.append(1)
            return httpx.Response(400)
        with self.assertRaises(providers.LLMError) as caught:
            providers.OpenAICompatibleLLM(profile(), httpx.MockTransport(rejected)).generate(
                [{'role': 'user', 'content': 'x'}])
        self.assertEqual((caught.exception.code, caught.exception.retryable, len(calls)),
                         ('PROVIDER_REJECTED', False, 1))

        def slow(request):
            raise httpx.ReadTimeout('slow', request=request)
        with self.assertRaises(providers.LLMError) as caught:
            providers.OpenAICompatibleLLM(profile(max_retries=1), httpx.MockTransport(slow)).generate(
                [{'role': 'user', 'content': 'x'}])
        self.assertEqual((caught.exception.code, caught.exception.retryable),
                         ('PROVIDER_TIMEOUT', True))

    def test_one_repair_turn_for_malformed_json(self):
        seen = []
        answers = iter([reply('ok: yes'), reply('{"ok": false}')])

        def handler(request):
            seen.append(json.loads(request.content))
            return next(answers)
        result = providers.OpenAICompatibleLLM(profile(), httpx.MockTransport(handler)).generate(
            [{'role': 'user', 'content': 'x'}], schema=Pong)
        self.assertEqual((result.data, result.repaired, result.attempts, result.input_tokens),
                         (Pong(ok=False), True, 2, 14))
        self.assertIn('not valid JSON', seen[1]['messages'][-1]['content'])
        broken = providers.FixtureLLM(profile('fixture-scripted', replies=['nope', 'still nope']))
        with self.assertRaises(providers.LLMError) as caught:
            broken.generate([{'role': 'user', 'content': 'x'}], schema=Pong)
        self.assertEqual(caught.exception.code, 'SCHEMA_INVALID')
        with self.assertRaises(AppError):
            providers.build(profile('fixture-scripted'), 'production')


class LlmApiTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin, cls.admin_id = cls.client('admin')

    def create(self, **body):
        defaults = {'kind': 'llm', 'provider': 'fixture-scripted', 'model_name': 'mock',
                    'model_revision': uuid.uuid4().hex[:8], 'config': {}}
        return self.admin.post('/api/v1/model-profiles', json={**defaults, **body})

    def principal(self):
        from backend.app.auth.service import Principal
        return Principal(uuid.UUID(self.admin_id), 'admin@example.test', 'admin', uuid.uuid4(), '')

    def test_profiles_test_activate_and_usage(self):
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'llm'")
        listed = self.admin.get('/api/v1/model-profiles', params={'kind': 'llm'}).json()['data']
        self.assertFalse(any(p['active'] for p in listed))
        with self.assertRaises(AppError) as caught:
            service.generate(self.engine, self.principal(), [{'role': 'user', 'content': 'x'}])
        self.assertEqual(caught.exception.code, 'PROVIDER_NOT_CONFIGURED')

        self.assertEqual(self.create(config={'api_key': 'x'}).status_code, 422)
        self.assertEqual(self.create(secret_ref='HOME').status_code, 422)
        self.assertEqual(self.c.post('/api/v1/model-profiles', json={
            'kind': 'llm', 'provider': 'fixture-scripted', 'model_name': 'm',
            'model_revision': 'r'}).status_code, 403)
        created = self.create(config={'replies': ['OK', '{"ok": true}'], 'currency': 'USD',
                                      'price_input_per_1k': 1, 'price_output_per_1k': 2})
        self.assertEqual(created.status_code, 201, created.text)
        llm = created.json()['data']
        self.assertEqual((llm['active'], llm['is_fixture']), (True, True))
        tested = self.admin.post(f"/api/v1/model-profiles/{llm['id']}/test",
                                 json={'check_json': True})
        self.assertEqual(tested.status_code, 200, tested.text)
        self.assertEqual((tested.json()['data']['reply'], tested.json()['data']['json_ok']),
                         ('OK', True))
        own = self.admin.get('/api/v1/usage').json()['data']
        row = next(r for r in own['own'] if r['profile_id'] == llm['id'])
        self.assertEqual(row['requests'], 2)
        self.assertGreater(row['cost'], 0)
        self.assertEqual(next(r for r in own['all'] if r['profile_id'] == llm['id'])['requests'], 2)

        newer = self.create().json()['data']
        mine = lambda: {p['id']: p['active'] for p in self.admin.get(
            '/api/v1/model-profiles', params={'kind': 'llm'}).json()['data']
            if p['id'] in (llm['id'], newer['id'])}
        self.assertEqual(mine(), {llm['id']: False, newer['id']: True})
        self.admin.post(f"/api/v1/model-profiles/{llm['id']}/activate")
        self.assertEqual(mine(), {llm['id']: True, newer['id']: False})

        embedding = self.create(kind='embedding', provider='fixture-hashing', dimension=16)
        self.assertEqual(embedding.status_code, 201, embedding.text)
        emb_id = embedding.json()['data']['id']
        self.assertEqual(self.admin.post(f'/api/v1/model-profiles/{emb_id}/test', json={})
                         .json()['data']['dimension'], 16)
        self.assertEqual(self.admin.post(f'/api/v1/model-profiles/{emb_id}/activate').status_code,
                         422)
        reranker = self.create(kind='reranker', provider='fixture-overlap').json()['data']
        self.assertEqual(self.admin.post(f"/api/v1/model-profiles/{reranker['id']}/test",
                                         json={}).status_code, 200)

    def test_budget_ceiling_holds_under_concurrency(self):
        created = self.create(config={'price_input_per_1k': 1000, 'price_output_per_1k': 1000,
                                      'daily_budget': 30, 'currency': 'USD'}).json()['data']
        self.admin.post(f"/api/v1/model-profiles/{created['id']}/activate")
        with transaction(self.engine, uuid.UUID(self.admin_id)) as conn:
            llm = providers.load(conn, created['id'])
        # Each hold costs (10 + 10) tokens * 1 per token = 20: one fits under 30, two do not.
        results, gate = [], threading.Event()

        def hold(wait):
            try:
                with transaction(self.engine, uuid.UUID(self.admin_id)) as conn:
                    budget.reserve(conn, uuid.UUID(self.admin_id), llm, 10, 10)
                    gate.set()
                    time.sleep(wait)            # still inside the transaction holding the lock
                results.append('held')
            except AppError as exc:
                results.append(exc.code)
        first = threading.Thread(target=hold, args=(0.5,))
        first.start()
        gate.wait(5)
        second = threading.Thread(target=hold, args=(0,))
        second.start()
        first.join()
        second.join()
        self.assertEqual(sorted(results), ['BUDGET_EXCEEDED', 'held'])
        refused = self.admin.post(f"/api/v1/model-profiles/{created['id']}/test", json={})
        self.assertEqual((refused.status_code, refused.json()['code']), (429, 'BUDGET_EXCEEDED'))

    def test_external_models_need_consent_for_book_text(self):
        version, _ = self.ready()
        external = profile()
        local = profile(locality='local')
        with transaction(self.engine, uuid.UUID(self.admin_id)) as conn:
            self.assertFalse(providers.may_send_book_text(conn, external, [version]))
            self.assertTrue(providers.may_send_book_text(conn, local, [version]))


if __name__ == '__main__':
    unittest.main()
