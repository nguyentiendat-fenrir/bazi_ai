"""LLM provider adapters (docs/09 · Provider adapters; docs/12 · Kết nối Gemma llama.cpp).

The active LLM is the newest enabled ``model_profiles`` row of kind ``llm``.
``openai_compatible`` speaks ``POST {base_url}/chat/completions`` — llama.cpp's
server (Gemma), vLLM or a hosted API — with the profile's model, timeout,
retries and JSON mode (``json_schema``, ``json_object`` or ``none``). Timeouts,
429 and 5xx retry with jitter; other errors fail at once. Structured output is
validated against a pydantic schema; a malformed reply gets exactly one repair
turn, then the call fails safely. ``fixture-scripted`` replies offline from its
config for contract and E2E tests and is refused in production. A profile not
declared ``locality: local`` is external: book text goes to it only for
versions that allow external processing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
import random
import re
import time

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..core.errors import AppError

TIMEOUT = 60.0
MAX_RETRIES = 2
_WORD = re.compile(r'\w+|[^\w\s]', re.UNICODE)


class LLMError(Exception):
    def __init__(self, code: str, message: str, retryable: bool):
        super().__init__(message)
        self.code, self.retryable = code, retryable


@dataclass(frozen=True)
class LLMProfile:
    id: str
    provider: str
    model_name: str
    model_revision: str
    config: dict
    secret_ref: str | None

    @property
    def is_fixture(self) -> bool:
        return self.provider.startswith('fixture')

    @property
    def local(self) -> bool:
        return self.is_fixture or self.config.get('locality') == 'local'


@dataclass
class LLMResult:
    text: str
    data: BaseModel | None
    input_tokens: int
    output_tokens: int
    model: str
    request_id: str | None
    latency_ms: int
    attempts: int = 1
    repaired: bool = False
    raw: list = field(default_factory=list)


def load(conn: Connection, profile_id=None) -> LLMProfile | None:
    row = conn.execute(text(
        "SELECT id, provider, model_name, model_revision, config, secret_ref FROM model_profiles"
        " WHERE kind = 'llm' AND (CAST(:id AS uuid) IS NULL AND enabled OR id = CAST(:id AS uuid))"
        ' ORDER BY created_at DESC LIMIT 1'),
        {'id': str(profile_id) if profile_id else None}).mappings().first()
    return LLMProfile(str(row['id']), row['provider'], row['model_name'], row['model_revision'],
                      row['config'] or {}, row['secret_ref']) if row else None


def estimate_tokens(messages: list[dict]) -> int:
    """Rough count before the call (budget holds); the provider's usage replaces it."""
    return sum(len(_WORD.findall(m.get('content') or '')) + 4 for m in messages)


def may_send_book_text(conn: Connection, profile: LLMProfile, version_ids: list) -> bool:
    if profile.local or not version_ids:
        return True
    return bool(conn.execute(text(
        'SELECT bool_and(external_processing_allowed) FROM book_versions'
        ' WHERE id = ANY(CAST(:ids AS uuid[]))'), {'ids': [str(v) for v in version_ids]}).scalar())


