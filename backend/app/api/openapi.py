"""OpenAPI document with examples (docs/10): every JSON request body and response gets a
success or failure example built from its schema, so the contract and the generated client
show real shapes. Examples are derived, never hand-kept, so they cannot drift from the DTOs."""
from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

EXAMPLE_UUID = '0b6e6600-2026-4a10-8000-00000000b471'
EXAMPLE_TIME = '2026-10-18T08:00:00Z'
# The code a client most often sees for each status; routes may raise more specific ones.
PROBLEM_CODES = {
    400: 'BAD_REQUEST', 401: 'AUTH_REQUIRED', 403: 'FORBIDDEN', 404: 'NOT_FOUND',
    409: 'CONFLICT', 410: 'EVENTS_EXPIRED', 412: 'REVISION_MISMATCH', 413: 'PAYLOAD_TOO_LARGE',
    415: 'UNSUPPORTED_MEDIA_TYPE', 422: 'VALIDATION_ERROR', 428: 'PRECONDITION_REQUIRED',
    429: 'RATE_LIMITED', 500: 'INTERNAL_ERROR', 502: 'PROVIDER_ERROR',
    503: 'PROVIDER_UNAVAILABLE',
}
_STRINGS = ('example', 'example_key', 'reader@example.test', '2026-10-18', 'vi', 'a1', 'x')


def _string(schema: dict) -> str:
    fmt = schema.get('format')
    if fmt == 'uuid':
        return EXAMPLE_UUID
    if fmt == 'date-time':
        return EXAMPLE_TIME
    if fmt == 'date':
        return EXAMPLE_TIME[:10]
    if fmt == 'email':
        return 'reader@example.test'
    if fmt in ('uri', 'url'):
        return 'https://example.test/'
    pattern = schema.get('pattern')
    low, high = schema.get('minLength', 0), schema.get('maxLength', 1000)
    for candidate in _STRINGS:
        if low <= len(candidate) <= high and (pattern is None or re.search(pattern, candidate)):
            return candidate
    return 'x' * max(low, 1)


def example(schema: Any, components: dict, depth: int = 0) -> Any:
    """A value valid for ``schema`` (enough for documentation; refs resolved, depth-capped)."""
    if not isinstance(schema, dict) or depth > 16:
        return None
    if '$ref' in schema:
        return example(components[schema['$ref'].rsplit('/', 1)[-1]], components, depth + 1)
    for key in ('example', 'default', 'const'):
        if key in schema and schema[key] is not None:
            return schema[key]
    if schema.get('examples'):
        return schema['examples'][0]
    if 'enum' in schema:
        return schema['enum'][0]
    for key in ('anyOf', 'oneOf'):
        if key in schema:
            options = [s for s in schema[key] if s.get('type') != 'null'] or schema[key]
            return example(options[0], components, depth + 1)
    if 'allOf' in schema:
        merged: dict = {}
        for part in schema['allOf']:
            value = example(part, components, depth + 1)
            if isinstance(value, dict):
                merged.update(value)
        return merged
    kind = schema.get('type')
    if kind == 'object' or 'properties' in schema:
        return {name: example(sub, components, depth + 1)
                for name, sub in schema.get('properties', {}).items()}
    if kind == 'array':
        return [example(schema.get('items', {}), components, depth + 1)
                for _ in range(max(1, schema.get('minItems', 1)))]
    if kind == 'string':
        return _string(schema)
    if kind in ('integer', 'number'):
        low = max(schema.get('minimum', 1), schema.get('exclusiveMinimum', 0) + 1)
        return int(low) if kind == 'integer' else float(low)
    if kind == 'boolean':
        return True
    return None


def problem_example(status: int) -> dict:
    code = PROBLEM_CODES.get(status, 'ERROR')
    body = {'type': f'urn:bazi:problem:{code.lower()}', 'title': code.replace('_', ' ').title(),
            'status': status, 'code': code, 'detail': None, 'request_id': 'req_0123456789abcdef',
            'field_errors': []}
    if status == 422:
        body['field_errors'] = [{'path': 'body.name', 'message': 'Field required'}]
    return body


def add_examples(document: dict) -> dict:
    components = document.get('components', {}).get('schemas', {})
    for operations in document.get('paths', {}).values():
        for method, operation in operations.items():
            if method not in ('get', 'post', 'put', 'patch', 'delete'):
                continue
            body = operation.get('requestBody', {}).get('content', {}).get('application/json')
            if body is not None and 'example' not in body:
                body['example'] = example(body.get('schema', {}), components)
            for status, response in operation.get('responses', {}).items():
                content = response.get('content', {})
                json_body = content.get('application/json')
                if json_body is None or 'example' in json_body or 'examples' in json_body:
                    continue
                if status.startswith(('4', '5')) and json_body.get('schema', {}).get(
                        '$ref', '').endswith('/Problem'):
                    json_body['example'] = problem_example(int(status))
                    content.get('application/problem+json', {}).setdefault(
                        'example', json_body['example'])
                else:
                    json_body['example'] = example(json_body.get('schema', {}), components)
    return document


def install(app: FastAPI) -> None:
    def openapi() -> dict:
        if app.openapi_schema is None:
            app.openapi_schema = add_examples(get_openapi(
                title=app.title, version=app.version, openapi_version=app.openapi_version,
                routes=app.routes))
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]
