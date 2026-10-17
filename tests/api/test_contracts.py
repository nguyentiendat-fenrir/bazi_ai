"""API contract: OpenAPI snapshot, typed problems, If-Match and Idempotency-Key.

The snapshot part runs without a database; behaviour tests need
BAZI_TEST_DATABASE_URL (tests/integration/db.py).
"""
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import uuid
import warnings

from fastapi import Body, Depends, Request
from sqlalchemy.engine import Connection

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

from backend.app.auth.deps import current_principal, db
from backend.app.auth.service import Principal, create_user
from backend.app.cli import OPENAPI_PATH, openapi_document
from backend.app.core.concurrency import claim_idempotency
from backend.app.core.config import load_settings
from backend.app.core.logging import configure_logging
from backend.app.main import create_app
from tests.integration.db import (ADMIN_URL, create_runtime_login, database_url, drop_database,
                                  drop_role, engine_for, migrated_database)

PASSWORD = 'correct horse battery staple'


class OpenApiSnapshotTests(unittest.TestCase):
    def test_snapshot_matches_code(self):
        committed = json.loads(Path(OPENAPI_PATH).read_text('utf-8'))
        self.assertEqual(committed, json.loads(json.dumps(openapi_document())),
                         'contracts/openapi.json is stale: run python -m backend.app.cli '
                         'export-openapi and review the diff')

    def test_every_operation_documents_permission_and_problems(self):
        document = openapi_document()
        for path, operations in document['paths'].items():
            for method, operation in operations.items():
                with self.subTest(op=f'{method.upper()} {path}'):
                    self.assertIn('x-permission', operation)
                    for status, response in operation['responses'].items():
                        if int(status) >= 400 and status != '503':
                            self.assertIn('application/problem+json', response['content'])
                    if operation['x-permission'] not in ('public', 'A or internal'):
                        self.assertIn('401', operation['responses'])

    def test_no_public_registration_route(self):
        posts = {p for p, ops in openapi_document()['paths'].items() if 'post' in ops}
        self.assertNotIn('/api/v1/auth/register', posts)
        users = openapi_document()['paths']['/api/v1/users']['post']
        self.assertEqual(users['x-permission'], 'A')


DB_NAME = ROLE = RUNTIME = None


def setUpModule():
    global DB_NAME, ROLE, RUNTIME
    if not ADMIN_URL:
        return  # snapshot tests still run; DB classes skip themselves
    DB_NAME = migrated_database('head')
    try:
        ROLE, RUNTIME = create_runtime_login(DB_NAME)
    except BaseException:
        drop_database(DB_NAME)
        raise


def tearDownModule():
    if DB_NAME:
        drop_database(DB_NAME)
    if ROLE:
        drop_role(ROLE)


def make_user(role):
    email = f'{uuid.uuid4().hex[:8]}@example.test'
    with engine_for(database_url(DB_NAME)).begin() as conn:
        create_user(conn, email, PASSWORD, role)
    return email


class DbApiTestCase(unittest.TestCase):
    def setUp(self):
        if not DB_NAME:
            self.skipTest('BAZI_TEST_DATABASE_URL is not set')
        with patch.dict(os.environ, {}, clear=True):
            config = load_settings(_env_file=None)
        self.app = create_app(config, engine=engine_for(RUNTIME))
        configure_logging('WARNING', [], stream=io.StringIO())

    def client(self, role='reader'):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            c = TestClient(self.app, client=('127.0.0.1', 40000))
        response = c.post('/api/v1/auth/login', json={'email': make_user(role),
                                                      'password': PASSWORD})
        c.headers['X-CSRF-Token'] = response.json()['data']['csrf_token']
        return c


class ProblemTests(DbApiTestCase):
    def test_framework_errors_are_typed_problems(self):
        c = self.client()
        cases = [(c.get('/api/v1/nope'), 404, 'NOT_FOUND'),
                 (c.delete('/api/v1/auth/me'), 405, 'METHOD_NOT_ALLOWED'),
                 (c.post('/api/v1/auth/login', json={'email': 'x'}), 422, 'VALIDATION_ERROR'),
                 (c.get('/api/v1/users'), 403, 'FORBIDDEN')]
        for response, status, code in cases:
            with self.subTest(code=code):
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers['content-type'], 'application/problem+json')
                body = response.json()
                self.assertEqual((body['status'], body['code']), (status, code))
                self.assertEqual(body['request_id'], response.headers['x-request-id'])