def _parse(content: str, schema: type[BaseModel]):
    cleaned = content.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`')
        cleaned = cleaned[cleaned.find('{'):] if '{' in cleaned else cleaned
    return schema.model_validate_json(cleaned)


class _Adapter:
    profile: LLMProfile

    def _complete(self, messages: list[dict], max_tokens: int, temperature: float,
                  schema: type[BaseModel] | None) -> tuple[str, int, int, str | None]:
        raise NotImplementedError

    def generate(self, messages: list[dict], max_tokens: int = 512, temperature: float = 0.2,
                 schema: type[BaseModel] | None = None) -> LLMResult:
        started = time.perf_counter()
        attempts, tokens_in, tokens_out = 0, 0, 0
        conversation = list(messages)
        repaired, request_id, raw = False, None, []
        while True:
            content, used_in, used_out, request_id = self._with_retries(
                conversation, max_tokens, temperature, schema)
            attempts += 1
            tokens_in, tokens_out = tokens_in + used_in, tokens_out + used_out
            raw.append(content)
            data = None
            if schema is not None:
                try:
                    data = _parse(content, schema)
                except (ValidationError, ValueError) as exc:
                    if repaired:
                        raise LLMError('SCHEMA_INVALID', 'reply did not match the schema twice',
                                       False) from None
                    repaired = True
                    conversation += [{'role': 'assistant', 'content': content},
                                     {'role': 'user', 'content': (
                                         'The reply was not valid JSON for the required schema: '
                                         f'{str(exc)[:400]}. Answer again with only the JSON.')}]
                    continue
            return LLMResult(content, data, tokens_in, tokens_out, self.profile.model_name,
                             request_id, int((time.perf_counter() - started) * 1000), attempts,
                             repaired, raw)

    def _with_retries(self, messages, max_tokens, temperature, schema):
        retries = int(self.profile.config.get('max_retries', MAX_RETRIES))
        base = float(self.profile.config.get('retry_base_seconds', 1.0))
        for attempt in range(retries + 1):
            try:
                return self._complete(messages, max_tokens, temperature, schema)
            except LLMError as exc:
                if not exc.retryable or attempt == retries:
                    raise
                time.sleep(random.uniform(0, base * 2 ** attempt))   # full jitter


class OpenAICompatibleLLM(_Adapter):
    def __init__(self, profile: LLMProfile, transport: httpx.BaseTransport | None = None):
        self.profile, self.transport = profile, transport

    def _complete(self, messages, max_tokens, temperature, schema):
        base = self.profile.config.get('base_url')
        if not base:
            raise LLMError('PROVIDER_NOT_CONFIGURED', 'LLM profile has no base_url', False)
        body = {'model': self.profile.model_name, 'messages': messages, 'max_tokens': max_tokens,
                'temperature': temperature}
        mode = self.profile.config.get('json_mode', 'json_object')
        if schema is not None and mode == 'json_schema':
            body['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': schema.__name__, 'schema': schema.model_json_schema(), 'strict': True}}
        elif schema is not None and mode == 'json_object':
            body['response_format'] = {'type': 'json_object'}
        headers = {}
        if self.profile.secret_ref and os.environ.get(self.profile.secret_ref):
            headers['Authorization'] = f'Bearer {os.environ[self.profile.secret_ref]}'
        try:
            with httpx.Client(transport=self.transport,
                              timeout=float(self.profile.config.get('timeout', TIMEOUT))) as client:
                response = client.post(f"{base.rstrip('/')}/chat/completions", json=body,
                                       headers=headers)
        except httpx.TimeoutException:
            raise LLMError('PROVIDER_TIMEOUT', 'the model did not answer in time', True) from None
        except httpx.HTTPError as exc:
            raise LLMError('PROVIDER_UNAVAILABLE', f'unreachable: {type(exc).__name__}',
                           True) from None
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMError('PROVIDER_UNAVAILABLE', f'provider answered {response.status_code}',
                           True)
        if response.status_code != 200:
            raise LLMError('PROVIDER_REJECTED', f'provider answered {response.status_code}', False)
        payload = response.json()
        try:
            content = payload['choices'][0]['message']['content'] or ''
        except (KeyError, IndexError, TypeError):
            raise LLMError('PROVIDER_MALFORMED', 'no message in the reply', False) from None
        usage = payload.get('usage') or {}
        return (content, int(usage.get('prompt_tokens') or estimate_tokens(messages)),
                int(usage.get('completion_tokens') or len(_WORD.findall(content))),
                payload.get('id'))


class FixtureLLM(_Adapter):
    """Offline replies from ``config.replies`` in turn (default ``OK``). Test-only."""

    def __init__(self, profile: LLMProfile):
        self.profile, self.turn = profile, 0

    def _complete(self, messages, max_tokens, temperature, schema):
        replies = self.profile.config.get('replies') or ['OK']
        reply = replies[min(self.turn, len(replies) - 1)]
        self.turn += 1
        if isinstance(reply, dict) and reply.get('error'):
            raise LLMError(reply['error'], 'scripted failure', bool(reply.get('retryable')))
        content = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        return content, estimate_tokens(messages), len(_WORD.findall(content)), None


def build(profile: LLMProfile, app_env: str, transport=None) -> _Adapter:
    if profile.provider == 'fixture-scripted':
        if app_env == 'production':
            raise AppError(503, 'PROVIDER_NOT_CONFIGURED', 'fixture LLM is test-only')
        return FixtureLLM(profile)
    if profile.provider == 'openai_compatible':
        return OpenAICompatibleLLM(profile, transport)
    raise AppError(422, 'VALIDATION_ERROR', f'unsupported LLM provider {profile.provider}')
