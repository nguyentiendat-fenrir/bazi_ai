"""Definition curation end to end on a published book, with a fake OpenAI-compatible model."""
import json
import os
from unittest.mock import patch
import uuid

import httpx

from backend.app.auth.service import Principal
from backend.app.core.config import load_settings
from backend.app.knowledge import curation
from tests.integration.env import FIELD_KEY, PipelineTestCase

QUOTE = 'Chủ và khách có tính tương đối theo cấp độ xét.'
PAGES = [('CHƯƠNG 1: KHÁCH CHỦ',
          'Khách chủ là cách phân định phần thuộc về chủ thể đang xét và phần ở bên ngoài chủ thể đó. '
          + QUOTE + ' Phải xác định cấp độ trước khi phân loại.')]


class FakeGemini:
    """Answers by step (recognised from the system prompt); records request bodies."""

    def __init__(self, verdict='pass', reject_schema=False):
        self.bodies, self.verdict, self.reject_schema = [], verdict, reject_schema

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        if self.reject_schema and 'response_format' in body:
            return httpx.Response(400, json={'error': {'message': 'Unknown name "$defs"'}})
        system = body['messages'][0]['content']
        if 'liệt kê những KHÁI NIỆM' in system:
            out = {'concepts': [{'name': 'Khách chủ', 'kind': 'explains', 'quote': QUOTE},
                                {'name': 'Câu không có trong sách', 'kind': 'explains',
                                 'quote': 'đoạn này không hề có trên trang'}]}
        elif 'biên tập viên' in system:
            out = {'status': 'ready', 'essential_notes': 'Phải xác định cấp độ trước.',
                   'definition': 'Cách phân định phần thuộc về chủ thể đang xét và phần ở bên ngoài'
                                 ' nó; tương đối theo cấp độ xét.',
                   'claims': [{'text': 'Khách và chủ tương đối theo cấp độ', 'evidence': ['E1']},
                              {'text': 'Ý bịa nhãn', 'evidence': ['E9']}]}
        else:
            out = {'verdict': self.verdict, 'problems': [] if self.verdict == 'pass' else
                   [{'kind': 'unsupported', 'detail': 'ý 2 không có nguồn'}]}
        return httpx.Response(200, json={
            'choices': [{'message': {'content': json.dumps(out, ensure_ascii=False)},
                         'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20}, 'model': 'fake-gemini'})


class CurationTests(PipelineTestCase):
    def setUp(self):
        super().setUp()
        if not getattr(type(self), 'version', None):
            type(self).version = self.publish_book(PAGES, 'manh_phai')
        with patch.dict(os.environ, {'FIELD_ENCRYPTION_KEY': FIELD_KEY}, clear=True):
            self.settings = load_settings(_env_file=None, curator_llm_base_url='http://gemini.test/v1beta/openai',
                                          curator_llm_model='fake-gemini')
        row = self.sql('SELECT id, email, role FROM users WHERE id = %s', self.user)[0]
        self.principal = Principal(row[0], row[1], row[2], uuid.UUID(int=0), '')

    def run_curation(self, fake, **kw):
        return curation.run(self.engine, self.principal, self.settings,
                            transport=httpx.MockTransport(fake), **kw)

    def test_draft_sources_review_then_people_approve(self):
        fake = FakeGemini()
        report = self.run_curation(fake)
        self.assertEqual((report['units'], report['candidates'], report['not_located']), (1, 2, 1))
        self.assertEqual((report['composed'], report['reviewed'], report['calls']), (1, 1, 3))
        self.assertTrue(all('chat_template_kwargs' not in b for b in fake.bodies))   # not vLLM

        # the quote was located by the code and stored as an ai_inferred span on that page
        cid, key, state, text_ = self.sql(
            "SELECT c.id::text, c.canonical_key, c.state, c.description FROM concepts c"
            " JOIN schools s ON s.id = c.school_id WHERE s.key = 'manh_phai' AND c.label = 'Khách chủ'")[0]
        self.assertEqual((key, state), ('bien_soan.khach_chu', 'draft'))
        self.assertIn('tương đối theo cấp độ', text_)
        quote, origin = self.sql(
            'SELECT substr(r.normalized_text, e.start_offset + 1, e.end_offset - e.start_offset), e.origin'
            ' FROM concept_sources cs JOIN evidence_spans e ON e.id = cs.evidence_id'
            ' JOIN page_revisions r ON r.id = e.page_revision_id WHERE cs.concept_id = %s', cid)[0]
        self.assertEqual((quote, origin), (QUOTE, 'ai_inferred'))
        claims, issues, verdict = self.sql(
            'SELECT claims, issues, llm_verdict FROM concept_curation WHERE concept_id = %s', cid)[0]
        self.assertEqual(len(claims), 1)                                  # the E9 claim was dropped
        self.assertTrue(any('E9' in i for i in issues))
        self.assertEqual(verdict, 'pass')

        # a rerun pays nothing and writes no new revision
        again = self.run_curation(FakeGemini())
        self.assertEqual((again['calls'], again['composed'], again['skipped']), (0, 0, 1))

        listed = self.c.get('/api/v1/curation/definitions', params={'verdict': 'pass'}).json()['data']
        self.assertEqual([r['label'] for r in listed], ['Khách chủ'])
        detail = self.c.get(f'/api/v1/curation/definitions/{cid}').json()['data']
        self.assertEqual(detail['evidence'][0]['quote'], QUOTE)
        approved = self.c.post('/api/v1/curation/definitions/approve', json={
            'items': [{'concept_id': cid, 'base_revision': 1}], 'reason': 'đã đọc đối chiếu nguồn'})
        self.assertEqual(approved.json()['data'], [{'concept_id': cid, 'approved': True, 'error': None}])
        self.assertEqual(self.sql("SELECT state FROM review_items WHERE entity_id = %s"
                                  " AND reason_code = 'CANDIDATE_DEFINITION'", cid), [('resolved',)])
        refused = self.c.post(f'/api/v1/curation/definitions/{cid}/rewrite', json={'note': 'ngắn hơn'})
        self.assertEqual(refused.status_code, 409)

    def test_rewrite_request_and_person_edit_keep_sources(self):
        self.run_curation(FakeGemini(verdict='fix'), names=['Khách chủ'], refresh=True)
        cid, revision = self.sql(
            "SELECT c.id::text, c.revision FROM concepts c WHERE c.label = 'Khách chủ'"
            ' ORDER BY c.revision DESC LIMIT 1')[0]
        if self.sql('SELECT state FROM concepts WHERE id = %s', cid)[0][0] == 'approved':
            self.skipTest('approved by the other test in this class')
        asked = self.c.post(f'/api/v1/curation/definitions/{cid}/rewrite', json={'note': 'nêu rõ cấp độ'})
        self.assertEqual(asked.json()['data']['status'], 'rewrite_requested')
        edited = self.c.post(f'/api/v1/concepts/{cid}/revisions', json={
            'base_revision': revision, 'description': 'Phân định chủ thể và phần bên ngoài, theo cấp độ.',
            'reason': 'sửa tay'}).json()['data']
        detail = self.c.get(f"/api/v1/curation/definitions/{edited['id']}").json()['data']
        self.assertEqual(detail['status'], 'ready')
        self.assertEqual(len(detail['evidence']), 1)
        self.assertIn('đã sửa tay sau khi máy soạn', detail['issues'])

    def test_provider_that_rejects_the_schema_gets_it_in_the_prompt(self):
        self.sql('DELETE FROM curation_calls')                # no cached answers: really call
        fake = FakeGemini(reject_schema=True)
        report = self.run_curation(fake, steps=('discover', 'compose'), names=['Khách chủ'],
                                   refresh=True)
        self.assertEqual((report['composed'], report['errors']), (1, []))
        plain = [b for b in fake.bodies if 'response_format' not in b]
        self.assertTrue(plain and 'JSON Schema' in plain[0]['messages'][-1]['content'])
        self.assertEqual(plain[0].get('reasoning_effort'), 'low')

    def test_budget_and_dry_run(self):
        dry = curation.run(self.engine, self.principal, self.settings, dry_run=True)
        self.assertEqual(dry['units'], 1)
        self.assertGreater(dry['estimated_input_tokens'], 0)
        stopped = self.run_curation(FakeGemini(), max_calls=0, refresh=True,
                                    steps=('compose',), names=['Một tên mới'])
        self.assertEqual(stopped['calls'], 0)
