"""SEC05 (docs/13, docs/12 · Observability): logs never carry what users typed.

Every flow that handles private input runs with DEBUG logging captured: sign-in
(password), birth profile and chart (label, local birth time), a conversation answered by
the worker (question), search (query), a request rejected by validation, an unhandled
error, and an erasure (email confirmation). The captured JSON lines must contain none of
those values, and every line must be JSON.
"""
import io
import json
import logging
from unittest.mock import patch
import uuid

from backend.app.core.logging import configure_logging
from backend.app.reasoning.worker import work_once
from tests.integration.env import PASSWORD, PipelineTestCase
from tests.integration.test_reasoning import ConversationMixin
from tests.integration.test_search import MANH


class LogPrivacyTests(ConversationMixin, PipelineTestCase):
    def setUp(self):
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'llm'")
        self.buffer = io.StringIO()
        configure_logging('DEBUG', [], stream=self.buffer)
        self.addCleanup(configure_logging, 'WARNING', [], io.StringIO())

    def test_private_input_stays_out_of_the_logs(self):
        self.publish_book(MANH, 'manh_phai')
        canary = uuid.uuid4().hex[:12]
        person, person_id = self.client('reader')            # signs in with PASSWORD
        email = self.sql('SELECT email FROM users WHERE id = %s', person_id)[0][0]
        birth = {'local_datetime': '1987-03-29T04:17', 'timezone': 'Asia/Ho_Chi_Minh',
                 'sex_for_luck': 'female'}
        profile = person.post('/api/v1/birth-profiles', json={
            'label': f'Hồ sơ {canary}', 'birth_input': birth})
        self.assertEqual(profile.status_code, 201, profile.text)
        person.post('/api/v1/charts', json={'profile_id': profile.json()['data']['id']})
        person.get('/api/v1/charts', params={'q': f'tìm {canary}'})
        conversation = self.conversation(person, mode='research')
        self.answered(conversation['id'], f'thực thần sinh tài {canary}', person)
        person.post('/api/v1/search', json={'query': f'tra cứu {canary}', 'rerank': False})
        bad = person.post('/api/v1/birth-profiles', json={
            'label': f'lỗi {canary}', 'birth_input': {**birth, 'timezone': f'Mars/{canary}'}})
        self.assertIn(bad.status_code, (400, 422))
        with patch('backend.app.api.search.search', side_effect=RuntimeError(f'boom {canary}')):
            crashed = person.post('/api/v1/search', json={'query': f'sập {canary}'})
        self.assertEqual(crashed.status_code, 500)
        self.assertEqual(person.post('/api/v1/auth/erasure', json={
            'confirm': email, 'password': PASSWORD}).status_code, 200)
        work_once(self.engine)
        logging.getLogger().handlers[-1].flush()

        lines = [line for line in self.buffer.getvalue().splitlines() if line.strip()]
        self.assertGreater(len(lines), 10)
        for line in lines:
            json.loads(line)                                   # structured, one event a line
        text = self.buffer.getvalue()
        for secret in (PASSWORD, email, canary, '1987-03-29', '04:17'):
            with self.subTest(secret=secret):
                self.assertNotIn(secret, text)
        self.assertIn('unhandled_exception', text)             # the crash is still recorded
