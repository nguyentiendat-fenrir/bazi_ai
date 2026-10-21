"""The "bazi-rag" MCP server through the API's HTTP route, with a fake library and model."""
from functools import cached_property
import unittest
import warnings

from backend.app.core.config import ConfigError, load_settings
from backend.app.knowledge.glossary import read
from backend.app.main import create_app
from backend.app.mcpserver.backend import Unavailable
from backend.app.answering.glossary_index import GlossaryIndex
from tests.unit.test_answering import FakeModel, Library, Q13, cite_all, honest_judge

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

TOKEN = 'mcp-test-token-0123456789-abcdefghijkl'
HEADERS = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
           'Authorization': f'Bearer {TOKEN}'}


class FakeBackend:
    def __init__(self, library=None, model=None, broken=False):
        self.library, self._model, self.broken = library or Library(), model, broken
        self.rag = object()

    def retriever(self):
        if self.broken:
            raise Unavailable('the MCP account x@example.test does not exist or is disabled')
        return self.library

    def model(self):
        return self._model or FakeModel(judge=honest_judge, synthesize=cite_all,
                                        rewrite={'queries': ['nguyệt lệnh']})

    @cached_property
    def concepts(self):
        return read()['concepts']

    @cached_property
    def glossary(self):
        return GlossaryIndex(self.concepts)


def settings(**extra):
    base = {'mcp_token': TOKEN, 'mcp_user_email': 'mcp@example.test', 'rag_load_models': False}
    return load_settings(_env_file=None, **{**base, **extra})


