"""Reasoning runs, conversations and the event stream (T039-T041)."""
import json
import unittest
import uuid

from backend.app.reasoning.worker import housekeeping, work_once
from tests.integration.env import PipelineTestCase
from tests.integration.test_search import MANH, TU_BINH

BIRTH = {'local_datetime': '1990-08-17T06:45', 'timezone': 'Asia/Ho_Chi_Minh',
         'sex_for_luck': 'male'}


def sse(text_body: str) -> list[dict]:
    events = []
    for block in text_body.strip().split('\n\n'):
        fields = dict(line.split(': ', 1) for line in block.split('\n') if ': ' in line
                      and not line.startswith(':'))
        if 'event' in fields:
            events.append({'id': fields['id'], 'event': fields['event'],
                           'data': json.loads(fields['data'])})
    return events


class ConversationMixin:
    def schools(self) -> dict[str, str]:
        return {s['key']: s['id'] for s in self.c.get('/api/v1/schools').json()['data']}

    def conversation(self, client=None, **context) -> dict:
        made = (client or self.c).post('/api/v1/conversations', json={'context': context})
        self.assertEqual(made.status_code, 201, made.text)
        return made.json()['data']

    def ask(self, conversation_id: str, content: str, client=None, **extra):
        return (client or self.c).post(f'/api/v1/conversations/{conversation_id}/messages',
                                       json={'content': content, **extra},
                                       headers={'Idempotency-Key': uuid.uuid4().hex})

    def answered(self, conversation_id: str, content: str, client=None) -> dict:
        posted = self.ask(conversation_id, content, client)
        self.assertEqual(posted.status_code, 202, posted.text)
        run = posted.json()['data']['run']
        self.assertEqual(run['state'], 'queued')
        self.assertEqual(work_once(self.engine), 'completed')
        return (client or self.c).get(f"/api/v1/runs/{run['id']}").json()['data']


class EmptyCorpusTests(ConversationMixin, PipelineTestCase):
    def test_research_on_an_empty_corpus_says_so(self):
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'llm'")
        conversation = self.conversation(mode='research')
        run = self.answered(conversation['id'], 'Thực thần sinh tài là gì?')
        self.assertEqual((run['state'], run['answer']['status'], run['answer']['claims']),
                         ('completed', 'empty_corpus', []))
        self.assertIn('chưa có sách', run['answer']['summary'])


