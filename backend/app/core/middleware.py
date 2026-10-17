"""Request correlation: one request_id per request in logs, headers and problems.

Pure ASGI (not BaseHTTPMiddleware) so SSE responses stream unbuffered and the
context variable is visible to handlers. It sits outside FastAPI's exception
middleware, so it is also the last line that turns unhandled errors into a 500
problem instead of letting the server print the exception text.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from .errors import unhandled_problem
from .logging import request_id_var

HEADER = b'x-request-id'
# Accept a caller's ID only if it is short and inert; otherwise mint our own.
_VALID_ID = re.compile(rb'^[A-Za-z0-9._-]{8,64}$')
log = logging.getLogger('bazi.access')


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        incoming = dict(scope['headers']).get(HEADER, b'')
        request_id = incoming.decode() if _VALID_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_id(message):
            nonlocal status, response_started
            if message['type'] == 'http.response.start':
                response_started = True
                status = message['status']
                headers = [h for h in message.get('headers', []) if h[0].lower() != HEADER]
                message = {**message, 'headers': [*headers, (HEADER, request_id.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:  # noqa: BLE001 - boundary: log, never echo
            if response_started:
                # Headers are gone; the client sees a truncated body. Record it.
                log.error('exception after response started',
                          exc_info=(type(exc), exc, exc.__traceback__),
                          extra={'event': 'unhandled_exception', 'error_code': 'INTERNAL_ERROR'})
            else:
                await unhandled_problem(exc)(scope, receive, send_with_id)
        finally:
            log.info('request', extra={
                'event': 'http_request', 'method': scope['method'], 'path': scope['path'],
                'status': status,
                'duration_ms': round((time.perf_counter() - started) * 1000, 1)})
            request_id_var.reset(token)
