"""Birth profiles and charts: encryption, ownership, revisions, immutability (T030)."""
import os
import unittest
from unittest.mock import patch
import warnings

import psycopg

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

from backend.app.calc.chart import compute
from backend.app.calc.timebase import BirthInput
from backend.app.core.config import load_settings
from backend.app.main import create_app
from tests.integration.env import PipelineTestCase

BIRTH = {'local_datetime': '1990-08-17T06:45', 'timezone': 'Asia/Ho_Chi_Minh',
         'sex_for_luck': 'male'}


class ChartApiTests(PipelineTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.me, cls.me_id = cls.client('reader')
        cls.other, _ = cls.client('reader')

    def app_with(self, key: str | None) -> TestClient:
        """Another API process on the same data, with another (or no) field key."""
        env = {'LOG_LEVEL': 'WARNING', **({'FIELD_ENCRYPTION_KEY': key} if key else {})}
        with patch.dict(os.environ, env, clear=True):
            config = load_settings(_env_file=None)
        client = TestClient(create_app(config, engine=self.engine, store=self.store),
                            client=('127.0.0.1', 40001))
        client.cookies = self.me.cookies
        client.headers['X-CSRF-Token'] = self.me.headers['X-CSRF-Token']
        return client

    def test_profiles_are_encrypted_owned_and_revised(self):
        created = self.me.post('/api/v1/birth-profiles', json={'label': 'Con trai',
                                                               'birth_input': BIRTH})
        self.assertEqual(created.status_code, 201, created.text)
        profile = created.json()['data']
        self.assertEqual((created.headers['etag'], profile['revision'],
                          profile['birth_input']['local_datetime']),
                         ('"1"', 1, '1990-08-17T06:45'))
        blob, version = self.sql('SELECT birth_input_encrypted, crypto_key_version FROM'
                                 ' birth_profiles WHERE id = %s', profile['id'])[0]
        self.assertNotIn(b'1990-08-17', bytes(blob))
        self.assertNotIn(b'Ho_Chi_Minh', bytes(blob))
        self.assertTrue(version.startswith('v1:'))
        url = f"/api/v1/birth-profiles/{profile['id']}"
        self.assertEqual(self.other.get(url).status_code, 404)        # row-level security
        listed = self.me.get('/api/v1/birth-profiles').json()['data']
        self.assertNotIn('birth_input', next(p for p in listed if p['id'] == profile['id']))

        self.assertEqual(self.me.patch(url, json={'label': 'x'}).status_code, 428)
        stale = self.me.patch(url, json={'label': 'x'}, headers={'If-Match': '"7"'})
        self.assertEqual((stale.status_code, stale.headers['etag']), (412, '"1"'))
        changed = self.me.patch(url, json={'birth_input': {**BIRTH, 'local_datetime':
                                                           '1990-08-17T07:15'}},
                                headers={'If-Match': '"1"'})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual((changed.json()['data']['revision'], changed.headers['etag']), (2, '"2"'))

        refused = self.me.post('/api/v1/birth-profiles', json={'label': 'gap', 'birth_input': {
            'local_datetime': '2021-03-14T02:30', 'timezone': 'America/New_York'}})
        self.assertEqual((refused.status_code, refused.json()['code']), (422, 'NONEXISTENT_TIME'))
        self.assertEqual(refused.json()['field_errors'][0]['path'], 'body.local_datetime')

    def test_charts_keep_their_input_and_facts(self):
        made = self.me.post('/api/v1/charts', json={'birth_input': BIRTH})
        self.assertEqual(made.status_code, 201, made.text)
        chart = made.json()['data']
        facts = chart['facts']
        self.assertEqual((chart['validation_status'], chart['policy_id'], facts['schema_version']),
                         ('valid', 'standard-v1', 'chart-facts/1'))
        self.assertEqual(facts['facts_hash'], compute(BirthInput(**BIRTH))['facts_hash'])
        self.assertEqual(chart['pillars']['year'], 'geng-wu')
        self.assertEqual(facts['input_snapshot']['local_datetime'], '1990-08-17T06:45')
        stored = self.sql("SELECT facts ? 'input_snapshot', validation_status FROM bazi_charts"
                          ' WHERE id = %s', chart['id'])[0]
        self.assertEqual(stored, (False, 'valid'))                # input only encrypted
        with self.assertRaises(psycopg.errors.RestrictViolation):
            self.sql("UPDATE bazi_charts SET facts = facts || '{\"x\": 1}' WHERE id = %s",
                     chart['id'])
        self.assertEqual(self.other.get(f"/api/v1/charts/{chart['id']}").status_code, 404)

        policy = self.sql("SELECT state, manifest_hash = bazi_sha256_text(config::text)"
                          " FROM calculation_policies WHERE key = 'standard-v1'")[0]
        self.assertEqual(policy, ('active', True))
        catalog = self.me.get('/api/v1/calculation-policies').json()['data']
        self.assertEqual({p['id'] for p in catalog['policies']},
                         {'standard-v1', 'zi23-v1', 'solar-time-v1'})

        unknown = self.me.post('/api/v1/charts', json={'birth_input': {
            **BIRTH, 'time_accuracy': 'unknown'}, 'policy_id': 'zi23-v1'}).json()['data']
        self.assertEqual((unknown['validation_status'], unknown['pillars']['hour'],
                          unknown['policy_id']), ('partial', None, 'zi23-v1'))
        bad = self.me.post('/api/v1/charts', json={'birth_input': {**BIRTH, 'longitude': 400}})
        self.assertEqual(bad.status_code, 422)
        both = self.me.post('/api/v1/charts', json={})
        self.assertEqual(both.status_code, 422)

    def test_profile_charts_survive_profile_changes(self):
        profile = self.me.post('/api/v1/birth-profiles', json={
            'label': 'Hồ sơ', 'birth_input': BIRTH}).json()['data']
        chart = self.me.post('/api/v1/charts', json={'profile_id': profile['id'],
                                                      'profile_revision': 1}).json()['data']
        self.assertEqual((chart['profile_revision'], chart['profile_label']), (1, 'Hồ sơ'))
        self.me.patch(f"/api/v1/birth-profiles/{profile['id']}", json={
            'birth_input': {**BIRTH, 'local_datetime': '1991-01-01T00:30'}},
            headers={'If-Match': '"1"'})
        again = self.me.get(f"/api/v1/charts/{chart['id']}").json()['data']
        self.assertEqual(again['facts']['input_snapshot']['local_datetime'], '1990-08-17T06:45')
        gone = self.me.post('/api/v1/charts', json={'profile_id': profile['id'],
                                                     'profile_revision': 1})
        self.assertEqual((gone.status_code, gone.json()['code']), (409, 'PROFILE_REVISION_GONE'))
        newer = self.me.post('/api/v1/charts', json={'profile_id': profile['id']}).json()['data']
        self.assertEqual(newer['profile_revision'], 2)
        listed = self.me.get('/api/v1/charts', params={'q': 'hồ'}).json()['data']
        self.assertTrue({chart['id'], newer['id']} <= {c['id'] for c in listed})

        kept = self.me.delete(f"/api/v1/birth-profiles/{profile['id']}").json()['data']
        self.assertEqual((kept['charts_deleted'], kept['charts_kept']), (0, 2))
        self.assertEqual(self.me.get(f"/api/v1/charts/{chart['id']}").status_code, 200)
        self.assertEqual(self.me.delete(f"/api/v1/charts/{chart['id']}").status_code, 204)
        self.assertEqual(self.me.get(f"/api/v1/charts/{chart['id']}").status_code, 404)

    def test_wrong_or_missing_key_never_returns_garbage(self):
        chart = self.me.post('/api/v1/charts', json={'birth_input': BIRTH}).json()['data']
        wrong = self.app_with('another-field-key-of-another-env').get(
            f"/api/v1/charts/{chart['id']}")
        self.assertEqual((wrong.status_code, wrong.json()['code']), (409, 'ENCRYPTION_KEY_MISMATCH'))
        missing = self.app_with(None).post('/api/v1/charts', json={'birth_input': BIRTH})
        self.assertEqual((missing.status_code, missing.json()['code']),
                         (503, 'ENCRYPTION_NOT_CONFIGURED'))


if __name__ == '__main__':
    unittest.main()