class ReasoningTests(ConversationMixin, PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        test = cls('test_research_without_a_model_quotes_sources')
        test.publish_book(MANH, 'manh_phai')
        test.publish_book(TU_BINH, 'tu_binh')
        cls.other, _ = cls.client('reviewer')

    def setUp(self):
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'llm'")

    def model(self, *replies):
        admin, _ = self.client('admin')
        made = admin.post('/api/v1/model-profiles', json={
            'kind': 'llm', 'provider': 'fixture-scripted', 'model_name': 'mock',
            'model_revision': uuid.uuid4().hex[:8],
            'config': {'replies': [json.dumps(r, ensure_ascii=False) for r in replies],
                       'locality': 'local'}})
        self.assertEqual(made.status_code, 201, made.text)

    def test_research_without_a_model_quotes_sources(self):
        manh = self.schools()['manh_phai']
        conversation = self.conversation(mode='research', school_ids=[manh])
        run = self.answered(conversation['id'], 'thực thần sinh tài')
        answer = run['answer']
        self.assertEqual(answer['status'], 'provider_not_configured')
        self.assertTrue(answer['claims'])
        claim = answer['claims'][0]
        self.assertEqual((claim['kind'], claim['support_status'], claim['school_key']),
                         ('source_statement', 'validated', 'manh_phai'))
        self.assertEqual(claim['citations'][0]['pages'], [1])
        stored = self.sql('SELECT count(*) FROM claims cl JOIN citations ci ON ci.claim_id = cl.id'
                          ' JOIN messages m ON m.id = cl.message_id WHERE m.run_id = %s', run['id'])
        self.assertGreaterEqual(stored[0][0], 1)

        stream = self.c.get(f"/api/v1/runs/{run['id']}/events")
        self.assertEqual(stream.headers['content-type'].split(';')[0], 'text/event-stream')
        events = sse(stream.text)
        kinds = [e['event'] for e in events]
        self.assertEqual(kinds[0], 'run.started')
        self.assertIn('retrieval.ready', kinds)
        self.assertEqual(kinds[-1], 'answer.completed')
        self.assertTrue(all(e['id'].startswith(run['id'] + ':') for e in events))
        resumed = sse(self.c.get(f"/api/v1/runs/{run['id']}/events",
                                 headers={'Last-Event-ID': events[2]['id']}).text)
        self.assertEqual([e['event'] for e in resumed], kinds[3:])     # replay, no re-run
        self.assertEqual(self.other.get(f"/api/v1/runs/{run['id']}").status_code, 404)
        self.assertEqual(self.other.get(f"/api/v1/runs/{run['id']}/events").status_code, 404)

        messages = self.c.get(f"/api/v1/conversations/{conversation['id']}/messages").json()['data']
        self.assertEqual([(m['role'], m['status']) for m in messages],
                         [('user', 'completed'), ('assistant', 'completed')])
        self.assertEqual(messages[1]['answer']['status'], 'provider_not_configured')
        found = self.c.get('/api/v1/conversations', params={'q': 'thực thần'}).json()['data']
        self.assertIn(conversation['id'], [c['id'] for c in found])

    def test_model_claims_are_validated_and_unsupported_ones_dropped(self):
        source = 'Tố công là cách nhật chủ làm việc, thực thần sinh tài mà giàu.'
        self.model({'summary': 'Sách Manh phái nói thực thần sinh tài thì giàu.',
                    'claims': [
                        {'text': source, 'kind': 'source_statement', 'evidence': ['E1'],
                         'school_key': 'manh_phai'},
                        {'text': 'Theo sách thì chắc chắn sẽ giàu 100%.', 'kind': 'interpretation',
                         'evidence': ['E1'], 'school_key': 'manh_phai'},
                        {'text': 'Một đoạn không có trong gói.', 'kind': 'source_statement',
                         'evidence': ['E9']},
                        {'text': 'Nhật chủ là Giáp.', 'kind': 'calculation',
                         'fact_paths': ['pillars.day.stem']},
                        {'text': 'Sách không nói về tiểu vận.', 'kind': 'limitation'}],
                    'limitations': [], 'follow_up_questions': ['Tài tinh là gì?']})
        conversation = self.conversation(mode='research',
                                         school_ids=[self.schools()['manh_phai']])
        answer = self.answered(conversation['id'], 'thực thần sinh tài')['answer']
        self.assertEqual((answer['status'], answer['rejected_claims']), ('partial', 2))
        statuses = [(c['kind'], c['support_status'], c['unresolved_exceptions'])
                    for c in answer['claims']]
        self.assertEqual(statuses[0], ('source_statement', 'validated', []))
        self.assertEqual(statuses[1][1], 'needs_review')
        self.assertIn('certainty_wording', statuses[1][2])
        self.assertIn('Sách không nói về tiểu vận.', answer['limitations'])
        self.assertEqual(answer['follow_up_questions'], ['Tài tinh là gì?'])

    def test_broken_model_output_falls_back_to_sources(self):
        self.model('not json', 'still not json')
        conversation = self.conversation(mode='research')
        answer = self.answered(conversation['id'], 'thực thần sinh tài')['answer']
        self.assertTrue(any('SCHEMA_INVALID' in note for note in answer['limitations']))
        self.assertTrue(all(c['support_status'] == 'validated' for c in answer['claims']))

    def test_chart_analysis_reports_facts_and_missing_rules(self):
        chart = self.c.post('/api/v1/charts', json={'birth_input': BIRTH}).json()['data']
        conversation = self.conversation(mode='chart_analysis', chart_id=chart['id'],
                                         school_ids=[self.schools()['manh_phai']])
        run = self.answered(conversation['id'], 'Nhật chủ của tôi thế nào?')
        answer = run['answer']
        calc = [c for c in answer['claims'] if c['kind'] == 'calculation']
        self.assertTrue(calc and all(c['support_status'] == 'validated' for c in calc))
        self.assertIn('pillars.day.stem', calc[0]['fact_paths'])
        self.assertTrue(any('phương pháp' in note for note in answer['limitations']))
        stranger = self.conversation(self.other, mode='research')
        blocked = self.other.patch(f"/api/v1/conversations/{stranger['id']}",
                                   json={'context': {'mode': 'chart_analysis',
                                                     'chart_id': chart['id']}},
                                   headers={'If-Match': '"1"'})
        self.assertEqual(blocked.status_code, 404)        # another owner's chart

    def test_modes_need_their_inputs(self):
        conversation = self.conversation(mode='comparison',
                                         school_ids=[self.schools()['manh_phai']])
        refused = self.ask(conversation['id'], 'So sánh thực thần sinh tài')
        self.assertEqual((refused.status_code, refused.json()['code']), (422, 'SCHOOLS_REQUIRED'))
        chart_less = self.ask(conversation['id'], 'Lá số?', mode='chart_analysis')
        self.assertEqual(chart_less.json()['code'], 'CHART_REQUIRED')
        both = self.schools()
        compare = self.conversation(mode='comparison',
                                    school_ids=[both['manh_phai'], both['tu_binh']])
        answer = self.answered(compare['id'], 'thực thần sinh tài')['answer']
        self.assertEqual({c['school_key'] for c in answer['claims']}, {'manh_phai', 'tu_binh'})

    def test_cancel_delete_and_memory_window(self):
        conversation = self.conversation(mode='research')
        first = self.answered(conversation['id'], 'thực thần sinh tài')
        posted = self.ask(conversation['id'], 'còn khách chủ thì sao?').json()['data']
        busy = self.ask(conversation['id'], 'câu thứ ba')
        self.assertEqual((busy.status_code, busy.json()['code']), (409, 'RUN_ACTIVE'))
        history = self.sql('SELECT context_snapshot FROM chat_runs WHERE id = %s',
                           posted['run']['id'])[0][0]['history']
        self.assertEqual([h['role'] for h in history], ['user', 'assistant'])
        cancelled = self.c.post(f"/api/v1/runs/{posted['run']['id']}/cancel").json()['data']
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertEqual(self.c.post(f"/api/v1/runs/{posted['run']['id']}/cancel")
                         .json()['data']['state'], 'cancelled')             # idempotent
        self.assertIsNone(work_once(self.engine))                           # nothing queued

        chart = self.c.post('/api/v1/charts', json={'birth_input': BIRTH}).json()['data']
        revision = self.c.get(f"/api/v1/conversations/{conversation['id']}").json()['data']['revision']
        moved = self.c.patch(f"/api/v1/conversations/{conversation['id']}", json={
            'context': {'mode': 'research', 'chart_id': chart['id']}},
            headers={'If-Match': f'"{revision}"'})
        self.assertEqual(moved.status_code, 200, moved.text)
        third = self.ask(conversation['id'], 'lá số mới').json()['data']
        self.assertEqual(self.sql('SELECT context_snapshot FROM chat_runs WHERE id = %s',
                                  third['run']['id'])[0][0]['history'], [])   # new window

        gone = self.c.delete(f"/api/v1/conversations/{conversation['id']}").json()['data']
        self.assertEqual(gone['runs_cancelled'], 1)
        self.assertEqual(self.c.get(f"/api/v1/conversations/{conversation['id']}").status_code,
                         404)
        left = self.sql("SELECT count(*) FILTER (WHERE content <> ''), count(*) FROM messages"
                        ' WHERE conversation_id = %s', conversation['id'])[0]
        self.assertEqual(left[0], 0)
        self.assertEqual(self.sql('SELECT count(*) FROM claims cl JOIN messages m ON'
                                  ' m.id = cl.message_id WHERE m.run_id = %s', first['id'])[0][0], 0)
        self.assertEqual(housekeeping(self.engine)['stale_runs_failed'], 0)


if __name__ == '__main__':
    unittest.main()
