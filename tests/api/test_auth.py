"""Auth API against PostgreSQL as the runtime role: sessions, CSRF, roles, bootstrap."""
import io
import os
import unittest
from unittest.mock import patch
import uuid
import warnings

import psycopg

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

from backend.app import cli
from backend.app.auth.service import create_user
from backend.app.core.config import load_settings
from backend.app.core.logging import configure_logging
from backend.app.main import create_app
from tests.integration.db import (ADMIN_URL, create_runtime_login, database_url, drop_database,
                                  drop_role, engine_for, migrated_database)

DB_NAME = ROLE = RUNTIME = None
PASSWORD = 'correct horse battery staple'


def setUpModule():
    global DB_NAME, ROLE, RUNTIME
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


def owner_engine():
    return engine_for(database_url(DB_NAME))


def make_user(role='reader', email=None, enabled=True):
    email = email or f'{uuid.uuid4().hex[:8]}@example.test'
    with owner_engine().begin() as conn:
        user = create_user(conn, email, PASSWORD, role)
        if not enabled:
            conn.exec_driver_sql('UPDATE users SET enabled = false WHERE id = %(id)s',
                                 {'id': user['id']})
    return email


def client(engine=None, **settings):
    with patch.dict(os.environ, {}, clear=True):
        config = load_settings(_env_file=None, **settings)
    app = create_app(config, engine=engine or engine_for(RUNTIME))
    configure_logging('WARNING', [], stream=io.StringIO())
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return TestClient(app, client=('127.0.0.1', 40000))


class AuthTests(unittest.TestCase):
    def login(self, c, email, password=PASSWORD, **kwargs):
        return c.post('/api/v1/auth/login', json={'email': email, 'password': password}, **kwargs)

    def signed_in(self, role='reader'):
        c = client()
        email = make_user(role)
        response = self.login(c, email)
        self.assertEqual(response.status_code, 200, response.text)
        c.headers['X-CSRF-Token'] = response.json()['data']['csrf_token']
        return c, email

    def test_login_sets_strict_httponly_cookie(self):
        c = client()
        email = make_user('reviewer')
        response = self.login(c, email.upper())
        self.assertEqual(response.status_code, 200)
        cookie = response.headers['set-cookie'].lower()
        for attribute in ('bazi_session=', 'httponly', 'samesite=strict', 'path=/'):
            self.assertIn(attribute, cookie)
        self.assertNotIn('secure', cookie)  # loopback HTTP exception outside production
        body = response.json()['data']
        self.assertEqual(body['user']['role'], 'reviewer')
        self.assertIn('library:review', body['user']['capabilities'])
        self.assertGreaterEqual(len(body['csrf_token']), 40)
        me = c.get('/api/v1/auth/me').json()['data']
        self.assertEqual(me['email'], email)

    def test_session_token_stored_only_as_hash(self):
        c = client()
        email = make_user()
        self.login(c, email)
        token = c.cookies.get('bazi_session')
        with psycopg.connect(database_url(DB_NAME)) as conn:
            stored = conn.execute('SELECT token_hash FROM sessions s JOIN users u'
                                  ' ON u.id = s.user_id WHERE u.email = %s', (email,)).fetchone()[0]
        self.assertNotEqual(stored, token)
        self.assertEqual(len(stored), 64)

    def test_bad_credentials_look_identical(self):
        c = client()
        email = make_user()
        disabled = make_user(enabled=False)
        bodies = [self.login(c, *args).json() for args in (
            (email, 'wrong password!!'), ('nobody@example.test',), (disabled,))]
        self.assertEqual({(b['status'], b['code'], b['detail']) for b in bodies},
                         {(401, 'AUTH_REQUIRED', 'Invalid email or password')})

    def test_login_rate_limited(self):
        c = client(login_max_failures=3)
        email = make_user()
        for _ in range(3):
            self.assertEqual(self.login(c, email, 'wrong password!!').status_code, 401)
        blocked = self.login(c, email)  # correct password, still blocked
        self.assertEqual((blocked.status_code, blocked.json()['code']), (429, 'RATE_LIMITED'))
        self.assertGreater(int(blocked.headers['retry-after']), 0)

    def test_mutations_need_csrf_token(self):
        c, _ = self.signed_in()
        token = c.headers.pop('X-CSRF-Token')
        denied = c.post('/api/v1/auth/logout')
        self.assertEqual((denied.status_code, denied.json()['code']), (403, 'CSRF_FAILED'))
        self.assertEqual(c.post('/api/v1/auth/logout', headers={'X-CSRF-Token': 'x' * 43})
                         .status_code, 403)
        self.assertEqual(c.post('/api/v1/auth/logout', headers={'X-CSRF-Token': token})
                         .status_code, 204)
        self.assertEqual(c.get('/api/v1/auth/me').status_code, 401)

    def test_foreign_origin_rejected(self):
        c = client()
        response = self.login(c, make_user(), headers={'Origin': 'https://evil.example'})
        self.assertEqual((response.status_code, response.json()['code']), (403, 'ORIGIN_REJECTED'))
        self.assertEqual(self.login(c, make_user(), headers={'Origin': 'http://127.0.0.1:8000'})
                         .status_code, 200)

    def test_no_open_registration(self):
        anonymous = client()
        payload = {'email': 'new@example.test', 'password': PASSWORD, 'role': 'admin'}
        self.assertEqual(anonymous.post('/api/v1/users', json=payload).status_code, 401)
        reader, _ = self.signed_in('reader')
        self.assertEqual(reader.post('/api/v1/users', json=payload).status_code, 403)
        self.assertEqual(reader.get('/api/v1/users').status_code, 403)

    def test_admin_manages_users(self):
        admin, _ = self.signed_in('admin')
        email = f'{uuid.uuid4().hex[:8]}@example.test'
        created = admin.post('/api/v1/users', json={'email': email, 'password': PASSWORD,
                                                    'role': 'reader'})
        self.assertEqual(created.status_code, 201)
        self.assertNotIn('password', created.text)
        duplicate = admin.post('/api/v1/users', json={'email': email, 'password': PASSWORD,
                                                      'role': 'reader'})
        self.assertEqual((duplicate.status_code, duplicate.json()['code']), (409, 'CONFLICT'))
        weak = admin.post('/api/v1/users', json={'email': 'w@example.test', 'password': 'short',
                                                 'role': 'reader'})
        self.assertEqual(weak.status_code, 422)
        listed = {u['email'] for u in admin.get('/api/v1/users').json()['data']}
        self.assertIn(email, listed)

    def test_disabling_user_revokes_sessions(self):
        admin, _ = self.signed_in('admin')
        member = client()
        email = make_user()
        self.login(member, email)
        user_id = next(u['id'] for u in admin.get('/api/v1/users').json()['data']
                       if u['email'] == email)
        self.assertEqual(admin.patch(f'/api/v1/users/{user_id}', json={'enabled': False})
                         .status_code, 200)
        self.assertEqual(member.get('/api/v1/auth/me').status_code, 401)

    def test_last_admin_cannot_demote_itself(self):
        admin, email = self.signed_in('admin')
        with psycopg.connect(database_url(DB_NAME), autocommit=True) as conn:
            # Isolate: leave only this test's admin enabled (disabling all would itself fail).
            conn.execute("UPDATE users SET enabled = false WHERE role = 'admin' AND email <> %s",
                         (email,))
        me = admin.get('/api/v1/auth/me').json()['data']['id']
        response = admin.patch(f'/api/v1/users/{me}', json={'role': 'reader'})
        self.assertEqual((response.status_code, response.json()['code']), (409, 'LAST_ADMIN'))

    def test_readiness_reports_rls_enforced(self):
        checks = {c['name']: c['code'] for c in
                  client().get('/api/v1/health/ready').json()['data']['checks']}
        self.assertEqual(checks['database'], 'REACHABLE')
        self.assertEqual(checks['database_role'], 'RLS_ENFORCED')
        as_owner = client(engine=owner_engine()).get('/api/v1/health/ready').json()['data']
        codes = {c['name']: (c['status'], c['code']) for c in as_owner['checks']}
        self.assertEqual(codes['database_role'], ('degraded', 'RLS_BYPASS_ROLE'))


