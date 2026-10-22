"""OCR on another machine: a small HTTP server around ``SenOcrEngine`` and the worker's client.

The worker renders pages as before and sends only the image; the remote machine needs the
app image, a GPU and the OCR models (``cli fetch-models --ocr-only``), not the database,
Redis or the object store. Set ``OCR_REMOTE_URL`` and ``OCR_REMOTE_TOKEN`` on the worker and
``shared_engine()`` returns a ``RemoteOcrEngine`` instead of loading the model locally.

Wire format of ``POST /v1/recognize``: the page as raw BGR uint8 bytes, zlib-compressed
(scanned pages are mostly white, so this is small and needs no image codec on either side),
with ``X-Shape: <height>,<width>,3``. The answer is the PaddleOCR-VL ``parsing_res_list``
exactly as the local engine returns it, so ``to_blocks`` and everything after are unchanged,
and the engine version is the server's, so units processed remotely and locally share
idempotency keys. Every route needs ``Authorization: Bearer <token>``.

Run the server (one process: the model is held once and pages are recognised one at a time)::

    OCR_SERVER_TOKEN=… uvicorn backend.app.ingestion.ocr_remote:create_server --factory \\
        --host 0.0.0.0 --port 8010
"""
from __future__ import annotations

import hmac
import json
import logging
import os
import zlib

from fastapi import Request   # module level: route annotations are resolved from globals

from .ocr import MAX_PIXELS, OcrOutOfMemory, OcrUnavailable

log = logging.getLogger('bazi.ocr')
MIN_TOKEN_LENGTH = 32
MAX_BODY = 64 * 1024 * 1024                  # compressed request cap
MAX_RAW = MAX_PIXELS * 3                     # decompressed cap: the render pixel limit, BGR
TIMEOUT_S = float(os.environ.get('OCR_REMOTE_TIMEOUT', '300'))


class BadImage(ValueError):
    pass


def encode(image) -> tuple[bytes, str]:
    """BGR uint8 array → (zlib body, ``X-Shape`` value)."""
    height, width, channels = image.shape
    return zlib.compress(image.tobytes(), 1), f'{height},{width},{channels}'


def decode(body: bytes, shape: str):
    """Inverse of ``encode``; refuses anything but H×W×3 within the pixel limit."""
    import numpy as np
    try:
        height, width, channels = (int(v) for v in shape.split(','))
    except ValueError:
        raise BadImage('X-Shape must be "<height>,<width>,3"') from None
    size = height * width * channels
    if channels != 3 or height <= 0 or width <= 0 or size > MAX_RAW:
        raise BadImage('image must be H×W×3 within the pixel limit')
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(body, size + 1)      # bounded: no decompression bomb
    except zlib.error:
        raise BadImage('body is not zlib data') from None
    if len(raw) != size or inflater.unconsumed_tail:
        raise BadImage('body does not match X-Shape')
    return np.frombuffer(raw, dtype=np.uint8).reshape(height, width, channels)


# ---- worker side ----------------------------------------------------------------------------

class RemoteOcrEngine:
    """Same interface as ``SenOcrEngine`` (``version``, ``recognize``), over HTTP."""

    def __init__(self, url: str, token: str, client=None, timeout: float = TIMEOUT_S):
        import httpx
        from .worker import RetryableError
        self._retryable = RetryableError
        self.url = url.rstrip('/')
        self._client = client or httpx.Client(base_url=self.url, timeout=timeout)
        self._client.headers['Authorization'] = f'Bearer {token}'
        health = self._send('GET', '/health')
        self.version = health['version']

    def _send(self, method: str, path: str, **kwargs) -> dict:
        import httpx
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            # The server is down or the network dropped: the unit retries later.
            raise self._retryable('OCR_REMOTE_UNREACHABLE', f'{self.url}: {type(exc).__name__}') from None
        if response.status_code == 200:
            return response.json()
        try:
            detail = response.json().get('detail', '')
        except ValueError:
            detail = response.text[:200]
        if response.status_code == 507:
            raise OcrOutOfMemory(str(detail))
        if response.status_code in (401, 403):
            raise OcrUnavailable(f'OCR server refused the token ({self.url})')
        if response.status_code >= 500:
            raise self._retryable('OCR_REMOTE_ERROR', f'{response.status_code}: {detail}'[:200])
        raise OcrUnavailable(f'OCR server answered {response.status_code}: {detail}'[:200])

    def recognize(self, image) -> list[dict]:
        body, shape = encode(image)
        return self._send('POST', '/v1/recognize', content=body,
                          headers={'Content-Type': 'application/octet-stream',
                                   'X-Shape': shape})['items']


def engine_from_env() -> RemoteOcrEngine | None:
    url = os.environ.get('OCR_REMOTE_URL', '').strip()
    if not url:
        return None
    token = os.environ.get('OCR_REMOTE_TOKEN', '').strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise OcrUnavailable(f'OCR_REMOTE_URL is set but OCR_REMOTE_TOKEN is shorter than '
                             f'{MIN_TOKEN_LENGTH} characters')
    return RemoteOcrEngine(url, token)


# ---- server side ----------------------------------------------------------------------------

def create_server(engine=None, token: str | None = None):
    """ASGI app; ``engine`` defaults to the local ``SenOcrEngine`` (loaded on first page)."""
    import anyio
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from .ocr import SenOcrEngine

    token = token if token is not None else os.environ.get('OCR_SERVER_TOKEN', '')
    if len(token) < MIN_TOKEN_LENGTH:
        raise RuntimeError(f'OCR_SERVER_TOKEN must be at least {MIN_TOKEN_LENGTH} characters')
    expected = f'Bearer {token}'.encode()
    engine = engine or SenOcrEngine()
    app = FastAPI(title='BAZI-AI OCR', docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def bearer(request: Request, call_next):
        given = request.headers.get('authorization', '').encode()
        if not hmac.compare_digest(given, expected):
            return JSONResponse({'detail': 'missing or invalid token'}, status_code=401,
                                headers={'WWW-Authenticate': 'Bearer'})
        return await call_next(request)

    @app.get('/health')
    def health():
        return {'version': engine.version}

    @app.post('/v1/recognize')
    async def recognize(request: Request):
        if int(request.headers.get('content-length') or 0) > MAX_BODY:
            return JSONResponse({'detail': 'body too large'}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BODY:
                return JSONResponse({'detail': 'body too large'}, status_code=413)
        try:
            image = decode(bytes(body), request.headers.get('x-shape', ''))
        except BadImage as exc:
            return JSONResponse({'detail': str(exc)}, status_code=400)
        try:
            # The engine serialises pages itself; run it off the event loop.
            items = await anyio.to_thread.run_sync(engine.recognize, image)
        except OcrOutOfMemory as exc:
            return JSONResponse({'detail': str(exc)[:200]}, status_code=507)
        except OcrUnavailable as exc:
            return JSONResponse({'detail': str(exc)[:200]}, status_code=503)
        log.info('ocr page', extra={'event': 'ocr_remote_page', 'pixels': image.shape[0] * image.shape[1],
                                    'items': len(items)})
        return JSONResponse({'items': json.loads(json.dumps(items, default=str))})

    return app
