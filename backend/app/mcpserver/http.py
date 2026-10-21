"""The MCP server inside the API: bearer-token check, mount, lifespan."""
from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json

from fastapi import FastAPI

from .backend import Backend
from .tools import build_server

MOUNT = '/mcp'


class BearerAuth:
    """ASGI guard: ``Authorization: Bearer <MCP_TOKEN>`` or 401, compared in constant time."""

    def __init__(self, app, token: str):
        self.app, self.expected = app, f'Bearer {token}'.encode()

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            given = dict(scope['headers']).get(b'authorization', b'')
            if not hmac.compare_digest(given, self.expected):
                body = json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {
                    'code': -32001, 'message': 'missing or invalid MCP token'}}).encode()
                await send({'type': 'http.response.start', 'status': 401, 'headers': [
                    (b'content-type', b'application/json'), (b'www-authenticate', b'Bearer'),
                    (b'content-length', str(len(body)).encode())]})
                await send({'type': 'http.response.body', 'body': body})
                return
        await self.app(scope, receive, send)


def install(app: FastAPI, settings, prefix: str, backend: Backend | None = None) -> None:
    """Mount the server when configured; ``lifespan(app)`` must then run its session manager."""
    app.state.mcp = None
    if not settings.mcp_enabled:
        return
    backend = backend or Backend(app.state.engine, settings, None)
    server = build_server(backend, settings)
    app.state.mcp, app.state.mcp_backend = server, backend
    app.mount(prefix + MOUNT, BearerAuth(server.streamable_http_app(),
                                         settings.mcp_token.get_secret_value()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    server = getattr(app.state, 'mcp', None)
    if server is None:
        yield
        return
    # Retrieval uses the RAG service built in the API lifespan (shared CPU models).
    if app.state.mcp_backend.rag is None:
        app.state.mcp_backend.rag = getattr(app.state, 'rag', None)
    async with server.session_manager.run():
        yield