class BootstrapTests(unittest.TestCase):
    def env(self, **extra):
        info = psycopg.conninfo.conninfo_to_dict(ADMIN_URL)
        return {'POSTGRES_HOST': info['host'], 'POSTGRES_PORT': str(info['port']),
                'POSTGRES_USER': info['user'], 'POSTGRES_PASSWORD': info['password'],
                'POSTGRES_DB': self.db, **extra}

    def setUp(self):
        self.db = migrated_database('head')
        self.addCleanup(drop_database, self.db)

    def test_bootstrap_creates_first_admin_once(self):
        env = self.env(BAZI_BOOTSTRAP_PASSWORD=PASSWORD)
        with patch.dict(os.environ, env, clear=True), \
                patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()):
            self.assertEqual(cli.main(['bootstrap-admin', '--email', 'Root@Example.test']), 0)
            self.assertEqual(cli.main(['bootstrap-admin', '--email', 'second@example.test']), 1)
        with psycopg.connect(database_url(self.db)) as conn:
            admins = conn.execute("SELECT email FROM users WHERE role = 'admin'").fetchall()
        self.assertEqual(admins, [('root@example.test',)])

    def test_create_runtime_login_is_rls_bound(self):
        role = f'bazi_app_{uuid.uuid4().hex[:8]}'
        # The role holds CONNECT on the database: drop the database first.
        self.addCleanup(lambda: (drop_database(self.db), drop_role(role)))
        env = self.env(POSTGRES_APP_USER=role, POSTGRES_APP_PASSWORD=uuid.uuid4().hex)
        with patch.dict(os.environ, env, clear=True), patch('sys.stdout', io.StringIO()):
            self.assertEqual(cli.main(['create-runtime-login']), 0)
            self.assertEqual(cli.main(['create-runtime-login']), 0)  # idempotent (ALTER)
        with psycopg.connect(ADMIN_URL) as conn:
            flags = conn.execute(
                "SELECT r.rolcanlogin, r.rolsuper, r.rolbypassrls, pg_has_role(r.oid,"
                " 'bazi_runtime', 'MEMBER') FROM pg_roles r WHERE r.rolname = %s",
                (role,)).fetchone()
        self.assertEqual(flags, (True, False, False, True))

    def test_bootstrap_rejects_weak_password(self):
        with patch.dict(os.environ, self.env(BAZI_BOOTSTRAP_PASSWORD='short'), clear=True):
            with self.assertRaises(SystemExit):
                cli.main(['bootstrap-admin', '--email', 'a@example.test'])


if __name__ == '__main__':
    unittest.main()
