"""RFC 9457 Problem Details responses with the error codes of docs/10.

Exception text never reaches the client: unexpected errors become a generic 500
whose detail only points at the request_id to search in the logs.
"""
from __future__ import annotations

from http import HTTPStatus
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import request_id_var

PROBLEM_JSON = 'application/problem+json'
log = logging.getLogger('bazi.errors')

# Generic HTTP statuses mapped to the docs/10 codes; others fall back to HTTP_<status>.
STATUS_CODES = {
    401: 'AUTH_REQUIRED',
    403: 'FORBIDDEN',
    404: 'NOT_FOUND',
    405: 'METHOD_NOT_ALLOWED',
    409: 'CONFLICT',
    412: 'REVISION_MISMATCH',
    413: 'FILE_TOO_LARGE',
    415: 'UNSUPPORTED_TYPE',
    422: 'VALIDATION_ERROR',
    429: 'RATE_LIMITED',
    503: 'SERVICE_UNAVAILABLE',
}


class AppError(Exception):
    """Expected failure with a stable code; ``detail`` must be safe to show."""

    def __init__(self, status: int, code: str, detail: str | None = None,
                 field_errors: list[dict] | None = None, headers: dict | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.field_errors = field_errors or []
        self.headers = headers


def problem_response(status: int, code: str, detail: str | None = None,
                     field_errors: list[dict] | None = None,
                     headers: dict | None = None) -> JSONResponse:
    body = {
        'type': f'urn:bazi:problem:{code.lower()}',
        'title': HTTPStatus(status).phrase,
        'status': status,
        'code': code,
        'detail': detail,
        'request_id': request_id_var.get(),
        'field_errors': field_errors or [],
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return problem_response(exc.status, exc.code, exc.detail, exc.field_errors, exc.headers)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = STATUS_CODES.get(exc.status_code, f'HTTP_{exc.status_code}')
    # Framework details such as "Not Found" are generic; keep them, they hold no data.
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem_response(exc.status_code, code, detail, headers=getattr(exc, 'headers', None))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Messages only: echoing the rejected input could leak passwords or birth data.
    fields = [{'path': '.'.join(str(p) for p in err['loc']), 'message': err['msg']}
              for err in exc.errors()]
    return problem_response(422, 'VALIDATION_ERROR', 'Request validation failed', fields)


def unhandled_problem(exc: BaseException) -> JSONResponse:
    log.error('unhandled exception', exc_info=(type(exc), exc, exc.__traceback__),
              extra={'event': 'unhandled_exception', 'error_code': 'INTERNAL_ERROR'})
    return problem_response(500, 'INTERNAL_ERROR',
                            'Unexpected server error; quote request_id when reporting it')


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
