"""The MCP server mounted in the API on the real database: account, RLS, BM25 retrieval."""
import os
from unittest.mock import patch
import warnings

from backend.app.core.config import load_settings
from backend.app.main import create_app
from tests.integration.env import FIELD_KEY, PipelineTestCase

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

TOKEN = 'mcp-integration-token-0123456789-abcdef'
HEADERS = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
           'Authorization': f'Bearer {TOKEN}'}


class McpOnRagTests(PipelineTestCase):
    def mcp_app(self, email):
        with patch.dict(os.environ, {'FIELD_ENCRYPTION_KEY': FIELD_KEY}, clear=True):
            settings = load_settings(_env_file=None, mcp_token=TOKEN, mcp_user_email=email,
                                     rag_load_models=False)
        return create_app(settings, readiness_checks=[], engine=self.engine, store=self.store)

    def call(self, c, name, arguments):
        response = c.post('/api/v1/mcp/', headers=HEADERS, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
            'params': {'name': name, 'arguments': arguments}})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['result']

    def test_tools_search_as_the_configured_account(self):
        self.publish_book([('CHƯƠNG 8: LUẬN DỤNG THẦN', 'Dụng thần của bát tự, chuyên tìm ở nguyệt lệnh.')],
                          'tu_binh')
        self.publish_book([('CHƯƠNG 5: MỘ KHỐ', 'Mộ bị xung gọi là khố, mộ không xung là tử.')],
                          'manh_phai')
        email = self.sql('SELECT email FROM users WHERE id = %s', self.user)[0][0]
        with TestClient(self.mcp_app(email)) as c:
            found = self.call(c, 'search_books', {'query': 'dụng thần nguyệt lệnh', 'school': 'tu_binh'})
            passages = found['structuredContent']['passages']
            self.assertTrue(any('nguyệt lệnh' in p['text'] for p in passages))
            self.assertTrue(all(p['school'] == 'tu_binh' for p in passages))
            # glossary sources are resolved in this library; its books are not in the test database
            terms = self.call(c, 'lookup_terms', {'text': 'Thương quan'})['structuredContent']['terms']
            self.assertEqual(terms[0]['sources'][0]['reason'], 'book not in this library (or not visible to you)')
            # no LLM configured here: the harness tool says so instead of failing the request
            answer = self.call(c, 'answer_question', {'question': 'Dụng thần tìm ở đâu?'})
            self.assertTrue(answer['isError'])
            self.assertIn('LLM is not configured', answer['content'][0]['text'])

        # a reader who was given nothing sees nothing (visibility applies to the MCP account)
        _, reader = self.client('reader')
        reader_email = self.sql('SELECT email FROM users WHERE id = %s', reader)[0][0]
        with TestClient(self.mcp_app(reader_email)) as c:
            empty = self.call(c, 'search_books', {'query': 'dụng thần nguyệt lệnh'})
        self.assertEqual(empty['structuredContent']['passages'], [])

        # a disabled account stops the tools at once
        self.sql('UPDATE users SET enabled = false WHERE id = %s', reader)
        with TestClient(self.mcp_app(reader_email)) as c:
            refused = self.call(c, 'search_books', {'query': 'dụng thần'})
        self.assertTrue(refused['isError'])
        self.assertIn('disabled', refused['content'][0]['text'])
