"""Qwen (vLLM, OpenAI-compatible) client for the RAG pilot.

One shared ``httpx`` client per process (created in the API lifespan, or once
per worker), explicit timeouts, bounded retries with full jitter on transient
failures only (timeouts, connection errors, 429/5xx; never 4xx). Structured
output asks vLLM for a JSON schema and is then parsed into a Pydantic model; a
response that fails validation is retried once with the error appended, then
fails with ``LLMError('SCHEMA_INVALID')`` — the caller decides the fallback.

Qwen3's thinking is off unless asked (``chat_template_kwargs.enable_thinking``):
it spends context tokens and the reasoning text is never shown or stored.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import random
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

T = TypeVar('T', bound=BaseModel)
RETRIES = 3


class LLMError(Exception):
    def __init__(self, code: str, message: str = ''):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    model: str
    timeout: float = 180.0
    api_key: str | None = None


@dataclass
class Completion:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    latency_ms: int


def _body(config: LLMConfig, messages: list[dict], max_tokens: int, temperature: float,
          thinking: bool, schema: type[BaseModel] | None) -> dict:
    body = {'model': config.model, 'messages': messages, 'max_tokens': max_tokens,
            'temperature': temperature,
            'chat_template_kwargs': {'enable_thinking': thinking}}
    if schema is not None:
        body['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': schema.__name__, 'schema': schema.model_json_schema()}}
    return body


def _completion(data: dict, started: float) -> Completion:
    choice = (data.get('choices') or [{}])[0]
    usage = data.get('usage') or {}
    content = (choice.get('message') or {}).get('content') or ''
    if choice.get('finish_reason') == 'length' and not content.strip():
        raise LLMError('TRUNCATED', 'the model ran out of tokens before answering')
    return Completion(content, usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0),
                      data.get('model', ''), int((time.perf_counter() - started) * 1000))


def _retryable(response: httpx.Response) -> bool:
    return response.status_code == 429 or response.status_code >= 500


def _parse(model: type[T], completion: Completion) -> T:
    raw = completion.text.strip()
    if raw.startswith('```'):
        raw = raw.strip('`').removeprefix('json').strip()
    return model.model_validate_json(raw)


def _repair(messages: list[dict], completion: Completion, error: ValidationError) -> list[dict]:
    problems = '; '.join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                         for e in error.errors(include_input=False))[:800]
    return messages + [{'role': 'assistant', 'content': completion.text[:4000]},
                       {'role': 'user', 'content': 'Kết quả trên không đúng định dạng JSON yêu cầu'
                        f' ({problems}). Trả lại đúng JSON theo schema, không thêm chữ nào khác.'}]


class AsyncLLM:
    """API side: one instance in ``app.state``, closed by the lifespan."""

    def __init__(self, config: LLMConfig, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        headers = {'Authorization': f'Bearer {config.api_key}'} if config.api_key else {}
        self.client = httpx.AsyncClient(
            base_url=config.base_url.rstrip('/'), headers=headers, transport=transport,
            timeout=httpx.Timeout(connect=5.0, read=config.timeout, write=30.0, pool=10.0),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8))

    async def aclose(self) -> None:
        await self.client.aclose()

    async def complete(self, messages: list[dict], max_tokens: int, temperature: float = 0.2,
                       thinking: bool = False, schema: type[BaseModel] | None = None) -> Completion:
        body = _body(self.config, messages, max_tokens, temperature, thinking, schema)
        for attempt in range(RETRIES):
            started = time.perf_counter()
            try:
                response = await self.client.post('/chat/completions', json=body)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == RETRIES - 1:
                    raise LLMError('PROVIDER_UNAVAILABLE', 'model server unreachable') from None
            else:
                if response.status_code < 400:
                    return _completion(response.json(), started)
                if not _retryable(response) or attempt == RETRIES - 1:
                    raise LLMError('PROVIDER_REJECTED' if not _retryable(response)
                                   else 'PROVIDER_UNAVAILABLE', f'HTTP {response.status_code}')
            await asyncio.sleep(random.uniform(0, 0.5 * 2 ** attempt))
        raise LLMError('PROVIDER_UNAVAILABLE')

    async def structured(self, messages: list[dict], model: type[T], max_tokens: int,
                         temperature: float = 0.2, thinking: bool = False) -> tuple[T, Completion]:
        completion = await self.complete(messages, max_tokens, temperature, thinking, model)
        try:
            return _parse(model, completion), completion
        except ValidationError as error:
            retry = await self.complete(_repair(messages, completion, error), max_tokens,
                                        temperature, thinking, model)
            try:
                return _parse(model, retry), retry
            except ValidationError:
                raise LLMError('SCHEMA_INVALID', 'model output failed validation twice') from None


class SyncLLM:
    """Worker side (Celery stages are synchronous): same contract, blocking client."""

    def __init__(self, config: LLMConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        headers = {'Authorization': f'Bearer {config.api_key}'} if config.api_key else {}
        self.client = httpx.Client(
            base_url=config.base_url.rstrip('/'), headers=headers, transport=transport,
            timeout=httpx.Timeout(connect=5.0, read=config.timeout, write=30.0, pool=10.0),
            limits=httpx.Limits(max_connections=16, max_keepalive_connections=8))

    def close(self) -> None:
        self.client.close()

    def complete(self, messages: list[dict], max_tokens: int, temperature: float = 0.0,
                 thinking: bool = False, schema: type[BaseModel] | None = None) -> Completion:
        body = _body(self.config, messages, max_tokens, temperature, thinking, schema)
        for attempt in range(RETRIES):
            started = time.perf_counter()
            try:
                response = self.client.post('/chat/completions', json=body)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == RETRIES - 1:
                    raise LLMError('PROVIDER_UNAVAILABLE', 'model server unreachable') from None
            else:
                if response.status_code < 400:
                    return _completion(response.json(), started)
                if not _retryable(response) or attempt == RETRIES - 1:
                    raise LLMError('PROVIDER_REJECTED' if not _retryable(response)
                                   else 'PROVIDER_UNAVAILABLE', f'HTTP {response.status_code}')
            time.sleep(random.uniform(0, 0.5 * 2 ** attempt))
        raise LLMError('PROVIDER_UNAVAILABLE')

    def structured(self, messages: list[dict], model: type[T], max_tokens: int,
                   temperature: float = 0.0, thinking: bool = False) -> tuple[T, Completion]:
        completion = self.complete(messages, max_tokens, temperature, thinking, model)
        try:
            return _parse(model, completion), completion
        except ValidationError as error:
            retry = self.complete(_repair(messages, completion, error), max_tokens, temperature,
                                  thinking, model)
            try:
                return _parse(model, retry), retry
            except ValidationError:
                raise LLMError('SCHEMA_INVALID', 'model output failed validation twice') from None


def config_from(settings) -> LLMConfig | None:
    """The configured Qwen endpoint, or None when the model is not configured."""
    if not settings.llm_configured:
        return None
    key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    return LLMConfig(settings.llm_base_url, settings.llm_model, settings.rag_llm_timeout, key)


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
