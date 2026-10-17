"""Erasure of a person's private data, account deletion and the deletion ledger (T049)."""
from datetime import datetime, timezone
import uuid

from backend.app.ops.backup import Database, export_ledger, reapply_ledger
from tests.integration.db import database_url
from tests.integration.env import PASSWORD, PipelineTestCase
from tests.integration.test_reasoning import BIRTH, ConversationMixin


class ErasureTests(ConversationMixin, PipelineTestCase):
    def setUp(self):
        self.sql("UPDATE model_profiles SET enabled = false WHERE kind = 'llm'")

    def email(self, user_id: str) -> str:
        return self.sql('SELECT email FROM users WHERE id = %s', user_id)[0][0]

    def private_data(self, client, canary: str) -> dict:
        """A profile, a chart, an answered conversation, a private case and a setting."""
        profile = client.post('/api/v1/birth-profiles', json={
            'label': f'Hồ sơ {canary}', 'birth_input': BIRTH})
        self.assertEqual(profile.status_code, 201, profile.text)
        chart = client.post('/api/v1/charts', json={'profile_id': profile.json()['data']['id']})
        self.assertEqual(chart.status_code, 201, chart.text)
        conversation = self.conversation(client, mode='research')
        self.answered(conversation['id'], f'Câu hỏi riêng {canary}', client)
        school = self.schools()['manh_phai']
        case = client.post('/api/v1/cases', json={
            'origin': 'user_case', 'school_id': school, 'narrative': f'Chuyện riêng {canary}',
            'chart_payload': {'schema': 'book-case/1', 'pillars': {
                'year': {'stem': 'jia', 'branch': 'zi'}, 'month': {'stem': 'bing', 'branch': 'yin'},
                'day': {'stem': 'wu', 'branch': 'chen'}, 'hour': None}}})
        self.assertEqual(case.status_code, 201, case.text)
        setting = client.patch('/api/v1/settings', json={
            'scope': 'user', 'key': 'chat.default_mode', 'value': 'comparison'},
            headers={'If-Match': '"0"'})
        self.assertEqual(setting.status_code, 200, setting.text)
        return {'chart': chart.json()['data']['id'], 'conversation': conversation['id']}

    def mentions(self, needle: str) -> list[str]:
        """Every table.column whose text (or JSON as text) still contains ``needle``."""
        columns = self.sql(
            "SELECT table_name, column_name FROM information_schema.columns WHERE"
            " table_schema = 'public' AND data_type IN ('text', 'jsonb', 'json', 'USER-DEFINED',"
            " 'character varying')")
        found = []
        for table, column in columns:
            if self.sql(f'SELECT 1 FROM "{table}" WHERE "{column}"::text LIKE %s LIMIT 1',
                        f'%{needle}%'):
                found.append(f'{table}.{column}')
        return found

    def test_a_person_erases_their_own_data_and_nobody_elses(self):
        me, my_id = self.client('reader')
        other, _ = self.client('reader')
        canary, kept = uuid.uuid4().hex, uuid.uuid4().hex
        self.private_data(me, canary)
        theirs = self.private_data(other, kept)
        self.assertTrue(self.mentions(canary))

        wrong = me.post('/api/v1/auth/erasure', json={'confirm': 'not-me@example.test',
                                                      'password': PASSWORD})
        self.assertEqual((wrong.status_code, wrong.json()['code']), (422, 'CONFIRMATION_MISMATCH'))
        bad = me.post('/api/v1/auth/erasure', json={'confirm': self.email(my_id),
                                                    'password': 'wrong password'})
        self.assertEqual((bad.status_code, bad.json()['code']), (403, 'PASSWORD_INCORRECT'))
        self.assertTrue(self.mentions(canary))                  # refused means nothing removed

        done = me.post('/api/v1/auth/erasure', json={'confirm': self.email(my_id),
                                                     'password': PASSWORD})
        self.assertEqual(done.status_code, 200, done.text)
        counts = done.json()['data']['counts']
        self.assertEqual((counts['charts'], counts['birth_profiles'], counts['conversations'],
                          counts['cases']), (1, 1, 1, 1))
        self.assertEqual(self.mentions(canary), [])
        for table in ('birth_profiles', 'bazi_charts', 'conversations', 'chat_runs',
                      'evidence_bundles', 'idempotency_keys'):
            self.assertEqual(self.sql(f'SELECT count(*) FROM {table} WHERE owner_id = %s',
                                      my_id)[0][0], 0, table)
        self.assertEqual(self.sql("SELECT count(*) FROM settings WHERE owner_id = %s", my_id)[0][0], 0)
        # Still signed in (data only), with an empty account.
        self.assertEqual(me.get('/api/v1/charts').json()['data'], [])
        self.assertEqual(me.get('/api/v1/conversations').json()['data'], [])

        self.assertTrue(self.mentions(kept))
        self.assertEqual(other.get(f"/api/v1/charts/{theirs['chart']}").status_code, 200)
        ledger = self.sql('SELECT subject_id::text, account_deleted, counts FROM deletion_ledger'
                          ' WHERE subject_id = %s', my_id)
        self.assertEqual([(s, a) for s, a, _ in ledger], [(my_id, False)])
        self.assertNotIn(canary, str(ledger[0][2]))
        audit = self.sql("SELECT action, redacted_diff::text FROM audit_logs WHERE target_id = %s",
                         my_id)
        self.assertEqual([a for a, _ in audit], ['user.erase_data'])

    def test_an_admin_deletes_an_account_and_its_sessions_stop(self):
        admin, admin_id = self.client('admin')
        person, person_id = self.client('reader')
        canary = uuid.uuid4().hex
        self.private_data(person, canary)
        email = self.email(person_id)
        reviewer = self.c.post(f'/api/v1/users/{person_id}/erasure', json={'confirm': email})
        self.assertEqual(reviewer.status_code, 403)

        done = admin.post(f'/api/v1/users/{person_id}/erasure',
                          json={'confirm': email, 'delete_account': True})
        self.assertEqual(done.status_code, 200, done.text)
        self.assertEqual(self.mentions(canary), [])
        self.assertEqual(self.mentions(email), [])               # the address is gone too
        self.assertEqual(person.get('/api/v1/auth/me').status_code, 401)
        relogin = person.post('/api/v1/auth/login', json={'email': email, 'password': PASSWORD})
        self.assertEqual(relogin.status_code, 401)
        self.assertEqual(self.sql('SELECT enabled FROM users WHERE id = %s', person_id)[0][0], False)
        self.assertEqual(self.sql('SELECT requested_by::text FROM deletion_ledger'
                                  ' WHERE subject_id = %s', person_id)[0][0], admin_id)

    def test_the_last_admin_cannot_delete_their_own_account(self):
        admin, admin_id = self.client('admin')
        others = [r[0] for r in self.sql("SELECT id::text FROM users WHERE role = 'admin'"
                                         ' AND enabled AND id <> %s', admin_id)]
        self.sql("UPDATE users SET enabled = false WHERE id = ANY(%s::uuid[])", others)
        try:
            refused = admin.post('/api/v1/auth/erasure', json={
                'confirm': self.email(admin_id), 'password': PASSWORD, 'delete_account': True})
            self.assertEqual((refused.status_code, refused.json()['code']), (409, 'LAST_ADMIN'))
        finally:
            self.sql("UPDATE users SET enabled = true WHERE id = ANY(%s::uuid[])", others)

    def test_a_restore_applies_erasures_made_after_the_backup(self):
        person, person_id = self.client('reader')
        before = datetime.now(timezone.utc)
        self.assertEqual(person.post('/api/v1/auth/erasure', json={
            'confirm': self.email(person_id), 'password': PASSWORD}).status_code, 200)
        db = Database.from_conninfo(database_url(self.db))
        ledger = export_ledger(db)
        self.assertIn(person_id, [e['subject_id'] for e in ledger['entries']])
        # As if an older backup brought the data back: it must go again.
        canary = uuid.uuid4().hex
        self.private_data(person, canary)
        self.assertTrue(self.mentions(canary))
        self.assertGreaterEqual(reapply_ledger(db, ledger, before), 1)
        self.assertEqual(self.mentions(canary), [])
        # Entries older than the backup were already applied in it.
        self.assertEqual(reapply_ledger(db, ledger, datetime.now(timezone.utc)), 0)

    def test_deleting_a_birth_profile_removes_its_label_and_birth_data(self):
        canary = uuid.uuid4().hex
        made = self.c.post('/api/v1/birth-profiles', json={'label': canary, 'birth_input': BIRTH})
        profile_id = made.json()['data']['id']
        gone = self.c.delete(f'/api/v1/birth-profiles/{profile_id}')
        self.assertIn(gone.status_code, (200, 204), gone.text)
        self.assertEqual(self.mentions(canary), [])
        self.assertEqual(self.sql('SELECT octet_length(birth_input_encrypted) FROM birth_profiles'
                                  ' WHERE id = %s', profile_id)[0][0], 0)