class SettingsTests(DbApiTestCase):
    def patch(self, c, scope, key, value, if_match):
        headers = {} if if_match is None else {'If-Match': if_match}
        return c.patch('/api/v1/settings', json={'scope': scope, 'key': key, 'value': value},
                       headers=headers)

    def test_user_setting_lifecycle_with_if_match(self):
        c = self.client()
        missing = self.patch(c, 'user', 'ui.theme', 'dark', None)
        self.assertEqual((missing.status_code, missing.json()['code']),
                         (428, 'PRECONDITION_REQUIRED'))
        created = self.patch(c, 'user', 'ui.theme', 'dark', '"0"')
        self.assertEqual((created.status_code, created.headers['etag']), (200, '"1"'))
        stale = self.patch(c, 'user', 'ui.theme', 'light', '"0"')
        self.assertEqual((stale.status_code, stale.json()['code'], stale.headers['etag']),
                         (412, 'REVISION_MISMATCH', '"1"'))
        updated = self.patch(c, 'user', 'ui.theme', 'light', '"1"')
        self.assertEqual(updated.json()['data']['revision'], 2)
        view = c.get('/api/v1/settings').json()['data']
        self.assertIn({'scope': 'user', 'key': 'ui.theme', 'value': 'light'},
                      [{k: s[k] for k in ('scope', 'key', 'value')} for s in view['settings']])
        self.assertEqual(set(view['runtime']), {'app_env', 'storage_backend', 'llm_provider',
                                                'llm_configured', 'embedding_configured'})

    def test_user_settings_are_private(self):
        alice, bob = self.client(), self.client()
        self.patch(alice, 'user', 'ui.locale', 'en', '"0"')
        keys = [s['key'] for s in bob.get('/api/v1/settings').json()['data']['settings']
                if s['scope'] == 'user']
        self.assertNotIn('ui.locale', keys)
        # Bob's own first write of the same key starts at revision 1 (separate row).
        self.assertEqual(self.patch(bob, 'user', 'ui.locale', 'vi', '"0"').status_code, 200)

    def test_system_scope_and_validation(self):
        reader, admin = self.client('reader'), self.client('admin')
        denied = self.patch(reader, 'system', 'retention.log_days', 30, '"0"')
        self.assertEqual(denied.status_code, 403)
        for key, value in (('unknown.key', 1), ('retention.log_days', -5),
                           ('library.default_rights_status', 'stolen')):
            with self.subTest(key=key):
                response = self.patch(admin, 'system', key, value, '"0"')
                self.assertEqual((response.status_code, response.json()['code']),
                                 (422, 'VALIDATION_ERROR'))
        ok = self.patch(admin, 'system', 'retention.log_days', 30, '"0"')
        self.assertEqual(ok.status_code, 200)
        self.assertIn('retention.log_days',
                      [s['key'] for s in reader.get('/api/v1/settings').json()['data']['settings']])


class UserIfMatchTests(DbApiTestCase):
    def test_stale_user_revision_rejected(self):
        admin = self.client('admin')
        email = make_user('reader')
        user_id = next(u['id'] for u in admin.get('/api/v1/users').json()['data']
                       if u['email'] == email)
        tag = admin.get(f'/api/v1/users/{user_id}').headers['etag']
        first = admin.patch(f'/api/v1/users/{user_id}', json={'role': 'reviewer'},
                            headers={'If-Match': tag})
        self.assertEqual(first.status_code, 200)
        stale = admin.patch(f'/api/v1/users/{user_id}', json={'role': 'admin'},
                            headers={'If-Match': tag})
        self.assertEqual((stale.status_code, stale.json()['code']), (412, 'REVISION_MISMATCH'))
        self.assertEqual(admin.patch(f'/api/v1/users/{user_id}', json={'enabled': False})
                         .status_code, 428)


class IdempotencyTests(DbApiTestCase):
    def setUp(self):
        super().setUp()
        self.calls = 0

        @self.app.post('/api/v1/_test/jobs', status_code=201)
        def create_job(request: Request, body: dict = Body(...),
                       principal: Principal = Depends(current_principal),
                       conn: Connection = Depends(db)):
            slot = claim_idempotency(conn, request, principal.user_id, 'POST /_test/jobs', body)
            if slot.replay:
                return slot.replay.body
            self.calls += 1
            result = {'data': {'job_id': str(uuid.uuid4()), 'input': body}}
            slot.complete(201, result)
            return result

    def test_same_key_same_payload_replays(self):
        c = self.client()
        headers = {'Idempotency-Key': 'upload-1'}
        first = c.post('/api/v1/_test/jobs', json={'file': 'a.pdf'}, headers=headers)
        second = c.post('/api/v1/_test/jobs', json={'file': 'a.pdf'}, headers=headers)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(self.calls, 1)

    def test_same_key_different_payload_conflicts(self):
        c = self.client()
        headers = {'Idempotency-Key': 'upload-2'}
        c.post('/api/v1/_test/jobs', json={'file': 'a.pdf'}, headers=headers)
        changed = c.post('/api/v1/_test/jobs', json={'file': 'b.pdf'}, headers=headers)
        self.assertEqual((changed.status_code, changed.json()['code']),
                         (409, 'IDEMPOTENCY_MISMATCH'))

    def test_keys_are_scoped_per_owner_and_validated(self):
        alice, bob = self.client(), self.client()
        headers = {'Idempotency-Key': 'shared-key'}
        a = alice.post('/api/v1/_test/jobs', json={'file': 'a.pdf'}, headers=headers).json()
        b = bob.post('/api/v1/_test/jobs', json={'file': 'b.pdf'}, headers=headers).json()
        self.assertNotEqual(a['data']['job_id'], b['data']['job_id'])
        for bad in (None, '', 'x' * 129, 'has space'):
            with self.subTest(key=bad):
                response = alice.post('/api/v1/_test/jobs', json={},
                                      headers={} if bad is None else {'Idempotency-Key': bad})
                self.assertEqual(response.status_code, 422)


if __name__ == '__main__':
    unittest.main()
