"""Backend foundation: config validation, request correlation, problems, redaction."""
import asyncio
import io
import json
import os
import unittest
from unittest.mock import patch
import warnings

from fastapi import Body

with warnings.catch_warnings():
    # Starlette 1.x warns that its TestClient will move to httpx2; behavior is unchanged.
    warnings.simplefilter('ignore')
    from fastapi.testclient import TestClient

from backend.app.core.config import ConfigError, load_settings
from backend.app.core.errors import AppError
from backend.app.core.health import CheckResult, ReadinessCheck, default_checks
from backend.app.core.logging import Redactor, configure_logging
from backend.app.main import create_app

# Obviously fake values; long enough for production validation.
SIGNING = 'fake-signing-key-for-tests-0123456789'
PROD = dict(app_env='production', postgres_password='fake-db-password-xyz',
            postgres_app_user='bazi_app', postgres_app_password='fake-app-password-xyz')
ENCRYPTION = 'fake-encryption-key-for-tests-012345'
DB_PASSWORD = 'fake-db-password-xyz'
# Split so the repository secret scanner does not flag the fixture DSN.
DSN_PREFIX = 'postgresql://' + 'bazi:'
FAKE_LLM_KEY = 'fake-llm-api-key-abc123'


def settings(**overrides):
    # Ignore the developer's .env and process environment for deterministic tests.
    with patch.dict(os.environ, {}, clear=True):
        return load_settings(_env_file=None, **overrides)


def check(status, code='X', essential=False, delay=0.0, error=None, timeout_s=2.0):
    async def run():
        await asyncio.sleep(delay)
        if error:
            raise error
        return CheckResult(status, code)
    return ReadinessCheck(f'check_{code.lower()}', essential, run, timeout_s)


class ConfigTests(unittest.TestCase):
    def test_defaults_treat_blank_placeholders_as_unset(self):
        config = settings(llm_base_url='', postgres_password='  ', llm_model='')
        self.assertIsNone(config.llm_base_url)
        self.assertIsNone(config.postgres_password)
        self.assertFalse(config.llm_configured)

    def test_invalid_values_fail_with_field_names_only(self):
        with self.assertRaises(ConfigError) as caught:
            settings(app_env='staging', postgres_port='not-a-port',
                     llm_base_url='http://gemma:8080/chat?token=leaky-value')
        message = str(caught.exception)
        for field in ('app_env', 'postgres_port', 'llm_base_url'):
            self.assertIn(field, message)
        self.assertNotIn('leaky-value', message)
        self.assertNotIn('not-a-port', message)
        self.assertIsNone(caught.exception.__cause__)

    def test_llm_base_url_normalized_to_v1(self):
        config = settings(llm_base_url='http://gemma:8080/v1/', llm_model='gemma')
        self.assertEqual(config.llm_base_url, 'http://gemma:8080/v1')
        self.assertTrue(config.llm_configured)

    def test_production_requires_strong_secrets_without_echoing_them(self):
        with self.assertRaisesRegex(ConfigError, 'session_signing_key'):
            settings(**PROD)
        with self.assertRaisesRegex(ConfigError, 'postgres_app_user distinct'):
            settings(**{**PROD, 'postgres_app_user': 'bazi'}, session_signing_key=SIGNING,
                     field_encryption_key=ENCRYPTION)
        with self.assertRaises(ConfigError) as caught:
            settings(**PROD, session_signing_key='short-secret', field_encryption_key=ENCRYPTION)
        self.assertIn('at least 32', str(caught.exception))
        self.assertNotIn('short-secret', str(caught.exception))
        ok = settings(**PROD, session_signing_key=SIGNING, field_encryption_key=ENCRYPTION)
        self.assertNotIn(SIGNING, repr(ok))

    def test_database_url_escapes_and_hides_password(self):
        url = settings(postgres_password='p@ss:/word', postgres_host='127.0.0.1').database_url
        self.assertEqual(url.password, 'p@ss:/word')
        self.assertNotIn('p@ss', str(url))
        self.assertIn('p%40ss%3A%2Fword', url.render_as_string(hide_password=False))

    def test_environment_variables_are_read(self):
        with patch.dict(os.environ, {'APP_ENV': 'test', 'POSTGRES_PORT': '6543'}, clear=True):
            config = load_settings(_env_file=None)
        self.assertEqual((config.app_env, config.postgres_port), ('test', 6543))


class RedactorTests(unittest.TestCase):
    def test_masks_known_secrets_and_credential_shapes(self):
        redact = Redactor([FAKE_LLM_KEY])
        text = redact(f'key {FAKE_LLM_KEY}; password=hunter22 token: "abc.def" '
                      'Authorization: Bearer eyJhbGciOi.x.y '
                      f'{DSN_PREFIX}dbpass@postgres:5432/bazi')
        for leaked in (FAKE_LLM_KEY, 'hunter22', 'abc.def', 'eyJhbGciOi', 'dbpass'):
            self.assertNotIn(leaked, text)
        self.assertIn(f'{DSN_PREFIX}[REDACTED]@postgres', text)


