"""Feedback on answers and rule analyses (M017): private, one per person and target."""
import json
import uuid

from tests.integration.env import PipelineTestCase
from tests.integration.test_reasoning import ConversationMixin
from tests.integration.test_search import MANH


class FeedbackTests(ConversationMixin, PipelineTestCase):
    def setUp(self):
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'llm'")

    def test_a_person_rates_their_answer_and_admins_only_see_counts(self):
        self.publish_book(MANH, 'manh_phai')
        me, my_id = self.client('reader')
        other, _ = self.client('reader')
        secret = f'bình luận riêng {uuid.uuid4().hex}'
        conversation = self.conversation(me, mode='research')
        run = self.answered(conversation['id'], 'thực thần sinh tài', me)
        message = run['assistant_message_id']
        url = f'/api/v1/messages/{message}/feedback'

        first = me.put(url, json={'rating': 1})
        self.assertEqual((first.status_code, first.json()['data']['rating']), (200, 1))
        again = me.put(url, json={'rating': -1, 'categories': ['wrong_source', 'unclear'],
                                  'comment': secret})
        self.assertEqual(again.json()['data']['categories'], ['unclear', 'wrong_source'])
        self.assertEqual(self.sql('SELECT count(*) FROM feedback WHERE user_id = %s', my_id)[0][0], 1)
        listed = me.get(f"/api/v1/conversations/{conversation['id']}/messages").json()['data']
        self.assertEqual([m['feedback']['rating'] if m['feedback'] else None for m in listed],
                         [None, -1])
        self.assertEqual(other.put(url, json={'rating': 1}).status_code, 404)
        bad = me.put(url, json={'rating': 2})
        self.assertEqual(bad.status_code, 422)
        question = listed[0]['id']
        refused = me.put(f'/api/v1/messages/{question}/feedback', json={'rating': 1})
        self.assertEqual((refused.status_code, refused.json()['code']), (409, 'NOT_RATEABLE'))

        admin, _ = self.client('admin')
        totals = admin.get('/api/v1/operations/metrics').json()['data']['database']['feedback_7d']
        self.assertGreaterEqual(totals['not_helpful'], 1)
        self.assertGreaterEqual(totals['categories']['wrong_source'], 1)
        self.assertNotIn(secret, json.dumps(totals, ensure_ascii=False))