class McpHttpTests(unittest.TestCase):
    def client(self, backend=None, **extra):
        app = create_app(settings(**extra), readiness_checks=[], mcp_backend=backend or FakeBackend())
        return TestClient(app)

    def rpc(self, c, method, params=None, headers=HEADERS, n=1):
        return c.post('/api/v1/mcp/', headers=headers,
                      json={'jsonrpc': '2.0', 'id': n, 'method': method, 'params': params or {}})

    def call(self, c, name, arguments):
        response = self.rpc(c, 'tools/call', {'name': name, 'arguments': arguments})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['result']

    def test_token_is_required(self):
        with self.client() as c:
            self.assertEqual(self.rpc(c, 'tools/list', headers={**HEADERS, 'Authorization': ''}).status_code, 401)
            wrong = self.rpc(c, 'tools/list', headers={**HEADERS, 'Authorization': 'Bearer nope'})
            self.assertEqual((wrong.status_code, wrong.headers['www-authenticate']), (401, 'Bearer'))

    def test_off_unless_configured(self):
        app = create_app(load_settings(_env_file=None, rag_load_models=False), readiness_checks=[])
        with TestClient(app) as c:
            self.assertEqual(self.rpc(c, 'tools/list').status_code, 404)

    def test_settings_reject_a_weak_or_unowned_token(self):
        with self.assertRaises(ConfigError):
            settings(mcp_token='short')
        with self.assertRaises(ConfigError):
            settings(mcp_user_email=None)
        self.assertTrue(settings().mcp_enabled)
        self.assertIn(TOKEN, settings().secret_values())          # redacted from logs

    def test_initialize_and_list_read_only_tools(self):
        with self.client() as c:
            init = self.rpc(c, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                              'clientInfo': {'name': 'test', 'version': '1'}})
            self.assertEqual(init.status_code, 200, init.text)
            self.assertEqual(init.json()['result']['serverInfo']['name'], 'bazi-rag')
            tools = {t['name']: t for t in self.rpc(c, 'tools/list', n=2).json()['result']['tools']}
        self.assertEqual(set(tools), {'search_books', 'answer_question', 'chart_facts', 'lookup_terms'})
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tools.values()))
        self.assertEqual(tools['search_books']['inputSchema']['properties']['school']['anyOf'][0]['enum'],
                         ['tu_binh', 'manh_phai'])

    def test_search_books_filters_by_school(self):
        with self.client() as c:
            out = self.call(c, 'search_books', {'query': 'mộ xung khố', 'school': 'manh_phai'})
        passages = out['structuredContent']['passages']
        self.assertTrue(passages)
        self.assertTrue(all(p['school'] == 'manh_phai' for p in passages))
        self.assertTrue(any('Mộ bị xung' in p['text'] for p in passages))

    def test_answer_question_runs_the_harness(self):
        with self.client() as c:
            out = self.call(c, 'answer_question',
                            {'question': 'Theo Tử Bình Chân Thuyên, dụng thần tìm ở đâu?'})['structuredContent']
            traced = self.call(c, 'answer_question', {'question': 'Dụng thần tìm ở đâu?',
                                                      'include_trace': True})['structuredContent']
        self.assertEqual(out['status'], 'ok')
        self.assertIn('[P1]', out['answer'])
        self.assertNotIn('trace', out)
        self.assertEqual(set(out['needs'][0]), {'id', 'kind', 'school', 'text', 'status'})
        self.assertTrue(traced['trace'])

    def test_risky_question_is_refused_without_the_model(self):
        model = FakeModel()                                         # any call would fail the test
        with self.client(FakeBackend(model=model)) as c:
            out = self.call(c, 'answer_question', {'question': 'Năm 2026 người này có chết không?'})
        self.assertEqual((out['structuredContent']['status'], model.calls), ('refused', []))

    def test_chart_facts_and_terms(self):
        with self.client() as c:
            facts = self.call(c, 'chart_facts', {'text': Q13})['structuredContent']
            none = self.call(c, 'chart_facts', {'text': 'không có lá số'})['structuredContent']
            terms = self.call(c, 'lookup_terms', {'text': 'Đây có phải Tòng Sát cách không?'})['structuredContent']
            mp = self.call(c, 'lookup_terms', {'text': 'Thể dụng', 'school': 'manh_phai'})['structuredContent']
        self.assertTrue(facts['found'])
        self.assertIn('Kình Dương: Tý — ngày, giờ', facts['text'])
        self.assertEqual(facts['pillars']['day'], ['ren', 'zi'])
        self.assertEqual(len(facts['luck']), 7)
        self.assertFalse(none['found'])
        self.assertEqual(terms['terms'][0]['label'], 'Tòng Sát cách')
        self.assertTrue(mp['terms'])
        self.assertTrue(all(t['school_key'] in ('manh_phai', 'tu_tru') for t in mp['terms']))
        source = terms['terms'][0]['sources'][0]                     # no library: book + page only
        self.assertEqual(source['matched'], 'not_found')
        self.assertTrue(source['title'] and source['anchor'])
        self.assertTrue(source['link'].startswith('/api/v1/sources/open?book='))

    def test_unavailable_backend_is_a_tool_error_not_a_crash(self):
        with self.client(FakeBackend(broken=True)) as c:
            out = self.call(c, 'search_books', {'query': 'dụng thần'})
        self.assertTrue(out['isError'])
        self.assertIn('disabled', out['content'][0]['text'])

    def test_invalid_arguments_are_rejected(self):
        with self.client() as c:
            out = self.call(c, 'search_books', {'query': 'x', 'school': 'tu_vi'})
        self.assertTrue(out['isError'])


class McpStdioTests(unittest.TestCase):
    def test_stdio_server_speaks_mcp_to_the_official_client(self):
        """What Claude Code/Desktop does: spawn the process, initialize, list, call."""
        import os
        from pathlib import Path
        import sys

        import anyio
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        root = Path(__file__).resolve().parents[2]
        params = StdioServerParameters(
            command=sys.executable, args=['-m', 'backend.app.mcpserver'], cwd=str(root),
            env={**os.environ, 'MCP_USER_EMAIL': 'mcp@example.test', 'RAG_LOAD_MODELS': 'false',
                 'PYTHONIOENCODING': 'utf-8'})

        async def go():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    info = await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool('chart_facts', {'text': Q13})
                    return info, tools, result
        info, tools, result = anyio.run(go)
        self.assertEqual(info.serverInfo.name, 'bazi-rag')
        self.assertEqual({t.name for t in tools.tools},
                         {'search_books', 'answer_question', 'chart_facts', 'lookup_terms'})
        self.assertFalse(result.isError)
        self.assertIn('B1 Nhật chủ: Nhâm', result.structuredContent['text'])


if __name__ == '__main__':
    unittest.main()