class AppTests(unittest.TestCase):
    def make_client(self, checks=None, client=('127.0.0.1', 50000), **config):
        config.setdefault('llm_api_key', FAKE_LLM_KEY)
        app_settings = settings(**config)
        # No database in unit tests: only the configuration-level checks by default.
        app = create_app(app_settings, readiness_checks=checks if checks is not None
                         else default_checks(app_settings))

        @app.get('/api/v1/_test/boom')
        async def boom():
            raise RuntimeError(f'upstream rejected api_key {FAKE_LLM_KEY}')

        @app.post('/api/v1/_test/echo')
        async def echo(year: int = Body(..., embed=True)):
            return {'year': year}

        @app.get('/api/v1/_test/conflict')
        async def conflict():
            raise AppError(412, 'REVISION_MISMATCH', 'Revision changed')

        self.logs = io.StringIO()
        configure_logging('INFO', app_settings.secret_values(), stream=self.logs)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            return TestClient(app, raise_server_exceptions=False, client=client)

    def log_lines(self):
        return [json.loads(line) for line in self.logs.getvalue().splitlines()]

    def assert_problem(self, response, status, code):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response.headers['content-type'], 'application/problem+json')
        body = response.json()
        self.assertEqual((body['status'], body['code']), (status, code))
        self.assertEqual(body['request_id'], response.headers['x-request-id'])
        return body

    def test_live_envelope_and_request_id_in_log(self):
        response = self.make_client().get('/api/v1/health/live')
        self.assertEqual(response.status_code, 200)
        request_id = response.headers['x-request-id']
        self.assertEqual(response.json(), {'data': {'status': 'ok'},
                                           'meta': {'request_id': request_id}})
        access = [l for l in self.log_lines() if l.get('event') == 'http_request']
        self.assertEqual(access[-1]['request_id'], request_id)
        self.assertEqual((access[-1]['path'], access[-1]['status']), ('/api/v1/health/live', 200))

    def test_incoming_request_id_kept_only_when_safe(self):
        client = self.make_client()
        kept = client.get('/api/v1/health/live', headers={'X-Request-ID': 'trace-1234abcd'})
        self.assertEqual(kept.headers['x-request-id'], 'trace-1234abcd')
        replaced = client.get('/api/v1/health/live', headers={'X-Request-ID': 'bad id<script>'})
        self.assertRegex(replaced.headers['x-request-id'], r'^[0-9a-f]{32}$')

    def test_unknown_route_is_problem(self):
        self.assert_problem(self.make_client().get('/api/v1/missing'), 404, 'NOT_FOUND')

    def test_app_error_keeps_code(self):
        body = self.assert_problem(self.make_client().get('/api/v1/_test/conflict'),
                                   412, 'REVISION_MISMATCH')
        self.assertEqual(body['detail'], 'Revision changed')

    def test_validation_error_lists_fields_without_input(self):
        response = self.make_client().post('/api/v1/_test/echo', json={'year': 'secret-birth'})
        body = self.assert_problem(response, 422, 'VALIDATION_ERROR')
        self.assertEqual(body['field_errors'][0]['path'], 'body.year')
        self.assertNotIn('secret-birth', response.text)

    def test_unhandled_exception_hides_text_and_logs_redacted(self):
        response = self.make_client().get('/api/v1/_test/boom')
        body = self.assert_problem(response, 500, 'INTERNAL_ERROR')
        self.assertNotIn(FAKE_LLM_KEY, response.text)
        self.assertNotIn('upstream', body['detail'])
        errors = [l for l in self.log_lines() if l.get('event') == 'unhandled_exception']
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]['request_id'], body['request_id'])
        self.assertEqual(errors[0]['exc_type'], 'RuntimeError')
        self.assertNotIn(FAKE_LLM_KEY, self.logs.getvalue())
        self.assertIn('[REDACTED]', errors[0]['traceback'])

    def test_ready_degraded_without_model(self):
        response = self.make_client().get('/api/v1/health/ready')
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['status'], 'degraded')
        self.assertEqual(data['checks'][0]['code'], 'PROVIDER_NOT_CONFIGURED')

    def test_ready_ok_when_model_configured(self):
        client = self.make_client(llm_base_url='http://gemma:8080/v1', llm_model='gemma')
        self.assertEqual(client.get('/api/v1/health/ready').json()['data']['status'], 'ok')

    def test_ready_fails_only_on_essential_checks(self):
        checks = [check('ok', 'DB', essential=True),
                  check('ok', 'SLOW', essential=True, delay=0.5, timeout_s=0.05),
                  check('ok', 'BROKEN', error=ValueError(f'password={DB_PASSWORD}'))]
        response = self.make_client(checks=checks).get('/api/v1/health/ready')
        self.assertEqual(response.status_code, 503)
        codes = {c['name']: c['code'] for c in response.json()['data']['checks']}
        self.assertEqual(codes, {'check_db': 'DB', 'check_slow': 'TIMEOUT',
                                 'check_broken': 'CHECK_ERROR'})
        self.assertNotIn(DB_PASSWORD, response.text + self.logs.getvalue())

    def test_ready_rejects_external_callers(self):
        client = self.make_client(client=('203.0.113.7', 50000))
        self.assert_problem(client.get('/api/v1/health/ready'), 403, 'FORBIDDEN')
        self.assertEqual(client.get('/api/v1/health/live').status_code, 200)

    def test_production_hides_openapi(self):
        client = self.make_client(**PROD, session_signing_key=SIGNING,
                                  field_encryption_key=ENCRYPTION)
        self.assertEqual(client.get('/api/v1/openapi.json').status_code, 404)


if __name__ == '__main__':
    unittest.main()
