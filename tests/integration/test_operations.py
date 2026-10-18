"""Operations metrics and alerts (T051): counts across owners, nothing private."""
from datetime import datetime, timedelta, timezone
import json
import unittest
import uuid

from backend.app.ops.metrics import _percentile, alerts
from tests.integration.env import PipelineTestCase
from tests.integration.test_reasoning import ConversationMixin
from tests.integration.test_search import MANH

NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def database(**changes) -> dict:
    base = {'ingestion': {'repeated_failures': 0, 'oldest_queued_seconds': None},
            'chat': {'oldest_queued_seconds': None}, 'stages': {'expired_leases': 0},
            'last_backup_at': (NOW - timedelta(hours=2)).isoformat(),
            'corpus_empty': False, 'active_embedding': True}
    for key, value in changes.items():
        if isinstance(value, dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


class AlertTests(unittest.TestCase):
    def codes(self, db=None, process=None, budgets=()) -> list[str]:
        return [a['code'] for a in alerts(db or database(), process or {'disk': None},
                                          list(budgets), NOW)]

    def test_a_healthy_system_has_no_alerts(self):
        self.assertEqual(self.codes(process={'disk': {'free_share': 0.5}}), [])

    def test_each_alert(self):
        self.assertEqual(self.codes(process={'disk': {'free_share': 0.05}}), ['DISK_LOW'])
        self.assertEqual(self.codes(database(last_backup_at=None)), ['BACKUP_MISSING'])
        old = (NOW - timedelta(hours=30)).isoformat()
        self.assertEqual(self.codes(database(last_backup_at=old)), ['BACKUP_OVERDUE'])
        self.assertEqual(self.codes(database(ingestion={'repeated_failures': 2})),
                         ['JOB_REPEATED_FAILURE'])
        self.assertEqual(self.codes(database(stages={'expired_leases': 1})), ['LEASE_EXPIRED'])
        self.assertEqual(self.codes(database(chat={'oldest_queued_seconds': 3600})),
                         ['QUEUE_STUCK'])
        self.assertEqual(self.codes(budgets=[{'profile_id': uuid.uuid4().hex, 'daily_budget': 1.0,
                                              'spent_today': 1.2}]), ['BUDGET_EXCEEDED'])
        self.assertEqual(self.codes(database(active_embedding=False)), ['NO_ACTIVE_EMBEDDING'])
        self.assertEqual(self.codes(database(active_embedding=False, corpus_empty=True)), [])

    def test_percentile(self):
        self.assertIsNone(_percentile([], 0.95))
        self.assertEqual(_percentile([float(i) for i in range(1, 101)], 0.95), 95.0)


class OperationsMetricsTests(ConversationMixin, PipelineTestCase):
    def test_admins_see_counts_across_owners_and_nothing_private(self):
        self.publish_book(MANH, 'manh_phai')
        reader, _ = self.client('reader')
        secret = f'câu hỏi riêng {uuid.uuid4().hex}'
        conversation = self.conversation(reader, mode='research')
        self.assertEqual(self.ask(conversation['id'], secret, reader).status_code, 202)
        self.c.post('/api/v1/search', json={'query': 'thực thần sinh tài', 'rerank': False})

        self.assertEqual(reader.get('/api/v1/operations/metrics').status_code, 403)
        self.assertEqual(self.c.get('/api/v1/operations/metrics').status_code, 403)   # reviewer
        admin, _ = self.client('admin')
        response = admin.get('/api/v1/operations/metrics')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()['data']
        db = data['database']
        self.assertGreaterEqual(db['chat']['by_state'].get('queued', 0), 1)   # another owner's run
        self.assertIsNotNone(db['chat']['oldest_queued_seconds'])
        self.assertGreaterEqual(db['pages'].get('accepted', 0), 2)
        self.assertGreaterEqual(db['ingestion']['by_state'].get('succeeded', 0), 1)
        self.assertTrue(db['active_embedding'])
        self.assertGreaterEqual(data['process']['retrieval_ms']['samples'], 1)
        self.assertIn('BACKUP_MISSING', [a['code'] for a in data['alerts']])
        dumped = json.dumps(data, ensure_ascii=False)
        self.assertNotIn(secret, dumped)
        self.assertNotIn(conversation['id'], dumped)
